import logging
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page

from src.evidence_serializer import EvidenceSerializer
from src.failure_reporter import FailureReporter
from src.hover_click_utils import try_hover_and_click
from src.locator_fallback import LocatorFallback
from src.storage import get_storage

logger = logging.getLogger(__name__)


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
        try:
            element_id = loc.get_attribute("id") or ""
            test_id = loc.get_attribute("data-testid") or ""
            raw_href = loc.get_attribute("href") or ""
            # Mock pages return MagicMock here — only keep real strings (B-029).
            href = raw_href if isinstance(raw_href, str) else ""
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
    ) -> None:
        """Record one evidence step.

        Args:
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
            screenshot_name = f"{self.test_name}_{step_idx}_{step_type}_{int(time.time())}.png"
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
            label = f"Navigate to {url}"
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
                "navigate", label, value=url, take_screenshot=True, elapsed_ms=int((time.time() - _t0) * 1000)
            )
        except Exception as e:
            self._record_step(
                "navigate",
                label,
                value=url,
                take_screenshot=True,
                error=str(e),
                elapsed_ms=int((time.time() - _t0) * 1000),
            )
            raise

    def fill(self, locator: str, value: str, label: str = "") -> None:
        if not label:
            label = f"Fill {locator} with '{value}'"
        _t0 = time.time()
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
            self._record_step("fill", label, locator=locator, value=value, elapsed_ms=int((time.time() - _t0) * 1000))
        except Exception as e:
            self._record_step(
                "fill", label, locator=locator, value=value, error=str(e), elapsed_ms=int((time.time() - _t0) * 1000)
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

    def click(self, locator: str, label: str = "") -> None:
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
                )
                self._verify_click_navigation(locator, label, el_metadata, original_url)
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
                        )
                        self._verify_click_navigation(locator, label, el_metadata, original_url)
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
                    self._verify_click_navigation(locator, label, el_metadata, original_url)
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
            )
            raise

    # ── B-029: post-click navigation verification ────────────────────────────

    def _verify_click_navigation(
        self,
        locator: str,
        label: str,
        el_metadata: dict[str, Any],
        original_url: str,
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
        """
        href = str(el_metadata.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return  # not a navigation link — nothing to verify
        try:
            target = urljoin(original_url, href)
            if (
                urlparse(target).path == urlparse(original_url).path
                and urlparse(target).netloc == urlparse(original_url).netloc
            ):
                return  # same-page link (anchor / hash navigation)
        except Exception:
            return

        if self._url_changed(original_url, timeout=2.5):
            return

        # Click succeeded but no navigation — likely swallowed by an overlay.
        # Dismiss and retry once before declaring failure.
        self._dismiss_ad_overlays()
        self._dismiss_confirmation_modals()
        try:
            self.page.locator(locator).first.click(timeout=5000)
        except Exception:
            pass
        if self._url_changed(original_url, timeout=2.5):
            return

        # Still no navigation — amend the recorded step to a truthful failure.
        self._amend_last_click_to_failure(label, locator, original_url)
        raise _LocatorNotFoundError(
            f"Click '{label}' succeeded but the page did not navigate (still on {original_url}). "
            "The click was likely swallowed by an overlay even after dismissal + retry."
        )

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

    def _amend_last_click_to_failure(self, label: str, locator: str, original_url: str) -> None:
        """Flip the last recorded passed/partial click step to a truthful failure."""
        if not self.steps:
            return
        last = self.steps[-1]
        result = last.get("result", {})
        if last.get("type") != "click" or result.get("status") not in ("passed", "partial_pass"):
            return
        error = (
            f"Click recorded passed but the page did not navigate (stayed on {original_url}). "
            "Overlay swallow suspected — the click was consumed by an ad/consent overlay."
        )
        result["status"] = "failed"
        result["error"] = error
        result["failure_note"] = error
        self._persist_sidecar("running")

    def assert_visible(self, locator: str, label: str = "") -> None:
        if not label:
            label = f"Assert visible: {locator}"
        _t0 = time.time()
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

    # --- B-020: Additional assertion methods ---

    def assert_hidden(self, locator: str, label: str = "") -> None:
        """Assert the element is hidden or detached — a state-ABSENCE check.

        For polarity ASSERTs like "popup closed" / "item removed": Playwright's
        ``wait_for(state="hidden")`` passes for hidden OR detached nodes, which
        is exactly the "this is gone" semantics.
        """
        if not label:
            label = f"Assert hidden: {locator}"
        _t0 = time.time()
        try:
            self.page.locator(locator).first.wait_for(state="hidden", timeout=5000)
            self._record_step(
                "assertion",
                label,
                locator=locator,
                take_screenshot=True,
                matched_text=None,
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
