import functools
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page

from src.config import evidence_image_extension
from src.credential_redaction import (
    is_sensitive_field,
    masked_screenshot_page,
    redact_text,
    redact_url_credentials,
    redact_value,
)
from src.evidence_image import encode_evidence_image
from src.evidence_loader import load_verification_strength, match_verification_to_test
from src.evidence_serializer import EvidenceSerializer
from src.failure_reporter import FailureReporter
from src.hover_click_utils import try_hover_and_click
from src.locator_fallback import LocatorFallback
from src.page_identity import same_page as _page_identity_same_page
from src.storage import get_storage

logger = logging.getLogger(__name__)


def _same_page(expected: str, actual: str) -> bool:
    """Return True when two URLs address the same page.

    Delegates to :func:`src.page_identity.same_page`, the one place that owns
    the page-identity rule: scheme + host + path only, ignoring query and
    fragment. The story-named-query exception (a story that names the bit after
    the ``?`` pins the query) is also documented there.
    """
    return _page_identity_same_page(expected, actual)


class _LocatorNotFoundError(RuntimeError):
    """Raised when a click target does not exist on the current page.

    The failure is recorded once with ``fast_fail=True`` (no expensive
    metadata/screenshot/diagnosis) and re-raised; the outer handler must
    not re-record it.
    """


class PageMismatchError(RuntimeError):
    """Raised when a step ran on a page other than the one its locator was
    resolved against (the gate-2 false-green class).

    A step that "succeeds" on the wrong page has not verified its
    condition — a flow divergence that used to be recorded in evidence only
    (AI-067) while the test still passed green. From the gate-2 work on
    B-093, a recorded mismatch fails the step: a passing test must
    provably have checked its condition on the page it was resolved for.
    """


class NavigationStatusError(RuntimeError):
    """Raised when a navigation reaches an HTTP error page (d-0032).

    Playwright raises only on network, protocol and timeout failures, so a
    404 or a 500 used to be recorded as a PASSED navigation step, with a
    screenshot of the error page as its evidence. A page the browser was not
    seen to reach is not evidence of arrival, so the step is recorded as
    failed - naming the status, the requested address and the address the
    browser actually ended on - and the test stops there.
    """


def _response_status(response: Any) -> int | None:
    """Return the HTTP status of a navigation response, or None when unknown.

    None covers the honest unknowns: a same-document navigation has no
    response, and a test double returns something that is not an integer. An
    unknown status is never treated as an error status.
    """
    try:
        status = getattr(response, "status", None)
    except Exception:
        return None
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    return status


def _redirect_chain(response: Any) -> list[str]:
    """Return the addresses a navigation was redirected through, oldest first.

    Playwright keeps the hops on ``response.request.redirected_from``. This
    catches a redirect that ends where it started (a session bounce that
    returns to the same address), which the final URL alone cannot show. A
    response that does not expose the chain - a test double, a same-document
    navigation - yields ``[]``, never a guess.
    """
    urls: list[str] = []
    node = getattr(response, "request", None)
    for _ in range(10):
        node = getattr(node, "redirected_from", None)
        if node is None:
            break
        address = getattr(node, "url", None)
        if not isinstance(address, str):
            break
        urls.append(address)
    return list(reversed(urls))


def _address_changed(requested: str, final: str) -> bool:
    """True when the browser ended on a different address than it was asked for.

    A plain string comparison, used only to REPORT a redirect when the page
    identity already matches - so it must not treat a relative address (which
    the browser resolves to an absolute one) as a redirect, and it must not
    hide a trailing-slash or query change, which is a redirect the user may
    want to know about.
    """
    if not requested or not final:
        return False
    if urlparse(requested).scheme not in ("http", "https"):
        return False
    return requested != final


# t-1063: the tracker and the generated conftest must agree on what "a failed
# step carries on" means. A package shipping a new tracker with an old conftest
# would carry on and never fail the test - a silent success. Both sides declare
# this marker; the fixture refuses to run when they differ.
JOURNEY_PROTOCOL = "carry-on-2"

# t-1095: the owner's rules for when a generated test stops. A journey carries on
# after what the STEP wanted went wrong (a missing element, a dead click, an
# assertion, a 404 page with a document); it stops only for a reason that has
# nothing to do with the step's intent. Each reason is named in plain words in the
# record and the report.
STOP_PAGE_GONE = (
    "the page or browser was closed, the target crashed, or a protocol error came back - nothing further can run"
)
STOP_UNRESPONSIVE = (
    "the page stopped responding - a liveness check after the failure raised, so nothing further can run"
)
STOP_NO_ARRIVAL = "the journey never reached its next page"
STOP_TIME_LIMIT = "the per-test time limit was reached"

STOP_REASONS = {
    "page_gone": STOP_PAGE_GONE,
    "unresponsive": STOP_UNRESPONSIVE,
    "no_arrival": STOP_NO_ARRIVAL,
    "time_limit": STOP_TIME_LIMIT,
}

#: Default per-test time limit in seconds. A backstop, not the rule: a journey
#: that runs this long is stopped and marked timed out, and the rest of the story
#: still reports. ``AITEST_TEST_TIME_LIMIT`` overrides it; ``0`` disables it.
DEFAULT_TEST_TIME_LIMIT_S = 300.0

#: Messages that mean the page itself is gone, whatever the step wanted.
_PAGE_GONE_MARKERS = (
    "has been closed",
    "target closed",
    "target crashed",
    "browser closed",
    "protocol error",
    "session closed",
    "page crashed",
)


class JourneyStopped(RuntimeError):
    """Raised when the journey stops for a reason that is not the step's intent.

    The tracker has already recorded the stop (``stop`` on the journey record, in
    the sidecar) and the failed steps before it. The message carries the whole
    journey summary, so the test fails once with everything a reader needs.
    """


def _normalised_address(url: str) -> tuple[str, str, str, str, str]:
    """The full address as a comparable tuple: scheme, host, path, query, fragment.

    The path's trailing slash is dropped - "/cart" and "/cart/" are the same
    address for this question (t-1098). Query and fragment are KEPT: "/products"
    -> "/products?page=2" and "/" -> "/#pricing" are moves, even though the page
    identity rule ignores them by design.
    """
    parsed = urlparse(str(url))
    return (
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        parsed.query,
        parsed.fragment,
    )


def _address_moved(before: str, after: str) -> bool | None:
    """Did the browser move at all? None when an address has no host to compare.

    Deliberately NOT the page-identity rule: identity answers "is this the page I
    expected" (query and fragment ignored, so dynamic ids are fine). This answers
    "did the address change", where a query-only or fragment-only change is a
    move and must not stop a journey (t-1098).
    """
    if not urlparse(before).netloc or not urlparse(after).netloc:
        return None
    return _normalised_address(before) != _normalised_address(after)


def _test_time_limit_s() -> float:
    """The per-test backstop, in seconds. ``AITEST_TEST_TIME_LIMIT=0`` disables it."""
    raw = os.environ.get("AITEST_TEST_TIME_LIMIT", "")
    if not raw:
        return DEFAULT_TEST_TIME_LIMIT_S
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_TEST_TIME_LIMIT_S


def _carries_on[StepMethod: Callable[..., Any]](method: StepMethod) -> StepMethod:
    """Let a failed step fail the TEST at its end, not the journey at that step.

    The owner's decision, 2026-10-29: "carry on as well... some links might not
    be static so they might change every single time... in that situation we
    want the test to be able to carry on."

    The method has already recorded the failed step when it raises. This wrapper
    keeps that record, drops the exception, and lets the next step run. The test
    is then failed ONCE, at its end, from ``journey_summary()`` (the generated
    conftest reads it and fails the report) - one failure, complete evidence.

    The single condition that still stops a journey is ``_cannot_continue()``:
    the page or its browser context is closed, so no later step could run at all.

    A HAND-SHAKE, not just a version marker (t-1066). Swallowing a failure is only
    safe when something will fail the test at its end. The generated conftest sets
    ``journey_hooked = True`` when its fixture creates the tracker; with no hook
    registered - a conftest written before the carry-on feature, which carries no
    marker and no report hook - the exception is RE-RAISED, so the test fails the
    old way instead of passing silently. What each guard catches:

    - the ``JOURNEY_PROTOCOL`` marker (checked in the conftest fixture): drift
      between two versions that both carry the check, and a NEW conftest with an
      OLD tracker (which fails even earlier, at import).
    - this hand-shake: a NEW tracker with a conftest that never registered.
    """

    @functools.wraps(method)
    def wrapper(self: EvidenceTracker, *args: Any, **kwargs: Any) -> Any:
        before = len(self.steps)
        self._stop_when_over_the_time_limit()
        try:
            return method(self, *args, **kwargs)
        except JourneyStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - see the docstring: recorded, then carried
            if not self.journey_hooked:
                # No hook means nothing would fail the test at its end, so a
                # swallowed failure would be a silent pass. Fail here instead.
                raise
            if self._page_gone(exc):
                # Reason 1: nothing further can run, whatever the step wanted.
                self._stop_journey("page_gone", str(exc)[:300])
            self._record_unrecorded_failure(method.__name__, args, exc, before)
            if not self._liveness_ok():
                # Reason 2: one trivial call against the page raised.
                self._stop_journey("unresponsive", str(exc)[:300])
            return None

    return cast(StepMethod, wrapper)


