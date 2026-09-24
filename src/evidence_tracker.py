import logging
import re
import sys
import time
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
from src.evidence_serializer import EvidenceSerializer
from src.failure_reporter import FailureReporter
from src.hover_click_utils import try_hover_and_click
from src.locator_fallback import LocatorFallback
from src.storage import get_storage

logger = logging.getLogger(__name__)


def _same_page(expected: str, actual: str) -> bool:
    """Return True when two URLs address the same page.

    Compares scheme + host + path only, ignoring query and fragment: SPA mocks
    encode state in the query (``success.html?item=blue-top``) and a differing
    query is not evidence of a different page. Trailing slashes are ignored.
    Anything unparseable counts as a match so a parse failure never raises a
    false mismatch.
    """

    if not expected or not actual:
        return True

    def _key(url: str) -> tuple[str, str, str]:
        parsed = urlparse(str(url))
        return (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/")

    try:
        left, right = _key(expected), _key(actual)
    except Exception:
        return True
    # No host on either side means this is not a comparable absolute URL —
    # fail open rather than raising a false mismatch.
    if not left[1] or not right[1]:
        return True
    return left == right


class _LocatorNotFoundError(RuntimeError):
    """Raised when a click target does not exist on the current page.

    The failure is recorded once with ``fast_fail=True`` (no expensive
    metadata/screenshot/diagnosis) and re-raised; the outer handler must
    not re-record it.
    """


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
        self.start_time = time.time()
        # AI-067: the page a step actually RAN on — captured before the action,
        # because a click legitimately navigates away from the page its locator
        # was resolved against. Compared with ``expected_page`` in
        # ``_record_step``.
        self._step_entry_url: str = ""

        # A5: per-page hint for the adaptive encoder. A page URL lands here when
        # a full-page capture on it found lossless WebP would NOT shrink the
        # file, so later captures on the same URL skip the ~330 ms method=0
        # probe that would just lose again. It only ever skips a probe — every
        # stored image stays lossless and pixel-identical (a cache miss or a
        # denser page simply re-probes and may pick WebP).
        self._encode_png_won: set[str] = set()

        # Determine evidence directory: per-test package takes precedence
        if test_package_dir is not None:
            self.evidence_dir = Path(test_package_dir) / "evidence"
        elif evidence_root is not None:
            self.evidence_dir = evidence_root / "evidence"
        else:
            # Fallback to workspace evidence directory
            self.evidence_dir = get_storage().evidence_dir()

        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.sidecar_path = self.evidence_dir / f"{self.test_name}.evidence.json"

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
    ) -> None:
        """Record one evidence step.

        Args:
            expected_page: The page this step's locator was resolved against.
                When the step actually runs somewhere else the mismatch is
                recorded on the step result (``page_mismatch``) so a wrong-page
                resolution is visible instead of silently passing. Empty means
                "not checked".
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

        # Determine step status — "partial_pass" when fallback was used
        if error:
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

        # AI-067: flag a step that ran on a page other than the one its locator
        # was resolved against. The trail/scope can be wrong even when an
        # element resolves (a page-level container matches anything), so the
        # mismatch must be recorded rather than passing silently.
        if expected_page:
            actual_page = self._step_entry_url or self._safe_page_url()
            if not _same_page(expected_page, actual_page):
                result["page_mismatch"] = {"expected": expected_page, "actual": actual_page}

        self.steps.append(
            {
                "step": step_idx + 1,
                "type": step_type,
                "label": self._clean_label(label),
                "locator": locator,
                "value": value,
                "screenshot": screenshot_path,
                "element": element_data,
                "url": self._safe_page_url(),  # B-033: per-step URL so flow divergence is traceable
                "result": result,
            }
        )

        # B-035: persist incrementally so a killed/timed-out process still
        # leaves evidence. Cheap (small JSON) — write on the first step and on
        # any failed/partial step; the final write() overwrites with the real
        # status.
        if step_idx == 0 or status in ("failed", "partial_pass"):
            self._persist_sidecar("running")

    def _safe_page_url(self) -> str:
        try:
            return str(self.page.url)
        except Exception:
            return ""

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
                duration_s=time.time() - self.start_time,
            )
            self.sidecar_path.write_text(json_content, encoding="utf-8")
        except Exception as exc:
            logger.warning("incremental evidence persistence failed: %s", exc)

    def navigate(self, url: str, label: str = "") -> None:
        """Navigate to a URL and record the navigation.

        Args:
            url: The URL to navigate to.
            label: Optional human-readable label for the step. Defaults to
                   "Navigate to <url>" when empty.
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
        try:
            self.page.goto(url)
            self._dismiss_consent_overlays()
            self._dismiss_ad_overlays()
            # Short settle so the evidence shot captures a rendered page, not
            # the mid-load flash (images get their own bounded wait in
            # ``_record_step``).
            self.page.wait_for_timeout(500)
            self._record_step(
                "navigate", label, value=safe_url, take_screenshot=True, elapsed_ms=int((time.time() - _t0) * 1000)
            )
        except Exception as e:
            self._record_step(
                "navigate",
                label,
                value=safe_url,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

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

    def click(self, locator: str, label: str = "", expected_page: str = "") -> None:
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
        except Exception as e:
            # Fast-failed not-found clicks were already recorded (fast_fail).
            if isinstance(e, _LocatorNotFoundError):
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
        self.run_history["total_runs"] += 1
        if status == "passed":
            self.run_history["passed_runs"] += 1
        else:
            self.run_history["failed_runs"] += 1

        self._persist_sidecar(status)
        return str(self.sidecar_path)
