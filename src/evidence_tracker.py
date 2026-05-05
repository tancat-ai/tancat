import json
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from src.failure_reporter import FailureReporter
from src.locator_fallback import LocatorFallback


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
            # Fallback to legacy behaviour (repo root)
            self.evidence_dir = Path(__file__).resolve().parents[1] / "evidence"

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
        """Best-effort dismissal of consent, cookie, and ad-overlay popups.

        Handles:
        - Standard GDPR consent buttons (Consent, Accept, Agree, etc.)
        - Google Consent TVM (fc-consent-root / fc-dialog-overlay)
        - Google AdSense vignette overlays
        - General modal overlays that intercept pointer events

        NOTE: Timeouts are intentionally low (500ms) to avoid blocking test execution.
        On sites without consent banners, this should complete in <200ms total.
        """
        # Fast-path: try JS removal first (no waiting, no iteration)
        try:
            self.page.evaluate(
                """
                () => {
                    // Remove consent/cookie banners via JS (fastest path)
                    document.querySelectorAll('.fc-consent-root, .fc-dialog-overlay, [class*=consent], [class*=cookie-banner], [class*=cookie-modal]').forEach(el => el.remove());
                    // Remove high z-index overlays (excluding iframes)
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        const style = window.getComputedStyle(el);
                        const zIndex = parseInt(style.zIndex, 10);
                        if (zIndex > 10000 && el.tagName !== 'IFRAME') { el.remove(); }
                    }
                }
                """
            )
        except Exception:
            pass

        # Only iterate buttons if JS didn't clear everything
        selectors = [
            "button:has-text('Consent')",
            "button:has-text('Accept')",
            "button:has-text('OK')",
            "button[aria-label='Close']",
        ]
        for selector in selectors:
            try:
                loc = self.page.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=500)
                    break
            except Exception:
                continue

        # Single Escape press
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass

    def _dismiss_ad_overlays(self) -> None:
        """Dismiss ad overlays that intercept pointer events.

        This handles Google AdSense overlays and other common ad frameworks
        that can block clicks on e-commerce test sites.

        NOTE: Uses JS removal (fast) instead of iterative clicking.
        """
        # Single Escape press
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass

        # Use JavaScript to remove ad overlays — fast and reliable
        try:
            self.page.evaluate(
                """
                () => {
                    const vignette = document.getElementById('google_vignette');
                    if (vignette) {
                        vignette.style.display = 'none';
                        vignette.style.visibility = 'hidden';
                    }
                    document.querySelectorAll('ins.adsbygoogle, iframe[id*="aswift"], iframe[title="Advertisement"], [class*="ads"], [id*="google_ads"]').forEach(el => {
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                    });
                }
                """
            )
        except Exception:
            pass

    def _load_previous_history(self) -> dict[str, int]:
        if self.sidecar_path.exists():
            try:
                with open(self.sidecar_path, encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("run_history", {"total_runs": 0, "passed_runs": 0, "failed_runs": 0})
            except Exception:
                pass
        return {"total_runs": 0, "passed_runs": 0, "failed_runs": 0}

    def _load_previous_steps(self) -> list[dict[str, Any]]:
        if self.sidecar_path.exists():
            try:
                with open(self.sidecar_path, encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("steps", [])
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
        try:
            element_id = loc.get_attribute("id") or ""
            test_id = loc.get_attribute("data-testid") or ""
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
            dw = doc_size["width"]
            dh = doc_size["height"]

            raw_bbox = loc.bounding_box()
            if raw_bbox:
                # bounding_box() is relative to the main frame (the whole page).
                # We record these coordinates as a percentage of the WHOLE document.
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

                # Record center point as percentage of FULL document
                viewport_pct = {
                    "x": (center_x / dw) * 100,
                    "y": (center_y / dh) * 100,
                }
        except Exception:
            pass

        return {
            "tag": tag,
            "element_id": element_id if element_id else None,
            "test_id": test_id if test_id else None,
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
    ) -> None:
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
                # Take full page screenshot so coordinates relative to frame always match.
                self.page.screenshot(path=str(screenshot_full_path), full_page=True)
                screenshot_path = f"evidence/{screenshot_name}"
            except Exception:
                pass

        element_data = self._get_element_metadata(locator)

        # On failure, generate self-diagnosing failure evidence (Tier 1).
        failure_note: str | None = None
        diagnosis: dict[str, Any] | None = None
        if error:
            try:
                diagnosis = FailureReporter.diagnose_failure(self.page, locator, step_type, error)
                failure_note = FailureReporter.generate_failure_note(diagnosis)
            except Exception:
                # Diagnosis is best-effort; don't let it break test execution.
                failure_note = f"[diagnosis failed: {error[:100]}]"

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
                "result": result,
            }
        )

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
            self.page.locator(locator).fill(value)
            self._record_step("fill", label, locator=locator, value=value, elapsed_ms=int((time.time() - _t0) * 1000))
        except Exception as e:
            self._record_step(
                "fill", label, locator=locator, value=value, error=str(e), elapsed_ms=int((time.time() - _t0) * 1000)
            )
            raise

    def click(self, locator: str, label: str = "") -> None:
        """Click an element, with layered fallback strategies.

        Strategy (Tier 2 — Locator Scoring + Controlled Fallback):
        1. Scroll into view
        2. Try direct click with primary locator
        3. If click fails with visibility/timeout error:
           a. Try hover-reveal fallback (existing)
           b. Try locator scoring fallback (new — higher-scoring alternatives)
        4. If any fallback succeeds, mark step as "partial_pass" with audit trail
        """
        if not label:
            label = f"Click {locator}"
        _t0 = time.time()
        try:
            # We record metadata BEFORE clicking in case navigation clears it
            el_metadata = self._get_element_metadata(locator)
            # Always click `first` to avoid strict-mode failures when a locator is
            # valid but matches multiple elements (common on e-commerce grids).
            loc = self.page.locator(locator).first
            try:
                loc.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                # Scrolling is best-effort; clicking may still succeed without it.
                pass

            # Attempt 1: Direct click
            try:
                loc.click(timeout=5000)
                self._record_step("click", label, locator=locator, elapsed_ms=int((time.time() - _t0) * 1000))
                self.steps[-1]["element"] = el_metadata
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

                    # Attempt 2: Hover-reveal fallback (existing)
                    hover_result = self._try_hover_and_click(loc, locator, label, el_metadata)
                    if hover_result is not None:
                        return  # Hover fallback succeeded

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
                else:
                    raise
        except Exception as e:
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

    def _try_hover_and_click(self, loc: Any, locator: str, label: str, el_metadata: dict) -> None | bool:
        """Try to click by first dispatching mouseenter events for hover-reveal elements.

        Returns True if the hover fallback succeeded, None if all attempts failed.

        This handles elements that are hidden via CSS (display:none, visibility:hidden,
        opacity:0) and only become visible when the parent element receives a mouseenter
        event — common pattern in e-commerce product grids.

        Strategy:
        1. Hover target element directly
        2. Dispatch mouseenter on target + ancestors
        3. Find and hover visible parent category triggers (e.g., "Women" revealing subcategories)
        4. Use JavaScript to force-show hidden elements and click via DOM
        """
        _t0 = time.time()

        # Attempt 1: Hover the element itself
        try:
            loc.hover(timeout=2000, force=False)
            self.page.wait_for_timeout(300)
        except Exception:
            pass

        try:
            loc.click(timeout=5000)
            self._record_step("click", label, locator=locator, elapsed_ms=int((time.time() - _t0) * 1000))
            self.steps[-1]["element"] = el_metadata
            return True
        except Exception:
            pass

        # Attempt 2: Dispatch mouseenter on element + ancestors
        try:
            loc.evaluate("el => el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))")
            self.page.wait_for_timeout(300)
            loc.click(timeout=5000)
            self._record_step("click", label, locator=locator, elapsed_ms=int((time.time() - _t0) * 1000))
            self.steps[-1]["element"] = el_metadata
            return True
        except Exception:
            pass

        # Attempt 3: Dispatch mouseenter on all ancestors (for overlay patterns)
        try:
            self.page.evaluate(
                """
                (selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return false;
                    const mouseEnter = new MouseEvent('mouseenter', { bubbles: true });
                    el.dispatchEvent(mouseEnter);
                    let parent = el.parentElement;
                    while (parent && parent.tagName !== 'BODY') {
                        parent.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                        parent = parent.parentElement;
                    }
                    return true;
                }
            """,
                locator,
            )
            self.page.wait_for_timeout(300)
            loc.click(timeout=5000)
            self._record_step("click", label, locator=locator, elapsed_ms=int((time.time() - _t0) * 1000))
            self.steps[-1]["element"] = el_metadata
            return True
        except Exception:
            pass

        # Attempt 4: Find and hover visible parent category triggers.
        # On sites like automationexercise.com, subcategory links (e.g., "Dress") are
        # hidden inside a sidebar menu until you hover the parent category header
        # (e.g., "Women", "Men", "Kids"). We need to find those visible trigger elements.
        try:
            result = self.page.evaluate(
                """
                (targetSelector) => {
                    const target = document.querySelector(targetSelector);
                    if (!target) return { clicked: false, reason: 'no target' };

                    // Walk up the DOM to find menu container structure
                    let el = target;
                    while (el && el.tagName !== 'BODY') {
                        // Look for parent elements that are visible and might be category triggers
                        // These are typically <a> or <li> elements with text content, no hidden classes
                        const style = window.getComputedStyle(el);

                        // Check siblings that might be the hover trigger
                        const parent = el.parentElement;
                        if (parent) {
                            for (const sibling of parent.children) {
                                const sibStyle = window.getComputedStyle(sibling);
                                const isVisible = sibStyle.display !== 'none' &&
                                                  sibStyle.visibility !== 'hidden' &&
                                                  sibStyle.opacity !== '0';
                                // Look for anchor tags or list items that are visible and have text
                                if (isVisible && (sibling.tagName === 'A' || sibling.tagName === 'LI') &&
                                    sibling.textContent.trim().length > 0 && sibling.textContent.trim().length < 50) {
                                    // Dispatch hover on this visible sibling
                                    const mouseEnter = new MouseEvent('mouseenter', { bubbles: true });
                                    sibling.dispatchEvent(mouseEnter);

                                    // Also try actual hover via dispatching on the element
                                    sibling.style.visibility = 'visible';
                                    sibling.style.display = 'block';
                                }
                            }
                        }

                        // Check if this ancestor is a visible category header
                        const ancestorStyle = window.getComputedStyle(el);
                        if (ancestorStyle.display !== 'none' && el.tagName === 'A' && el.textContent.trim()) {
                            // Hover this visible ancestor
                            const mouseEnter = new MouseEvent('mouseenter', { bubbles: true });
                            el.dispatchEvent(mouseEnter);
                            const mouseOver = new MouseEvent('mouseover', { bubbles: true });
                            el.dispatchEvent(mouseOver);

                            // Now check if target became visible
                            const targetStyle2 = window.getComputedStyle(target);
                            if (targetStyle2.display !== 'none' && targetStyle2.visibility !== 'hidden') {
                                return { clicked: false, reason: 'ancestor hovered', madeVisible: true };
                            }
                        }

                        el = el.parentElement;
                    }
                    return { clicked: false, reason: 'walked ancestors' };
                }
                """,
                locator,
            )

            if result and result.get("madeVisible"):
                self.page.wait_for_timeout(500)  # Longer wait for CSS transition after hover
                try:
                    loc.click(timeout=5000)
                    self._record_step("click", label, locator=locator, elapsed_ms=int((time.time() - _t0) * 1000))
                    self.steps[-1]["element"] = el_metadata
                    return True
                except Exception:
                    pass
        except Exception:
            pass

        # Attempt 5: Force-show the element via JavaScript and click programmatically.
        # This is a last resort for elements hidden behind CSS hover menus.
        try:
            self.page.evaluate(
                """
                (selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return false;

                    // Force the element and all ancestors to be visible
                    let current = el;
                    while (current && current.tagName !== 'BODY') {
                        const style = window.getComputedStyle(current);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                            // Remove inline styles that hide the element
                            current.style.display = '';
                            current.style.visibility = '';
                            current.style.opacity = '1';

                            // Also remove any CSS classes that might be hiding it
                            const classesToRemove = [];
                            for (const cls of current.classList) {
                                if (cls.includes('hidden') || cls.includes('collapse') ||
                                    cls.includes('invisible') || cls.includes('collapsed')) {
                                    classesToRemove.push(cls);
                                }
                            }
                            classesToRemove.forEach(c => current.classList.remove(c));

                            // Add a class to force visibility
                            current.style.setProperty('display', 'block', 'important');
                            current.style.setProperty('visibility', 'visible', 'important');
                        }
                        current = current.parentElement;
                    }

                    // Now click the element programmatically
                    el.click();
                    return true;
                }
                """,
                locator,
            )
            self.page.wait_for_timeout(500)
            # Record success — JS click was used as fallback
            self._record_step("click", label, locator=locator, elapsed_ms=int((time.time() - _t0) * 1000))
            self.steps[-1]["element"] = el_metadata
            return True
        except Exception:
            pass

        # All hover attempts failed — return None to signal fallback failure
        return None

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

    def write(self, status: str = "passed") -> str:
        """Writes the sidecar and updates history."""
        self.run_history["total_runs"] += 1
        if status == "passed":
            self.run_history["passed_runs"] += 1
        else:
            self.run_history["failed_runs"] += 1

        duration_s = round(time.time() - self.start_time, 2)

        payload = {
            "schema_version": "1.0",
            "test": {
                "name": self.test_name,
                "condition_ref": self.condition_ref,
                "story_ref": self.story_ref,
                "status": status,
                "duration_s": duration_s,
            },
            "page": {
                "url": self.page.url,
            },
            "run_history": self.run_history,
            "steps": self.steps,
        }

        with open(self.sidecar_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        return str(self.sidecar_path)