class EvidenceTracker:
    def __init__(
        self,
        page: Page,
        test_name: str,
        condition_ref: str = "unknown",
        story_ref: str = "unknown",
        *,
        evidence_root: Path | None = None,
        test_package_dir: Path | None = None,
    ) -> None:
        """Initialize the EvidenceTracker.

        Args:
            page: Playwright Page instance.
            test_name: Name of the test (used for evidence file naming).
            condition_ref: Condition/test case reference (e.g. "TC01.01").
            story_ref: User story reference (e.g. "S01").
            evidence_root: Legacy — root directory for evidence. Deprecated; use
                test_package_dir instead. When both are provided, test_package_dir
                takes precedence.
            test_package_dir: Directory containing the test file. Evidence is written
                to <test_package_dir>/evidence/ so each test package gets its own
                evidence folder alongside its tests.
        """
        self.page = page
        self.test_name = test_name
        self.condition_ref = condition_ref
        self.story_ref = story_ref

        self.steps: list[dict[str, Any]] = []
        # t-0929: page arrivals the test EXPECTS, recorded immediately before
        # the assertion. Separate from ``steps`` because an expectation is not
        # a test step (it must not add to the pass/skip counts).
        self.page_expectations: list[dict[str, Any]] = []
        self.start_time = time.time()
        # AI-067: the page a step actually RAN on — captured before the action,
        # because a click legitimately navigates away from the page its locator
        # was resolved against. Compared with ``expected_page`` in
        # ``_record_step``.
        self._step_entry_url: str = ""
        # t-1066: set by the generated conftest fixture. Until something promises
        # to fail the test at its end, a failed step raises as it always did.
        self.journey_hooked: bool = False
        # t-1095: why the journey stopped, when it did ({"reason", "detail"}).
        self.stop: dict[str, str] | None = None
        self._time_limit_s: float = _test_time_limit_s()

        # A5: per-page hint for the adaptive encoder. A page URL lands here when
        # a full-page capture on it found lossless WebP would NOT shrink the
        # file, so later captures on the same URL skip the ~330 ms method=0
        # probe that would just lose again. It only ever skips a probe — every
        # stored image stays lossless and pixel-identical (a cache miss or a
        # denser page simply re-probes and may pick WebP).
        self._encode_png_won: set[str] = set()

        # Determine evidence directory: per-test package takes precedence
        package_root: Path | None = None
        if test_package_dir is not None:
            package_root = Path(test_package_dir)
            self.evidence_dir = package_root / "evidence"
        elif evidence_root is not None:
            package_root = evidence_root
            self.evidence_dir = evidence_root / "evidence"
        else:
            # Fallback to workspace evidence directory
            self.evidence_dir = get_storage().evidence_dir()

        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.sidecar_path = self.evidence_dir / f"{self.test_name}.evidence.json"

        # B-100: stamp the emit-time verification verdict into the sidecar, so
        # the evidence bundle itself says what this test provably checked. The
        # pipeline wrote it beside the tests; a package without it (older run)
        # yields an empty dict, never an error.
        self.verification: dict[str, Any] = {}
        if package_root is not None:
            verdict = match_verification_to_test(load_verification_strength(package_root), self.test_name)
            if verdict is not None:
                self.verification = verdict

        # Load run history immediately so we can increment during steps if needed
        self.run_history = self._load_previous_history()

        # We also need to map previous steps to increment their individual run counts run_count
        self.previous_steps_data = self._load_previous_steps()

    @staticmethod
    def _clean_label(label: str) -> str:
        """Convert raw placeholder tokens into cleaner user-facing labels."""
        raw = str(label or "").strip()
        match = re.fullmatch(r"\{\{([A-Z_]+):(.+)\}\}", raw)
        if not match:
            return raw

        action = match.group(1).strip().lower().replace("_", " ")
        description = match.group(2).strip()
        if not description:
            return raw
        return f"{action.title()}: {description}"

    def _dismiss_consent_overlays(self) -> None:
        """Delegate to central consent dismissal utility."""
        from src.browser_utils import dismiss_consent_overlays

        dismiss_consent_overlays(self.page)

    @staticmethod
    def _is_modal_close_target(locator: str) -> bool:
        """True when the locator is a confirmation-modal close control.

        Generated tests emit explicit "close popup / OK / Continue Shopping"
        steps for added-to-cart modals; the tracker auto-dismisses those same
        modals before every click. When the modal is already gone, such a step
        is a satisfied no-op, not a failure.
        """
        low = locator.lower()
        return any(
            t in low
            for t in (
                "close-modal",
                "close_modal",
                "close modal",
                "modal-close",
                "modal_close",
                "continue shopping",
                "btn-success",
            )
        )

    def _dismiss_ad_overlays(self) -> None:
        """Delegate to central consent dismissal utility (includes ad overlay handling)."""
        from src.browser_utils import dismiss_consent_overlays

        dismiss_consent_overlays(self.page)

    def _dismiss_confirmation_modals(self) -> None:
        """Dismiss confirmation modals/popups that block pointer events.

        E-commerce sites show an "added to cart" modal (#cartModal) that
        intercepts clicks on navigation links. Best-effort and non-destructive:
        if no modal is visible these selectors won't match and this is a no-op.
        Mirrors the journey scraper's ``_dismiss_modals``.
        """
        # B-015 lesson: never match generic button text globally — saucedemo's
        # cart page has a visible "Continue Shopping" button that would get
        # clicked, navigating the generated test back to inventory. Text-based
        # dismissal is scoped to modal/dialog containers only.
        modal_containers = "#cartModal, .modal, [role='dialog'], .modal-dialog, .modal-content"
        dismiss_selectors = [
            f"{modal_containers} button:has-text('Continue Shopping')",
            f"{modal_containers} .continue-shopping",
            f"{modal_containers} .close",
            f"{modal_containers} .modal-close",
            f"{modal_containers} .close-btn",
            f"{modal_containers} [data-dismiss='modal']",
            f"{modal_containers} .modal-footer .btn",
            f"{modal_containers} button.btn-success.close-modal",
        ]
        for selector in dismiss_selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() and locator.is_visible(timeout=200):
                    locator.click(timeout=1000)
                    self.page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    def _load_previous_history(self) -> dict[str, int]:
        if self.sidecar_path.exists():
            try:
                return EvidenceSerializer.load_run_history(self.sidecar_path)
            except Exception:
                pass
        return {"total_runs": 0, "passed_runs": 0, "failed_runs": 0}

    def _load_previous_steps(self) -> list[dict[str, Any]]:
        if self.sidecar_path.exists():
            try:
                return EvidenceSerializer.load_steps(self.sidecar_path)
            except Exception:
                pass
        return []

    def _get_element_metadata(self, locator: str | None = None) -> dict[str, Any]:
        """Calculates bbox and viewport percentages for the element."""
        if not locator:
            return {}

        # The URL this measurement is taken on. A click is measured BEFORE it
        # runs, so the page it ran on is not the URL the step ends on (B-105).
        # The overlay needs the measurement page, not the destination page.
        measured_url = self._safe_page_url()

        loc = self.page.locator(locator).first

        tag = ""
        try:
            # We evaluate tag name
            tag = loc.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            pass

        element_id = ""
        test_id = ""
        href = ""
        target = ""
        try:
            element_id = loc.get_attribute("id") or ""
            test_id = loc.get_attribute("data-testid") or ""
            raw_href = loc.get_attribute("href") or ""
            # Mock pages return MagicMock here — only keep real strings (B-029).
            href = raw_href if isinstance(raw_href, str) else ""
            # B-072: target="_blank" links open a new tab — the post-click
            # check needs to know, to distinguish "new tab" from "swallowed".
            raw_target = loc.get_attribute("target") or ""
            target = raw_target if isinstance(raw_target, str) else ""
        except Exception:
            pass

        bbox = None
        viewport_pct = None
        doc_width: int | None = None
        doc_height: int | None = None

        try:
            # Best effort: bring into view so bbox is meaningful.
            try:
                loc.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass

            # Capture full document size so coordinates relative to frame always match.
            doc_size = self.page.evaluate(
                "() => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight })"
            )
            dw = max(doc_size["width"], 1)
            dh = max(doc_size["height"], 1)
            # The document the percentage is relative to. The same percentage
            # lands on a different pixel on a page of a different height, so
            # the overlay may only draw this marker on a frame of this size.
            doc_width = int(dw)
            doc_height = int(dh)

            raw_bbox = loc.bounding_box()
            if raw_bbox:
                # bounding_box() is relative to the viewport; the evidence
                # screenshot is full-page (whole document), so the recorded
                # percentages must be document-relative. Without the scroll
                # correction, markers land off-page — e.g. a negative y for an
                # element scrolled above the viewport (AI-043 validator caught
                # y=-4.02 in production evidence).
                try:
                    scroll = self.page.evaluate("() => ({ x: window.scrollX, y: window.scrollY })")
                    scroll_x = float(scroll.get("x", 0))
                    scroll_y = float(scroll.get("y", 0))
                except Exception:
                    scroll_x = 0.0
                    scroll_y = 0.0

                center_x = raw_bbox["x"] + (raw_bbox["width"] / 2)
                center_y = raw_bbox["y"] + (raw_bbox["height"] / 2)

                bbox = {
                    "x": raw_bbox["x"],
                    "y": raw_bbox["y"],
                    "width": raw_bbox["width"],
                    "height": raw_bbox["height"],
                    "center_x": center_x,
                    "center_y": center_y,
                }

                # Record center point as percentage of FULL document, clamped
                # to [0, 100] so fixed/edge-positioned elements can never paint
                # an off-page marker.
                doc_center_x = center_x + scroll_x
                doc_center_y = center_y + scroll_y
                viewport_pct = {
                    "x": min(100.0, max(0.0, (doc_center_x / dw) * 100)),
                    "y": min(100.0, max(0.0, (doc_center_y / dh) * 100)),
                }
        except Exception:
            pass

        return {
            "tag": tag,
            "element_id": element_id if element_id else None,
            "test_id": test_id if test_id else None,
            "href": href if href else None,
            "target": target if target else None,
            "bbox": bbox,
            "viewport_pct": viewport_pct,
            "doc_width": doc_width,
            "doc_height": doc_height,
            "measured_url": measured_url,
        }

    def _record_step(
        self,
        step_type: str,
        label: str,
        locator: str | None = None,
        value: str | None = None,
        take_screenshot: bool = False,
        error: str | None = None,
        matched_text: str | None = None,
        fallback_used: bool = False,
        fallback_chain: list[dict[str, Any]] | None = None,
        elapsed_ms: int | None = None,
        fast_fail: bool = False,
        element_metadata: dict[str, Any] | None = None,
        expected_page: str = "",
        navigation: dict[str, Any] | None = None,
        mismatch_wording: str = "its locator was resolved against",
    ) -> None:
        """Record one evidence step.

        Args:
            expected_page: The page this step was supposed to run on - the page
                its locator was resolved against, or, for a navigation step,
                the page it was asked to reach. When the step actually runs
                somewhere else the mismatch is recorded on the step result
                (``page_mismatch``) so a wrong-page resolution is visible
                instead of silently passing. Empty means "not checked".
            navigation: What the browser did for a navigation step
                (``requested``, ``final``, ``status``, and a ``note`` when a
                redirect was recorded but not judged). Stored on the step so
                the evidence names where the browser actually went.
            mismatch_wording: How the expectation is described in the failure
                text - "its locator was resolved against" for an element step,
                "the step was asked for" for a navigation.
            fast_fail: True when the step failed because the locator does not
                exist on the current page. Skips the expensive element-metadata
                capture (waits ~5s per Playwright call on a missing element),
                the full-page screenshot and the failure diagnosis.
            element_metadata: Pre-captured element metadata to use instead of
                re-querying the locator. Critical after a click that navigated
                away — the old locator no longer exists and every un-timed
                Playwright call would wait the full default timeout (~30s each,
                ~120s total), hanging the test. Failed steps (error set) also
                skip re-querying — same hang class (B-041).
        """
        step_idx = len(self.steps)

        # Calculate run count for this specific step by checking previous steps
        step_run_count = 1
        if len(self.previous_steps_data) > step_idx:
            prev_step = self.previous_steps_data[step_idx]
            if prev_step.get("type") == step_type:
                step_run_count = prev_step.get("result", {}).get("run_count", 0) + 1

        screenshot_path = None
        frame_url = ""
        frame_doc_width: int | None = None
        frame_doc_height: int | None = None
        if take_screenshot:
            screenshot_stem = f"{self.test_name}_{step_idx}_{step_type}_{int(time.time())}"
            # Default name; the bytes path may re-point it when the adaptive
            # encoder (A5) keeps the PNG instead of writing WebP.
            screenshot_name = f"{screenshot_stem}{evidence_image_extension()}"
            screenshot_full_path = self.evidence_dir / screenshot_name
            try:
                # Evidence must reflect the settled page. Product grids use
                # lazy-loaded images, so a screenshot taken the instant an
                # assert returns shows blank/broken images — a spurious
                # "missing image" defect in the evidence. Wait (bounded) for
                # in-flight images to finish before capturing; never block
                # the suite (capped at 4s, errors ignored).
                try:
                    self.page.evaluate(
                        """() => Promise.race([
                            Promise.all(Array.from(document.images).map(
                                img => img.complete ? Promise.resolve()
                                    : new Promise(res => {
                                        img.addEventListener('load', res, { once: true });
                                        img.addEventListener('error', res, { once: true });
                                    })
                            )),
                            new Promise(res => setTimeout(res, 4000)),
                        ])"""
                    )
                except Exception:
                    pass
                # Take full page screenshot so coordinates relative to frame always match.
                # AI-045 §8.4: blank filled credential fields (password inputs and
                # text inputs whose attributes look credential-ish) for the
                # duration of the capture, then restore — evidence screenshots
                # must never contain typed secrets in the clear.
                with masked_screenshot_page(self.page):
                    # The frame records the page it shows and the size of the
                    # document it captured. A marker measured on another
                    # document cannot be drawn on this frame (B-105).
                    frame_url = self._safe_page_url()
                    try:
                        frame_doc = self.page.evaluate(
                            "() => ({ width: document.documentElement.scrollWidth,"
                            " height: document.documentElement.scrollHeight })"
                        )
                        if isinstance(frame_doc, dict):
                            frame_doc_width = int(max(frame_doc.get("width") or 0, 1))
                            frame_doc_height = int(max(frame_doc.get("height") or 0, 1))
                    except Exception:
                        pass
                    screenshot_bytes = self.page.screenshot(full_page=True)
                    if isinstance(screenshot_bytes, bytes):
                        # A5: lossless WebP at method=0 — or the original PNG
                        # whenever WebP would not be strictly smaller. The
                        # extension follows the format actually written
                        # (src/evidence_image.py). Pages where WebP already
                        # lost skip the probe entirely (self._encode_png_won).
                        current_url = self._safe_page_url()
                        if current_url in self._encode_png_won:
                            data, actual_fmt = screenshot_bytes, "png"
                        else:
                            data, actual_fmt = encode_evidence_image(screenshot_bytes)
                            if actual_fmt == "png" and current_url:
                                self._encode_png_won.add(current_url)
                        screenshot_name = f"{screenshot_stem}.{actual_fmt}"
                        screenshot_full_path = self.evidence_dir / screenshot_name
                        screenshot_full_path.write_bytes(data)
                    else:
                        # Capture backends that only support path-based capture —
                        # and test doubles that return a sentinel — write through
                        # Playwright instead.
                        self.page.screenshot(path=str(screenshot_full_path), full_page=True)
                screenshot_path = f"evidence/{screenshot_name}"
            except Exception as exc:
                # Evidence collection must never break test execution, but a
                # missing screenshot should not be silent — it is the most
                # useful failure artifact (B-033).
                logger.warning("screenshot capture failed for %s: %s", screenshot_name, exc)

        # Failed steps skip metadata capture (B-041): a failing locator is
        # missing/hidden/timed-out, and every un-timed Playwright call
        # (_get_element_metadata: evaluate / get_attribute / bounding_box)
        # waits the full default timeout (~30s each) on a missing element —
        # the B-029 hang class. A failed assertion previously burned ~120s
        # and got killed by pytest-timeout, aborting the whole suite. The
        # failure note + screenshot carry the diagnostic payload instead.
        if fast_fail or error or element_metadata is not None:
            element_data = element_metadata if element_metadata is not None else {}
        else:
            element_data = self._get_element_metadata(locator)

        # AI-067: the page a step RAN on, compared with the page its locator
        # was resolved against. The trail/scope can be wrong even when an
        # element resolves (a page-level container matches anything), so a
        # mismatch must never pass silently.
        page_mismatch: dict[str, str] | None = None
        if expected_page:
            # A navigation runs on the page it LANDS on, so read the live URL.
            # Every other step runs on the page it was entered on, which the
            # caller records before acting - reading the live URL there would
            # compare against a page the step itself may have changed (t-1031:
            # a goto that trusted the entry URL compared the PREVIOUS step's
            # page and failed a correct arrival).
            if step_type == "navigate":
                actual_page = self._safe_page_url()
            else:
                actual_page = self._step_entry_url or self._safe_page_url()
            if not _same_page(expected_page, actual_page):
                page_mismatch = {"expected": expected_page, "actual": actual_page}

        # On failure, generate self-diagnosing failure evidence (Tier 1).
        failure_note: str | None = None
        diagnosis: dict[str, Any] | None = None
        if error and not fast_fail:
            try:
                diagnosis = FailureReporter.diagnose_failure(self.page, locator, step_type, error)
                failure_note = FailureReporter.generate_failure_note(diagnosis)
            except Exception:
                # Diagnosis is best-effort; don't let it break test execution.
                failure_note = f"[diagnosis failed: {error[:100]}]"
        elif error and fast_fail:
            # Fast-fail errors are self-diagnosing ("not found on current page…")
            # but must still carry a failure note for the evidence index (B-033).
            failure_note = str(error)[:300]
        elif page_mismatch is not None:
            failure_note = (
                f"Step ran on '{page_mismatch['actual']}' but {mismatch_wording} "
                f"'{page_mismatch['expected']}' - the flow "
                "diverged, so this check did not verify its condition."
            )

        # Determine step status — "partial_pass" when fallback was used.
        # A mismatch on a would-be-passing step is a failure: the check ran
        # on the wrong page, so it verified nothing (B-093 gate 2).
        if error:
            status = "failed"
        elif page_mismatch is not None:
            status = "failed"
        elif fallback_used:
            status = "partial_pass"
        else:
            status = "passed"

        result: dict[str, Any] = {
            "status": status,
            "elapsed_ms": elapsed_ms if elapsed_ms is not None else 0,
            "run_count": step_run_count,
            "matched_text": matched_text,
            "error": error,
            "failure_note": failure_note,
            "diagnosis": diagnosis,
        }

        if fallback_used:
            result["fallback_used"] = True
            result["fallback_chain"] = fallback_chain or []

        if page_mismatch is not None:
            result["page_mismatch"] = page_mismatch

        if navigation is not None:
            result["navigation"] = navigation

        self.steps.append(
            {
                "step": step_idx + 1,
                "type": step_type,
                "label": self._clean_label(label),
                "locator": locator,
                "value": value,
                "screenshot": screenshot_path,
                "frame_url": frame_url,
                "frame_doc_width": frame_doc_width,
                "frame_doc_height": frame_doc_height,
                "element": element_data,
                "url": self._safe_page_url(),  # B-033: per-step URL so flow divergence is traceable
                "result": result,
            }
        )

        # B-035: persist incrementally so a killed/timed-out process still
        # leaves evidence. Cheap (small JSON) — write on the first step and on
        # any failed/partial step; the final write() overwrites with the real
        # status. t-1057: a failure also stamps the steps that come after it, so
        # the incremental sidecar already marks them.
        self._mark_off_course_steps()
        if step_idx == 0 or status in ("failed", "partial_pass"):
            self._persist_sidecar("running")

        # Gate 2 (B-093): a mismatch on a would-be-passing step now fails the
        # test. Evidence is persisted above first, so the sidecar keeps the
        # mismatch. The exception still marks the step as a failure, and the
        # journey carries on (t-1057): with the page intact, the later steps run
        # and the test is failed once at its end from journey_summary(). Only a
        # closed page stops it. A step that already failed for its own reason
        # keeps its original error — the mismatch stays recorded, it does not
        # mask the real cause.
        if page_mismatch is not None and not error:
            raise PageMismatchError(
                f"{step_type} '{label}' ran on '{page_mismatch['actual']}' but "
                f"{mismatch_wording} '{page_mismatch['expected']}'. The flow "
                "diverged from the resolved page context; this check did not "
                "verify its condition."
            )

    def _safe_page_url(self) -> str:
        try:
            return str(self.page.url)
        except Exception:
            return ""

    # --- t-1057: carry on after a failed step, report once at the end ---

    def _cannot_continue(self) -> bool:
        """True only when the rest of the journey cannot run at all.

        THE single stop condition: the page is closed, or its browser context is
        closed. A crash that kills the page leaves nothing for the later steps to
        run on, so the test ends there. Every other failure is recorded and the
        journey carries on.
        """
        try:
            if self.page.is_closed() is True:
                return True
        except Exception:
            pass
        try:
            context = self.page.context
            if context is not None and context.is_closed() is True:
                return True
        except Exception:
            pass
        return False

    def _click_moved(self, original_url: str, pages_before: tuple[Any, ...]) -> bool:
        """True when the click changed the page (URL identity) or opened a tab."""
        try:
            if len(tuple(self.page.context.pages)) > len(pages_before):
                return True
        except Exception:
            pass
        # Unknown addresses never stop a journey; a query or fragment change does
        # count as a move (t-1098).
        return _address_moved(original_url, self._safe_page_url()) is not False

    def _page_gone(self, exc: Exception) -> bool:
        """Reason 1: the page, its context or the protocol is gone."""
        if self._cannot_continue():
            return True
        message = str(exc).lower()
        return any(marker in message for marker in _PAGE_GONE_MARKERS)

    def _liveness_ok(self) -> bool:
        """One trivial call against the page. False means nothing further can run.

        Reason 2: the step failure may have been a symptom of a page that is no
        longer answering. A closed page is already reason 1; this catches the page
        that still claims to be open but raises on the cheapest possible call.
        """
        try:
            self.page.evaluate("() => 1")
        except Exception:
            return False
        return True

    def _stop_when_over_the_time_limit(self) -> None:
        """Reason 4: the per-test backstop. Not the main rule - a last resort."""
        if self._time_limit_s <= 0:
            return
        if self.stop is not None:
            return
        elapsed = time.time() - self.start_time
        if elapsed > self._time_limit_s:
            self._stop_journey(
                "time_limit",
                f"the test ran {elapsed:.0f}s, over the {self._time_limit_s:.0f}s per-test limit",
            )

    def _fail_stopped_step(self, detail: str) -> None:
        """The step that tripped rule 3 did not do its job: mark it failed.

        Exactly one step is recorded for a stop - the real one - and it is the
        one that failed, so the count and the summary cannot lie (t-1098).
        """
        if not self.steps:
            return
        result = self.steps[-1].setdefault("result", {})
        result["status"] = "failed"
        result["error"] = result.get("error") or detail
        result["failure_note"] = detail

    def _stop_journey(self, reason: str, detail: str) -> None:
        """Record that the journey stopped, persist it, and raise it once.

        ``reason`` is one of the four keys in :data:`STOP_REASONS`; the plain-words
        text for it goes into the record, the sidecar and the report.
        """
        self.stop = {"reason": reason, "detail": detail}
        self._persist_sidecar("running")
        raise JourneyStopped(self.journey_summary() or f"Journey stopped: {STOP_REASONS.get(reason, reason)}")

    def _record_unrecorded_failure(
        self, method_name: str, args: tuple[Any, ...], exc: Exception, steps_before: int
    ) -> None:
        """Record a failure that escaped before the method recorded its own step."""
        if len(self.steps) > steps_before:
            return  # the method already recorded the failed step
        value = args[0] if args and isinstance(args[0], str) else None
        self._record_step(
            method_name,
            f"{method_name} step failed",
            locator=value,
            take_screenshot=True,
            error=str(exc)[:300],
            fast_fail=True,
        )

    def _off_course_of(self, step: dict[str, Any]) -> dict[str, str] | None:
        """The page a failed step did not reach, when the failure names one."""
        result = step.get("result") or {}
        mismatch = result.get("page_mismatch")
        if isinstance(mismatch, dict) and mismatch.get("expected") and mismatch.get("actual"):
            return {"expected": str(mismatch["expected"]), "actual": str(mismatch["actual"])}
        navigation = result.get("navigation")
        if isinstance(navigation, dict):
            requested = str(navigation.get("requested") or "")
            final = str(navigation.get("final") or "")
            if requested and final and requested != final:
                return {"expected": requested, "actual": final}
        return None

    def _mark_off_course_steps(self) -> dict[str, Any] | None:
        """Stamp every step AFTER the first failure as off course.

        A pass that happens after the journey left its course is never a clean
        pass. The stamp names the step that failed first (``failed_step``) and,
        when the failure names one, the page that was expected and the page the
        later steps really ran on. A missing element names no page, and the
        marking does not need to know what failed - the step number is enough
        (t-1063). Idempotent: safe on every record and on the final write.
        """
        first_failed = next((s for s in self.steps if (s.get("result") or {}).get("status") == "failed"), None)
        if first_failed is None:
            return None
        failed_index = self.steps.index(first_failed)
        info: dict[str, Any] = {"failed_step": failed_index + 1}
        info.update(self._off_course_of(first_failed) or {})
        for step in self.steps[failed_index + 1 :]:
            result = step.setdefault("result", {})
            result.setdefault("off_course", dict(info))
        return info

    def journey_failures(self) -> list[dict[str, Any]]:
        """Return one entry per failed step, in order (empty when none failed)."""
        failures: list[dict[str, Any]] = []
        for index, step in enumerate(self.steps):
            result = step.get("result") or {}
            if result.get("status") != "failed":
                continue
            failures.append(
                {
                    "step": index + 1,
                    "type": step.get("type", ""),
                    "label": step.get("label", ""),
                    "error": result.get("error") or result.get("failure_note") or "",
                    "page": self._off_course_of(step),
                }
            )
        return failures

    def journey_record(self) -> dict[str, Any]:
        """The journey failure as data, for the evidence sidecar and the report.

        Empty when no step failed, so a clean test carries no journey block. The
        report renders one line per failed step (step number, expected page,
        reached page) and the off-course note from these fields - it does not have
        to re-derive them from the steps (t-1063).
        """
        failures = self.journey_failures()
        if not failures and self.stop is None:
            return {}
        first = failures[0] if failures else None
        if first is None:
            return {
                "protocol": JOURNEY_PROTOCOL,
                "failed_steps": [],
                "off_course": {},
                "later_steps": 0,
                "later_passed_off_course": 0,
                "stop": dict(self.stop or {}),
                "stop_text": STOP_REASONS.get(str((self.stop or {}).get("reason", "")), ""),
                "summary": self.journey_summary(),
            }
        failed_index = int(first["step"]) - 1
        later = self.steps[failed_index + 1 :]
        later_passed = sum(1 for step in later if (step.get("result") or {}).get("status") == "passed")
        off_course = self._off_course_of(self.steps[failed_index]) or {}
        return {
            "protocol": JOURNEY_PROTOCOL,
            "failed_steps": failures,
            "off_course": off_course,
            "later_steps": len(later),
            # Every later step ran after a failure, so every later pass is off
            # course - whether or not the failure named a page (t-1063).
            "later_passed_off_course": later_passed,
            "stop": dict(self.stop) if self.stop else {},
            "stop_text": STOP_REASONS.get(str((self.stop or {}).get("reason", "")), ""),
            "summary": self.journey_summary(),
        }

    def journey_summary(self) -> str:
        """One paragraph for the end of the test: what failed, and what came after.

        Empty when no step failed. The generated conftest fails the test with this
        text once, at the end, instead of the journey stopping at the failed step.
        """
        failures = self.journey_failures()
        stop_line = self._stop_line()
        if not failures:
            return stop_line
        first = failures[0]
        failed_index = int(first["step"]) - 1
        later = self.steps[failed_index + 1 :]
        later_passed = sum(1 for step in later if (step.get("result") or {}).get("status") == "passed")
        if self.stop:
            first_line = (
                f"{len(failures)} step(s) failed, then the journey stopped ({len(later)} later step(s) had run)."
            )
        else:
            first_line = (
                f"{len(failures)} step(s) failed; the journey carried on to the end ({len(later)} later step(s) ran)."
            )
        lines = [
            first_line,
            "",
            f"Step {first['step']} '{first['label']}' failed:",
        ]
        if first["error"]:
            lines.append(f"  {first['error']}")
        if first["page"]:
            lines.append(f"  expected: {first['page']['expected']}")
            lines.append(f"  reached:  {first['page']['actual']}")
            lines.append("")
            lines.append(
                f"Later steps ran on the page the journey did not expect "
                f"('{first['page']['actual']}'): {len(later)} ran, {later_passed} passed. "
                "None of those passes is a clean pass."
            )
        for failure in failures[1:]:
            lines.append(f"Also failed: step {failure['step']} '{failure['label']}' - {failure['error']}")
        if stop_line:
            lines.extend(["", stop_line])
        return "\n".join(lines)

    def _stop_line(self) -> str:
        """The stop, in plain words, for the record and the report."""
        if not self.stop:
            return ""
        text = STOP_REASONS.get(str(self.stop.get("reason", "")), "")
        detail = str(self.stop.get("detail") or "")
        line = f"Journey stopped: {text}."
        if detail and detail not in text:
            line += f" {detail}"
        return line

    def record_page_expectation(
        self,
        expected_url: str,
        *,
        observed_url: str = "",
        trail_step: str = "",
        producer: str = "",
        description: str = "",
        reason: str = "",
        query_rule: str = "",
        query_reason: str = "",
    ) -> None:
        """Record what page the test expects before the arrival assertion runs.

        t-0929 (owner's decision, 2026-10-25): when the run observed the browser
        on a different page than the assertion's candidate, the emitted test
        FAILS honestly instead of rewriting the expectation. This record keeps
        the failure provable and readable:

        - ``timestamp``: when this step was evaluated at run time;
        - ``trail_step``: the observed step the candidate was checked against
          (index/action/description/from/to/timestamp) - emit-time knowledge
          that otherwise existed only in memory;
        - ``producer``: which source chose the candidate (keyword resolver,
          post-login override, or flow memory) - previously a log line only;
        - ``query_rule``: which page-identity rule applied (``identity`` by
          default, or ``story-pins-query`` when the story named the bit after
          the ``?`` - see ``src/page_identity.py``);
        - ``query_reason``: why that rule fired or did not fire;
        - ``actual_url``: what the browser was on when the expectation ran.
        """
        entry: dict[str, Any] = {
            "timestamp": round(time.time(), 3),
            "expected_url": expected_url,
            "observed_url": observed_url,
            "actual_url": self._safe_page_url(),
            "trail_step": trail_step,
            "producer": producer,
            "description": description,
        }
        if reason:
            entry["reason"] = reason
        if query_rule:
            entry["query_rule"] = query_rule
        if query_reason:
            entry["query_reason"] = query_reason
        self.page_expectations.append(entry)
        # Persist immediately: the assertion fails on the next line, and a
        # later write() must never be the only place the record exists.
        self._persist_sidecar("running")

    def _persist_sidecar(self, status: str) -> None:
        """Write the current steps + run history to the sidecar JSON.

        Called incrementally by ``_record_step`` (B-035) and finally by
        ``write()`` with the definitive status.
        """
        try:
            json_content = EvidenceSerializer.serialize(
                test_name=self.test_name,
                condition_ref=self.condition_ref,
                story_ref=self.story_ref,
                status=status,
                page_url=self._safe_page_url(),
                run_history=self.run_history,
                steps=self.steps,
                page_expectations=self.page_expectations,
                duration_s=time.time() - self.start_time,
                verification=self.verification,
                journey=self.journey_record(),
            )
            self.sidecar_path.write_text(json_content, encoding="utf-8")
        except Exception as exc:
            logger.warning("incremental evidence persistence failed: %s", exc)

    @_carries_on
    def navigate(self, url: str, label: str = "", expected_page: str = "") -> None:
        """Navigate to a URL and record the navigation.

        Args:
            url: The URL to navigate to.
            label: Optional human-readable label for the step. Defaults to
                   "Navigate to <url>" when empty.
            expected_page: The page this step is supposed to reach, when the
                   caller knows it. When it is given and the browser ends up
                   somewhere else, the step is recorded as failed and names
                   both pages. Empty means "the caller did not say" - a
                   redirect is then recorded (``navigation`` on the step) but
                   not judged; see the note below.

        d-0032: a navigation step used to pass on "no exception raised", and
        Playwright raises only on network, protocol and timeout failures - so a
        404, a 500 or a bounce home was recorded as PASSED with a screenshot of
        the error page. The response is now read:

        - 4xx/5xx -> failed, naming the status, the requested address and the
          address the browser actually reached (``NavigationStatusError``).
        - an ``expected_page`` was given and the browser is not on it -> the
          same failed shape a wrong-page step already uses (``page_mismatch``
          on the step, ``PageMismatchError`` raised).
        - otherwise a redirect to a different address is recorded on the step
          under ``navigation`` with a note naming both addresses, and is not
          judged: a canonical redirect and an auth bounce look the same from
          here, so failing both would be a false red. Say it, do not guess.

        The screenshot and the recorded final address stay on the step either
        way - they are the evidence for what the browser reached.
        """
        if not label:
            label = f"Navigate to {redact_url_credentials(url)}"
        # AI-045 §8.4: never persist basic-auth userinfo (user:pass@host) in
        # the evidence sidecar; navigation itself uses the original URL.
        safe_url = redact_url_credentials(url)
        # B-072: close stray tabs a previous step's new-tab link leaked (headless
        # tab creation can lag past the post-click observation window). The
        # tracker works on ONE page; a second tab is an artifact, not test state.
        try:
            for stray in list(self.page.context.pages):
                if stray is not self.page:
                    stray.close()
        except Exception:
            pass
        _t0 = time.time()
        page_before = self._safe_page_url()
        try:
            response = self.page.goto(url)
            status = _response_status(response)
            final_url = self._safe_page_url()
            # The step now runs on the page it landed on. Keep the tracker's
            # entry URL truthful too, so no later reader sees the page the
            # navigation started from (t-1031).
            self._step_entry_url = final_url
            navigation: dict[str, Any] = {
                "requested": safe_url,
                "final": final_url,
                "status": status,
            }
            if status is not None and status >= 400:
                # An HTTP error page is not arrival. Record the failure with
                # the evidence (screenshot, both addresses) and stop.
                error = f"navigation returned HTTP {status}: asked for '{safe_url}', the browser reached '{final_url}'"
                self._record_step(
                    "navigate",
                    label,
                    value=safe_url,
                    take_screenshot=True,
                    error=error,
                    elapsed_ms=int((time.time() - _t0) * 1000),
                    navigation=navigation,
                    # There is no element to diagnose - the error names the
                    # status and both addresses, so it is its own diagnosis.
                    # The screenshot is still taken (it is the evidence of the
                    # page the browser reached).
                    fast_fail=True,
                )
                raise NavigationStatusError(f"navigate '{label}': {error}")
            chain = _redirect_chain(response)
            if not _same_page(final_url, safe_url):
                # The browser left the address that was asked for. Record both,
                # so the step is never a silent pass - and judge it only when
                # the caller said where it should land.
                navigation["redirected"] = True
                if chain:
                    navigation["redirect_chain"] = chain
                if not expected_page:
                    landed = "no expected page was supplied, so this redirect is recorded, not judged"
                elif _same_page(expected_page, final_url):
                    landed = "that is the expected page"
                else:
                    landed = "that is not the expected page"
                navigation["note"] = f"the browser was redirected from '{safe_url}' to '{final_url}'; {landed}"
            else:
                # t-1049: a redirect the user did not choose must be visible even
                # when it lands on the page that was asked for (a canonical
                # slash, a locale prefix, a session bounce that returns). The
                # page identity says it is the same page, so this is not a
                # failure - but the record says a redirect happened and keeps
                # both addresses, so the user can decide about it.
                if chain or _address_changed(safe_url, final_url):
                    navigation["redirected"] = True
                    if chain:
                        navigation["redirect_chain"] = chain
                    navigation["note"] = (
                        f"the address redirected from '{safe_url}' to '{final_url}'; "
                        "both name the same page, so this is not a failure"
                    )
            self._dismiss_consent_overlays()
            self._dismiss_ad_overlays()
            # Short settle so the evidence shot captures a rendered page, not
            # the mid-load flash (images get their own bounded wait in
            # ``_record_step``).
            self.page.wait_for_timeout(500)
            self._record_step(
                "navigate",
                label,
                value=safe_url,
                take_screenshot=True,
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
                navigation=navigation,
                mismatch_wording="the step was asked for",
            )
            # Rule 3 (t-1095): a navigation's job is to change the page. If the
            # browser is still on the page it left, the remaining steps belong to
            # a page it never reached, so they could only produce noise. A 404 or
            # a redirect DID move the browser, so those carry on.
            # A readable status means a real document navigation was reported.
            # With no status there is nothing to judge (a same-document
            # navigation, or a test double that reports none).
            if status is not None and _address_moved(page_before, self._safe_page_url()) is False:
                if self.stop is None:
                    detail = (
                        f"the navigate step '{label}' did not change the page; "
                        f"the browser stayed on '{self._safe_page_url()}'"
                    )
                    self._fail_stopped_step(detail)
                    self._mark_off_course_steps()
                    self._stop_journey("no_arrival", detail)
        except JourneyStopped:
            # A stop is not a step failure: the step that tripped it is already
            # recorded. Let it out untouched or the generic handler below would
            # record a second, invented step and the summary would lie (t-1098).
            raise
        except NavigationStatusError:
            # Already recorded with its own evidence - re-raise, do not record
            # the same failure twice.
            raise
        except PageMismatchError:
            # Recorded by the success path of _record_step (B-093) - re-raise.
            raise
        except Exception as e:
            self._record_step(
                "navigate",
                label,
                value=safe_url,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
            raise

    @_carries_on
    def fill(self, locator: str, value: str, label: str = "", expected_page: str = "") -> None:
        # AI-045 §8.4: classify the field BEFORE filling. Sensitive fields get
        # their value replaced by the redaction marker in BOTH evidence
        # channels (sidecar ``value`` + any label that embeds it). Detection
        # must run before the fill attempt: on the failure path the element
        # may be gone from the DOM entirely, and locator-string matching alone
        # is the weaker heuristic.
        sensitive = is_sensitive_field(self.page, locator)
        safe_value = redact_value(value) if sensitive else value
        if not label:
            label = f"Fill {locator} with '{safe_value}'"
        else:
            # An explicitly supplied label may still quote the raw value
            # (e.g. "Fill password with 'hunter2'") — scrub it defensively.
            label = redact_text(label, value) if sensitive else label
        _t0 = time.time()
        self._step_entry_url = self._safe_page_url()
        try:
            # B-045: native <select> elements reject .fill() ("Element is not an
            # <input>, <textarea> or [contenteditable]"). The banking mock is the
            # first golden target with native selects (from/to account, payee);
            # detect the tag and route to .select_option() so the generated test
            # passes instead of erroring at runtime.
            tag = self._locator_tag(locator)
            if tag == "select":
                self._select_option(locator, value)
            else:
                self.page.locator(locator).fill(value)
            self._record_step(
                "fill",
                label,
                locator=locator,
                value=safe_value,
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
        except Exception as e:
            # A page-mismatch failure was already recorded by the success
            # path of _record_step — re-raise without re-recording (B-093).
            if isinstance(e, PageMismatchError):
                raise
            self._record_step(
                "fill",
                label,
                locator=locator,
                value=safe_value,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
            raise

    def _select_option(self, locator: str, value: str) -> None:
        """Select an option on a native <select>, robust to value/label mismatch.

        LLM fill values are nondeterministic ("Electric Company") and rarely
        equal the option's ``value`` attribute ("electric") or its exact label
        ("City Electric Company"). Try, in order:
          1. exact option value
          2. exact option label
          3. first option whose label CONTAINS the requested value
             (case-insensitive) — the closest real-world match.
        """
        locator_obj = self.page.locator(locator)
        try:
            locator_obj.select_option(value)
            return
        except Exception:
            pass
        try:
            locator_obj.select_option(label=value)
            return
        except Exception:
            pass
        # Substring match over option labels via evaluate (returns the value).
        needle = value.strip().lower()
        matched_value = locator_obj.evaluate(
            """(sel, needle) => {
                const opts = Array.from(sel.options);
                const hit = opts.find(o => o.text.toLowerCase().includes(needle));
                return hit ? hit.value : null;
            }""",
            needle,
        )
        if matched_value is None:
            # Surface the real error from the first attempt.
            locator_obj.select_option(value)
        locator_obj.select_option(matched_value)

    def _locator_tag(self, locator: str) -> str:
        """Return the resolved element's tag name for a locator, or empty.

        Uses Playwright's own engine to inspect the first matching element —
        cheap, and avoids a CSS tag parse that would misread compound
        selectors. Empty on any error (locator resolves to nothing yet,
        evaluation fails, etc.) so the caller falls back to plain .fill().
        """
        try:
            return str(self.page.locator(locator).evaluate("el => el.tagName").lower())
        except Exception:
            return ""

    @_carries_on
    def click(self, locator: str, label: str = "", expected_page: str = "", must_move: bool = False) -> None:
        """Click an element, with layered fallback strategies.

        Strategy (Tier 2 — Locator Scoring + Controlled Fallback):
        1. Scroll into view
        2. Try direct click with primary locator
        3. If click fails with visibility/timeout error:
           a. Try hover-reveal fallback (hover_click_utils)
           b. Try locator scoring fallback (new — higher-scoring alternatives)
        4. If any fallback succeeds, mark step as "partial_pass" with audit trail
        """
        if not label:
            label = f"Click {locator}"
        _t0 = time.time()
        self._step_entry_url = self._safe_page_url()
        try:
            # Always click `first` to avoid strict-mode failures when a locator is
            # valid but matches multiple elements (common on e-commerce grids).
            loc = self.page.locator(locator).first
            # Fast-fail FIRST (before metadata capture, which waits ~5s per
            # Playwright call on a missing element): if the element does not exist
            # on the CURRENT page, do not run the fallback marathon — it builds
            # candidates from the same DOM and cannot recover a non-existent
            # element. A wrong-page locator previously burned 5s + hover +
            # scoring fallbacks (~150s per click), blowing the whole suite's
            # 600s budget on a single step.
            try:
                if loc.count() == 0:
                    raise _LocatorNotFoundError(
                        f"Locator '{locator}' not found on current page ({self.page.url}). "
                        "The element exists on a different page than the one this step runs on."
                    )
                if not loc.is_visible():
                    # Modal-close targets: the tracker auto-dismisses
                    # confirmation modals before every click, so a generated
                    # "close popup / OK" step may find its button already
                    # hidden. The click's intent (dismiss the modal) is then
                    # already satisfied — record a no-op instead of failing.
                    if self._is_modal_close_target(locator):
                        self._record_step(
                            "click",
                            label,
                            locator=locator,
                            elapsed_ms=int((time.time() - _t0) * 1000),
                            element_metadata={"note": "modal already dismissed — no-op"},
                            expected_page=expected_page,
                        )
                        return
                    raise _LocatorNotFoundError(
                        f"Locator '{locator}' is hidden on current page ({self.page.url}). "
                        "Hidden elements are not clickable — the resolver emitted a "
                        "non-interactive element (e.g. a hidden CSRF input)."
                    )
            except _LocatorNotFoundError:
                self._record_step(
                    "click",
                    label,
                    locator=locator,
                    take_screenshot=True,  # B-033: failed steps always carry a screenshot
                    error=str(sys.exc_info()[1]),
                    elapsed_ms=int((time.time() - _t0) * 1000),
                    fast_fail=True,
                    expected_page=expected_page,
                )
                raise
            # Proactively dismiss consent/ad overlays AND confirmation modals
            # BEFORE the click attempt. Google's consent banner, ad
            # interstitials and e-commerce "added to cart" modals re-render
            # after the initial navigate() dismissal; without this, Playwright
            # waits the full 5s timeout per click and then falls into the
            # hover/scoring fallback chain (~8-30s per click on covered
            # elements). Dismissal costs ~1.5s and makes the click succeed on
            # the first try.
            self._dismiss_ad_overlays()
            self._dismiss_confirmation_modals()
            # B-029: capture the URL BEFORE any click so a swallowed link click
            # (ad/consent overlay intercepting the navigation) is detectable.
            original_url = self._safe_page_url()
            # B-072: the pages already open BEFORE the click — a page appearing
            # after the click means the link opened a NEW tab (target="_blank"),
            # which the original page's URL check can never see.
            try:
                pages_before: tuple[Page, ...] = tuple(self.page.context.pages)
            except Exception:
                pages_before = ()
            # We record metadata BEFORE clicking in case navigation clears it
            el_metadata = self._get_element_metadata(locator)
            try:
                loc.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                # Scrolling is best-effort; clicking may still succeed without it.
                pass

            # Attempt 1: Direct click
            try:
                loc.click(timeout=5000)
                # Clicks capture evidence on success too — without it, a
                # passing click step (especially one that navigates, e.g.
                # "Proceed To Checkout") leaves no trace in the run evidence.
                self._record_step(
                    "click",
                    label,
                    locator=locator,
                    take_screenshot=True,
                    elapsed_ms=int((time.time() - _t0) * 1000),
                    element_metadata=el_metadata,
                    expected_page=expected_page,
                )
                self._verify_click_navigation(locator, label, el_metadata, original_url, pages_before)
                # Rule 3 (t-1095): only a click the emitter KNOWS must move arms
                # this. A click the story does not expect to navigate (a tab, an
                # "add to cart") must never stop the journey.
                if must_move and self.stop is None and not self._click_moved(original_url, pages_before):
                    detail = (
                        f"the click step '{label}' (via '{locator}') was expected to move the browser; "
                        f"it stayed on '{self._safe_page_url()}'"
                    )
                    self._fail_stopped_step(detail)
                    self._mark_off_course_steps()
                    self._stop_journey("no_arrival", detail)
                return
            except Exception as click_error:
                # Check if this looks like a visibility/overlay issue
                error_str = str(click_error).lower()
                is_visibility_issue = any(
                    term in error_str
                    for term in ["timeout", "visible", "attached", "detached", "hidden", "not visible", "not enabled"]
                )

                if is_visibility_issue:
                    # First, try to dismiss any ad overlays that might be blocking
                    self._dismiss_ad_overlays()
                    self.page.wait_for_timeout(300)

                    # Attempt 2: Hover-reveal fallback (delegated to hover_click_utils)
                    if try_hover_and_click(self.page, loc, locator):
                        self._record_step(
                            "click",
                            label,
                            locator=locator,
                            take_screenshot=True,
                            elapsed_ms=int((time.time() - _t0) * 1000),
                            element_metadata=el_metadata,
                            expected_page=expected_page,
                        )
                        self._verify_click_navigation(locator, label, el_metadata, original_url, pages_before)
                        return

                    # Attempt 3: Locator scoring fallback (new — Tier 2)
                    LocatorFallback.try_fallback(
                        loc,
                        locator,
                        label,
                        el_metadata,
                        click_error,
                        self.page,
                        self._record_step,
                        elapsed_ms=int((time.time() - _t0) * 1000),
                    )
                    # try_fallback records the step internally; verify it actually
                    # navigated (B-029) and amend to a failure if it did not.
                    self._verify_click_navigation(locator, label, el_metadata, original_url, pages_before)
                else:
                    raise
        except JourneyStopped:
            # The step that tripped rule 3 is already recorded; a second invented
            # step here would double-count it (t-1098).
            raise
        except Exception as e:
            # Fast-failed not-found clicks were already recorded (fast_fail).
            # A page-mismatch failure was already recorded by the success
            # path of _record_step (B-093). Re-raise without re-recording.
            if isinstance(e, (_LocatorNotFoundError, PageMismatchError)):
                raise
            # Always screenshot on click failure; this is the single most useful
            # artifact for evidence viewer + heatmaps.
            self._record_step(
                "click",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
            raise

    # ── B-029: post-click navigation verification ────────────────────────────

    def _verify_click_navigation(
        self,
        locator: str,
        label: str,
        el_metadata: dict[str, Any],
        original_url: str,
        pages_before: tuple[Page, ...] = (),
    ) -> None:
        """Ensure a "successful" click on a link actually navigated.

        Google's ad stack (FreeCmp consent dialog, ``#google_vignette``) can
        swallow link clicks: Playwright reports the click as successful (even
        the JS ``el.click()`` fallback returns without raising) but the URL
        never changes. The step is then recorded "passed" and the *next* step
        fails with a misleading "element on a different page" error (B-029).

        When a link click does not navigate, dismiss overlays and retry once.
        If it still does not navigate, amend the recorded step to a failure
        instead of leaving a false pass.

        B-072: ``target="_blank"`` links open a NEW tab, so the original page's
        URL never changes even on a healthy click. ``pages_before`` is the
        context's page list captured before the click; a new entry after the
        click means the navigation happened in the new tab — that is a
        verified success, not a swallowed click.
        """
        href = str(el_metadata.get("href") or "").strip()
        is_nav_link = bool(href) and not href.startswith(("#", "javascript:", "mailto:", "tel:"))
        if is_nav_link:
            try:
                target = urljoin(original_url, href)
                if (
                    urlparse(target).path == urlparse(original_url).path
                    and urlparse(target).netloc == urlparse(original_url).netloc
                ):
                    is_nav_link = False  # same-page link (anchor / hash navigation)
            except Exception:
                is_nav_link = False

        # B-072: wait for EITHER a same-tab URL change OR a new tab. A new
        # tab appearing is always a successful navigation — even for
        # javascript:/no-href elements (window.open links). The new page
        # arrives via the CDP connection a moment after the click, so a
        # single immediate check races the event: poll for both.
        #
        # The wait is only worth it when the element CAN open a tab (real
        # link, target="_blank", or javascript: onclick). Plain #anchor / mailto:
        # / tel: clicks return immediately — no 2.5s tax per step (A5).
        can_open_tab = is_nav_link or str(el_metadata.get("target") or "") == "_blank" or href.startswith("javascript:")
        if not can_open_tab:
            return  # plain same-page/mailto/tel link — nothing to verify

        if not is_nav_link:
            # B-072: window.open-style links have no retry path — give them one
            # long observation window. Headless tab creation can lag many
            # seconds (measured ~8s on this machine's headless Chromium 151).
            outcome = self._wait_for_navigation(original_url, pages_before, timeout=10.0)
            if outcome != "none":
                if outcome == "url":
                    return
                self._record_new_tab_navigation(cast("Page", outcome), label, el_metadata, original_url)
                return
            return  # opened nothing observable — the click itself worked

        outcome = self._wait_for_navigation(original_url, pages_before, timeout=2.5)
        if outcome == "url":
            return
        if outcome != "none":
            # B-072: a new tab appeared — the navigation went there. Duck-typed
            # on purpose (B-029 stub pages are not real Page instances).
            self._record_new_tab_navigation(cast("Page", outcome), label, el_metadata, original_url)
            return

        # Click succeeded but no navigation — likely swallowed by an overlay.
        # Dismiss and retry once before declaring failure.
        self._dismiss_ad_overlays()
        self._dismiss_confirmation_modals()
        try:
            self.page.locator(locator).first.click(timeout=5000)
        except Exception:
            pass
        # B-072: longer second window — headless new-tab creation can lag ~8s
        # (measured), so the short first window is not enough to rule out a
        # slow tab before declaring the click swallowed.
        outcome = self._wait_for_navigation(original_url, pages_before, timeout=7.5)
        if outcome == "url":
            return
        if outcome != "none":
            self._record_new_tab_navigation(cast("Page", outcome), label, el_metadata, original_url)
            return

        # Still no navigation — amend the recorded step to a truthful failure.
        if str(el_metadata.get("target") or "") == "_blank":
            # B-072: headless Chromium drops new-tab navigation from trusted
            # anchor clicks — no tab appears at all, so there is nothing to
            # wait for. This is an environment limit, not an overlay swallow:
            # the actionable fix is to check the href without clicking.
            detail = (
                'The link has target="_blank" and no new tab appeared — headless '
                "Chromium drops new-tab navigation from anchor clicks, so this "
                "criterion cannot be click-verified in a headless run. Check the "
                "link's href instead of clicking it."
            )
        else:
            detail = "The click was likely swallowed by an overlay even after dismissal + retry."
        self._amend_last_click_to_failure(label, locator, original_url, detail)
        raise _LocatorNotFoundError(
            f"Click '{label}' succeeded but the page did not navigate (still on {original_url}). {detail}"
        )

    def _find_new_tab(self, pages_before: tuple[Page, ...]) -> Page | None:
        """B-072: return the most recent page opened after the click, if any."""
        try:
            current = list(self.page.context.pages)
        except Exception:
            return None
        prior = set(pages_before)
        new_tabs = [p for p in current if p not in prior]
        return new_tabs[-1] if new_tabs else None

    def _wait_for_navigation(
        self,
        original_url: str,
        pages_before: tuple[Page, ...],
        timeout: float,
    ) -> str | Page:
        """B-072: poll up to *timeout* seconds for a navigation event.

        Returns ``"url"`` when the original page navigated, the new ``Page``
        when a new tab appeared, or ``"none"`` when neither happened in the
        window.
        """
        deadline = time.time() + timeout
        while True:
            try:
                if self.page.url != original_url:
                    return "url"
            except Exception:
                return "url"  # page closed/navigated away — treat as navigated
            new_tab = self._find_new_tab(pages_before)
            if new_tab is not None:
                return new_tab
            if time.time() >= deadline:
                return "none"
            time.sleep(0.15)

    def _record_new_tab_navigation(
        self,
        new_tab: Page,
        label: str,
        el_metadata: dict[str, Any],
        original_url: str,
    ) -> None:
        """B-072: the click opened a new tab — the navigation went there.

        Wait for the new tab to load, record its final URL on the click step
        (plus whether it matches the link's href), then close the tab so the
        suite continues on the original page without leaking tabs. A
        target="_blank" link that opens NO tab still falls through to the
        swallowed-click failure path.
        """
        try:
            new_tab.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        new_url = new_tab.url
        href = str(el_metadata.get("href") or "").strip()
        matched: bool | None = None  # None = no href to compare against (window.open)
        if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
            try:
                target = urljoin(original_url, href)
                a, b = urlparse(target), urlparse(new_url)
                matched = (
                    a.scheme in ("http", "https")
                    and a.netloc.lower() == b.netloc.lower()
                    and a.path.rstrip("/") == b.path.rstrip("/")
                )
            except Exception:
                matched = False
        if self.steps and self.steps[-1].get("type") == "click":
            element = self.steps[-1].get("element")
            if isinstance(element, dict):
                element["new_tab"] = {"url": new_url, "matched_href": matched}
        try:
            new_tab.close()
        except Exception:
            pass

    def _url_changed(self, original_url: str, timeout: float) -> bool:
        """Poll for a URL change within *timeout* seconds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.page.url != original_url:
                    return True
            except Exception:
                return True
            time.sleep(0.15)
        return False

    def _amend_last_click_to_failure(
        self, label: str, locator: str, original_url: str, detail: str | None = None
    ) -> None:
        """Flip the last recorded passed/partial click step to a truthful failure."""
        if not self.steps:
            return
        last = self.steps[-1]
        result = last.get("result", {})
        if last.get("type") != "click" or result.get("status") not in ("passed", "partial_pass"):
            return
        if detail is None:
            detail = "Overlay swallow suspected — the click was consumed by an ad/consent overlay."
        error = f"Click recorded passed but the page did not navigate (stayed on {original_url}). {detail}"
        result["status"] = "failed"
        result["error"] = error
        result["failure_note"] = error
        self._persist_sidecar("running")

    @_carries_on
    def assert_visible(self, locator: str, label: str = "", expected_page: str = "") -> None:
        if not label:
            label = f"Assert visible: {locator}"
        _t0 = time.time()
        self._step_entry_url = self._safe_page_url()
        try:
            # Use `first` to avoid strict-mode violations when multiple elements
            # match (common with overlays/duplicate buttons in e-commerce UIs).
            loc = self.page.locator(locator).first
            loc.wait_for(state="visible", timeout=5000)
            matched_text = loc.text_content()
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=matched_text,
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
        except Exception as e:
            # A page-mismatch failure was already recorded by the success
            # path of _record_step — re-raise without re-recording (B-093).
            if isinstance(e, PageMismatchError):
                raise
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
            raise

    # --- B-020: Additional assertion methods ---

    @_carries_on
    def assert_hidden(self, locator: str, label: str = "", expected_page: str = "") -> None:
        """Assert the element is hidden or detached — a state-ABSENCE check.

        For polarity ASSERTs like "popup closed" / "item removed": Playwright's
        ``wait_for(state="hidden")`` passes for hidden OR detached nodes, which
        is exactly the "this is gone" semantics.
        """
        if not label:
            label = f"Assert hidden: {locator}"
        _t0 = time.time()
        self._step_entry_url = self._safe_page_url()
        try:
            self.page.locator(locator).first.wait_for(state="hidden", timeout=5000)
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=None,
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
        except Exception as e:
            # A page-mismatch failure was already recorded by the success
            # path of _record_step — re-raise without re-recording (B-093).
            if isinstance(e, PageMismatchError):
                raise
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
                expected_page=expected_page,
            )
            raise

    @_carries_on
    def assert_text(self, locator: str, expected: str, label: str = "") -> None:
        """Assert the element's text content matches the expected string exactly."""
        if not label:
            label = f"Assert text: {expected}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="visible", timeout=5000)
            actual = (loc.text_content() or "").strip()
            if actual != expected:
                raise AssertionError(f"Expected text '{expected}' but got '{actual}'")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=actual,
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_text_contains(self, locator: str, expected: str, label: str = "") -> None:
        """Assert the element's text content contains the expected substring."""
        if not label:
            label = f"Assert text contains: {expected}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="visible", timeout=5000)
            actual = (loc.text_content() or "").strip()
            if expected not in actual:
                raise AssertionError(f"Text '{actual}' does not contain '{expected}'")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=actual,
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_disabled(self, locator: str, label: str = "") -> None:
        """Assert the element is disabled."""
        if not label:
            label = f"Assert disabled: {locator}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="attached", timeout=5000)
            if loc.is_enabled():
                raise AssertionError(f"Element {locator} is enabled but expected disabled")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_enabled(self, locator: str, label: str = "") -> None:
        """Assert the element is enabled."""
        if not label:
            label = f"Assert enabled: {locator}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="visible", timeout=5000)
            if not loc.is_enabled():
                raise AssertionError(f"Element {locator} is disabled but expected enabled")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_checked(self, locator: str, label: str = "") -> None:
        """Assert a checkbox or radio button is checked."""
        if not label:
            label = f"Assert checked: {locator}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="attached", timeout=5000)
            if not loc.is_checked():
                raise AssertionError(f"Element {locator} is not checked")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_count(self, locator: str, expected: int, label: str = "") -> None:
        """Assert the number of elements matching the locator equals expected."""
        if not label:
            label = f"Assert count: {expected}"
        _t0 = time.time()
        try:
            actual = self.page.locator(locator).count()
            if actual != expected:
                raise AssertionError(f"Expected {expected} elements but found {actual}")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=str(actual),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_count_at_least(self, locator: str, minimum: int, label: str = "") -> None:
        """Assert at least ``minimum`` elements match the locator (B-090).

        A criterion like "shows at least four capability cards" must count the
        matching elements, not assert one element's visibility. ``assert_count``
        is an exact check; this is the lower-bound variant the criterion asks
        for. Zero matches always fails.
        """
        if not label:
            label = f"Assert count >= {minimum}"
        _t0 = time.time()
        try:
            actual = self.page.locator(locator).count()
            if actual < minimum:
                raise AssertionError(f"Expected at least {minimum} elements but found {actual}")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=f"{actual} element(s) (>= {minimum})",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_value(self, locator: str, expected: str, label: str = "") -> None:
        """Assert an input/textarea/select has the expected value attribute."""
        if not label:
            label = f"Assert value: {expected}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="visible", timeout=5000)
            actual = loc.get_attribute("value") or ""
            if actual != expected:
                raise AssertionError(f"Expected value '{expected}' but got '{actual}'")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=actual,
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @staticmethod
    def _attribute_violations(
        value: str,
        *,
        forbidden: tuple[str, ...] = (),
        must_be_url: bool = False,
        required_scheme: str = "",
    ) -> list[str]:
        """B-069 part b: predicate violations for an attribute value.

        A value violates the condition when it contains any forbidden
        substring (case-insensitive), when ``must_be_url`` and it is not an
        http(s) URL, or when ``required_scheme`` (B-087) and it does not start
        with that scheme (``mailto:`` / ``tel:``).
        """
        violations: list[str] = []
        lowered = value.lower()
        for token in forbidden:
            if token in lowered:
                violations.append(f"contains forbidden '{token}'")
        if must_be_url and not lowered.startswith(("http://", "https://")):
            violations.append("is not an http(s) URL")
        if required_scheme and not lowered.startswith(required_scheme.lower()):
            violations.append(f"does not start with '{required_scheme}'")
        return violations

    @_carries_on
    def assert_attribute(
        self,
        locator: str,
        attribute: str,
        label: str = "",
        *,
        forbidden: tuple[str, ...] = (),
        must_be_url: bool = False,
        required_scheme: str = "",
    ) -> None:
        """Assert an element's attribute is present and non-empty (B-069 part b).

        When ``forbidden`` is given, the value must not contain any of those
        substrings (case-insensitive) — a "live" href that still says ``TBD``
        or ``YOUR_VIDEO_ID_HERE`` fails instead of passing. When
        ``must_be_url`` is given, the value must be an http(s) URL. When
        ``required_scheme`` is given (B-087), the value must start with it —
        ``mailto:`` / ``tel:``.
        """
        if not label:
            label = f"Assert attribute {attribute}: {locator}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="attached", timeout=5000)
            actual = loc.get_attribute(attribute) or ""
            if not actual:
                raise AssertionError(f"Expected non-empty attribute '{attribute}' on {locator} but got empty")
            violations = self._attribute_violations(
                actual, forbidden=forbidden, must_be_url=must_be_url, required_scheme=required_scheme
            )
            if violations:
                raise AssertionError(
                    f"Attribute '{attribute}' on {locator} violates the condition: "
                    f"{'; '.join(violations)} (value={actual!r})"
                )
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=f"{attribute}={actual}",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_no_forbidden(
        self,
        selector: str,
        forbidden: str | tuple[str, ...],
        label: str = "",
        attribute: str | None = None,
        *,
        also_text: bool = False,
    ) -> None:
        """Assert NO element matching ``selector`` contains ``forbidden`` (B-069 part b).

        Page-level integrity check that needs no element resolution —
        "no TBD in links" inspects every ``<a>`` href, "no TBD in buttons"
        inspects every button's text. Case-insensitive. Zero matching
        elements passes vacuously (the condition holds trivially) and the
        count is recorded for the evidence.

        B-088: ``forbidden`` may be several tokens at once ("no link, button or
        heading anywhere contains placeholder text") and ``also_text`` widens an
        attribute scan to the element's text too ("appear in no href and in no
        visible copy").
        """
        tokens = (forbidden,) if isinstance(forbidden, str) else tuple(forbidden)
        tokens = tuple(token for token in tokens if token)
        if not label:
            label = f"No {', '.join(tokens)} in {selector}"
        _t0 = time.time()
        try:
            loc = self.page.locator(selector)
            count = loc.count()
            offenders: list[str] = []
            for i in range(count):
                element = loc.nth(i)
                values: list[str] = []
                if attribute:
                    raw = element.get_attribute(attribute)
                    if raw:
                        values.append(raw.strip())
                    if also_text:
                        text = (element.text_content() or "").strip()
                        if text:
                            values.append(text)
                else:
                    text = (element.text_content() or "").strip()
                    if text:
                        values.append(text)
                for value in values:
                    lowered = value.lower()
                    if any(token.lower() in lowered for token in tokens):
                        offenders.append(value[:80])
                        break
            if offenders:
                raise AssertionError(
                    f"Found {len(offenders)} element(s) matching {selector} containing one of {tokens}: {offenders[:3]}"
                )
            self._record_step(
                "assertion",
                label,
                locator=selector,
                take_screenshot=True,
                matched_text=f"{count} element(s), none contain {tokens}",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=selector,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_attribute_all(
        self,
        selector: str,
        attribute: str,
        label: str = "",
        *,
        forbidden: tuple[str, ...] = (),
        must_be_url: bool = False,
    ) -> None:
        """Assert EVERY element matching ``selector`` has a non-empty ``attribute`` (B-069 part b).

        "all images have alt" → every ``<img>`` must carry a non-empty alt.
        Zero matching elements FAILS — the condition expects the elements to
        exist. ``forbidden`` / ``must_be_url`` apply the same predicates as
        :meth:`assert_attribute` to every value.
        """
        if not label:
            label = f"All {selector} have {attribute}"
        _t0 = time.time()
        try:
            loc = self.page.locator(selector)
            count = loc.count()
            if count == 0:
                raise AssertionError(f"Expected elements matching {selector} but found none")
            bad: list[str] = []
            for i in range(count):
                element = loc.nth(i)
                value = element.get_attribute(attribute) or ""
                if not value:
                    bad.append(f"#{i}: empty")
                    continue
                violations = self._attribute_violations(value, forbidden=forbidden, must_be_url=must_be_url)
                if violations:
                    bad.append(f"#{i}: {'; '.join(violations)}")
            if bad:
                raise AssertionError(
                    f"{len(bad)}/{count} element(s) matching {selector} fail attribute '{attribute}': {bad[:3]}"
                )
            self._record_step(
                "assertion",
                label,
                locator=selector,
                take_screenshot=True,
                matched_text=f"{count} element(s), all have non-empty '{attribute}'",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=selector,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_contains(self, section: str, child: str, label: str = "") -> None:
        """Assert a named section contains a child element (B-088).

        ``section`` is the section heading's text and ``child`` is a CSS
        selector. The check finds the innermost element that has a heading with
        that text AND contains a matching child — so a contact link elsewhere on
        the page cannot satisfy it. Fails when no such container exists.
        """
        if not label:
            label = f"{child} inside {section}"
        _t0 = time.time()
        heading_selector = f":is(h1,h2,h3,h4,h5,h6):has-text({section!r})"
        try:
            heading = self.page.locator(heading_selector).first
            heading.wait_for(state="attached", timeout=5000)
            container = (
                self.page.locator("div, section, article, li")
                .filter(has=self.page.locator(heading_selector))
                .filter(has=self.page.locator(child))
                .last
            )
            if container.count() == 0:
                raise AssertionError(f"No element containing heading {section!r} also contains {child!r}")
            self._record_step(
                "assertion",
                label,
                locator=child,
                take_screenshot=True,
                matched_text=f"{child} found inside section {section!r}",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=child,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_no_broken_images(self, label: str = "") -> None:
        """Assert every ``<img>`` on the page finished loading (B-090).

        A page-fact criterion ("no image on the page is broken — every image
        element has a non-zero natural width") must inspect every image, not
        assert one hero div's visibility. Waits (bounded, 4s) for in-flight
        images so a slow load is not a false failure, then fails listing the
        broken sources.
        """
        if not label:
            label = "No broken images"
        _t0 = time.time()
        try:
            self.page.evaluate(
                """() => Promise.race([
                    Promise.all(Array.from(document.images).map(
                        img => img.complete ? Promise.resolve()
                            : new Promise(res => {
                                img.addEventListener('load', res, { once: true });
                                img.addEventListener('error', res, { once: true });
                            })
                    )),
                    new Promise(res => setTimeout(res, 4000)),
                ])"""
            )
            broken = self.page.evaluate(
                """() => Array.from(document.images)
                    .filter(img => !img.complete || img.naturalWidth === 0)
                    .map(img => img.currentSrc || img.src || img.alt || '(unnamed)')"""
            )
            if broken:
                raise AssertionError(f"{len(broken)} broken image(s): {list(broken)[:3]}")
            count = self.page.evaluate("() => document.images.length")
            self._record_step(
                "assertion",
                label,
                locator="img",
                take_screenshot=True,
                matched_text=f"{count} image(s), all loaded",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator="img",
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_natural_width(self, locator: str, label: str = "") -> None:
        """Assert the first element matching ``locator`` is a loaded image (B-090).

        "The hero product screenshot has finished loading (natural width > 0)"
        must read the image's ``naturalWidth``; ``assert_visible`` passes even
        for a broken image icon. Fails when the element is not an image (no
        natural width) or has not loaded.
        """
        if not label:
            label = f"Natural width > 0: {locator}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="visible", timeout=5000)
            width = loc.evaluate("el => el.naturalWidth")
            if not width:
                raise AssertionError(f"Image {locator} is not loaded (naturalWidth={width})")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=f"naturalWidth={width}",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_no_horizontal_scroll(self, width: int = 375, label: str = "") -> None:
        """Assert the page does not scroll horizontally at ``width`` px (B-090).

        "At a viewport width of 375 pixels the page does not scroll
        horizontally" must resize the viewport and measure ``scrollWidth`` — a
        visibility assert checked neither. The original viewport is restored
        afterwards so later steps are unaffected.
        """
        if not label:
            label = f"No horizontal scroll at {width}px"
        _t0 = time.time()
        original = self.page.viewport_size
        try:
            height = int(original["height"]) if original and original.get("height") else 800
            self.page.set_viewport_size({"width": int(width), "height": height})
            metrics = self.page.evaluate(
                "() => ({scrollWidth: document.documentElement.scrollWidth,"
                " clientWidth: document.documentElement.clientWidth})"
            )
            scroll_width = int(metrics["scrollWidth"])
            client_width = int(metrics["clientWidth"])
            if scroll_width > client_width + 1:
                raise AssertionError(
                    f"Page scrolls horizontally at {width}px: scrollWidth={scroll_width} > clientWidth={client_width}"
                )
            self._record_step(
                "assertion",
                label,
                locator="html",
                take_screenshot=True,
                matched_text=f"scrollWidth={scroll_width} <= clientWidth={client_width} @ {width}px",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator="html",
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise
        finally:
            if original:
                try:
                    self.page.set_viewport_size(original)
                except Exception:
                    pass

    @_carries_on
    def assert_anchor_targets_exist(self, selector: str = 'a[href^="#"]', label: str = "") -> None:
        """Assert every in-page anchor points at an element that exists (B-092).

        "Every same-page anchor link points at an element that exists" is a
        page-wide scan, not a check of one link. Anchors with a bare ``#``
        fragment point at the top of the document and are treated as valid;
        external hrefs are ignored (the default selector only matches in-page
        anchors). Fails listing the fragments with no matching element.
        """
        if not label:
            label = "Every same-page anchor target exists"
        _t0 = time.time()
        try:
            missing = self.page.evaluate(
                """(sel) => Array.from(document.querySelectorAll(sel))
                    .map(a => a.getAttribute('href') || '')
                    .filter(h => h.startsWith('#') && h.length > 1)
                    .filter(h => {
                        const id = decodeURIComponent(h.slice(1));
                        return !document.getElementById(id) && !document.querySelector(h);
                    })""",
                selector,
            )
            count = self.page.evaluate("(sel) => document.querySelectorAll(sel).length", selector)
            if missing:
                raise AssertionError(f"{len(missing)} anchor target(s) missing: {list(missing)[:3]}")
            self._record_step(
                "assertion",
                label,
                locator=selector,
                take_screenshot=True,
                matched_text=f"{count} anchor(s), all targets exist",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=selector,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_section_has_price(self, section: str, label: str = "") -> None:
        """Assert a named section shows a price (B-092).

        "The Pro Deployment tier is shown with a price" must find the section
        whose heading names the tier and check it contains a currency amount —
        asserting the heading's visibility never checked a price.
        """
        if not label:
            label = f"{section} shows a price"
        _t0 = time.time()
        heading_selector = f":is(h1,h2,h3,h4,h5,h6):has-text({section!r})"
        price_pattern = re.compile(r"[$\u20ac\u00a3]\s?\d")
        try:
            heading = self.page.locator(heading_selector).first
            heading.wait_for(state="attached", timeout=5000)
            container = (
                self.page.locator("div, section, article, li").filter(has=self.page.locator(heading_selector)).last
            )
            if container.count() == 0:
                raise AssertionError(f"No section containing heading {section!r} found")
            text = container.first.text_content() or ""
            if not price_pattern.search(text):
                raise AssertionError(f"Section {section!r} shows no price (text={text[:120]!r})")
            self._record_step(
                "assertion",
                label,
                locator=heading_selector,
                take_screenshot=True,
                matched_text=f"price found in section {section!r}",
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=heading_selector,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    @_carries_on
    def assert_empty(self, locator: str, label: str = "") -> None:
        """Assert an element has no text and no child elements."""
        if not label:
            label = f"Assert empty: {locator}"
        _t0 = time.time()
        try:
            loc = self.page.locator(locator).first
            loc.wait_for(state="attached", timeout=5000)
            text = (loc.text_content() or "").strip()
            children = loc.locator("* ").count()
            if text or children > 0:
                raise AssertionError(f"Element is not empty: text='{text}', children={children}")
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
        except Exception as e:
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    def write(self, status: str = "passed") -> str:
        """Writes the sidecar and updates history."""
        self._mark_off_course_steps()
        self.run_history["total_runs"] += 1
        if status == "passed":
            self.run_history["passed_runs"] += 1
        else:
            self.run_history["failed_runs"] += 1

        self._persist_sidecar(status)
        return str(self.sidecar_path)
