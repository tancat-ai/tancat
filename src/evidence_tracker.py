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
        """Best-effort consent dismissal before evidence screenshots."""
        selectors = [
            "button:has-text('Consent')",
            "button:has-text('Accept')",
            "button:has-text('Continue')",
            "button:has-text('OK')",
            "button:has-text('Got it')",
            "button:has-text('I Agree')",
            "button:has-text('Agree')",
            "button[aria-label='Close']",
            "button[aria-label='close']",
        ]
        for selector in selectors:
            try:
                loc = self.page.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    loc.click(timeout=2000)
                    self.page.wait_for_timeout(300)
                    break
            except Exception:
                continue

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
            "elapsed_ms": 0,  # Could bracket logic above via time.time() to grab real ms
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
        try:
            self.page.goto(url)
            self._dismiss_consent_overlays()
            self._record_step("navigate", label, value=url, take_screenshot=True)
        except Exception as e:
            self._record_step("navigate", label, value=url, take_screenshot=True, error=str(e))
            raise

    def fill(self, locator: str, value: str, label: str = "") -> None:
        if not label:
            label = f"Fill {locator} with '{value}'"
        try:
            self.page.locator(locator).fill(value)
            self._record_step("fill", label, locator=locator, value=value)
        except Exception as e:
            self._record_step("fill", label, locator=locator, value=value, error=str(e))
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
                self._record_step("click", label, locator=locator)
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
                    )
                else:
                    raise
        except Exception as e:
            # Always screenshot on click failure; this is the single most useful
            # artifact for evidence viewer + heatmaps.
            self._record_step("click", label, locator=locator, take_screenshot=True, error=str(e))
            raise

    def _try_hover_and_click(self, loc: Any, locator: str, label: str, el_metadata: dict) -> None | bool:
        """Try to click by first dispatching mouseenter events for hover-reveal elements.

        Returns True if the hover fallback succeeded, None if all attempts failed.

        This handles elements that are hidden via CSS (display:none, visibility:hidden,
        opacity:0) and only become visible when the parent element receives a mouseenter
        event — common pattern in e-commerce product grids.
        """
        # Try hovering over the element itself first
        try:
            loc.hover(timeout=2000, force=False)
            self.page.wait_for_timeout(300)  # Brief wait for CSS transition
        except Exception:
            pass

        # Try clicking after hover
        try:
            loc.click(timeout=5000)
            self._record_step("click", label, locator=locator)
            self.steps[-1]["element"] = el_metadata
            return True
        except Exception:
            pass

        # Try dispatching mouseenter on the element
        try:
            loc.evaluate("el => el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))")
            self.page.wait_for_timeout(300)
            loc.click(timeout=5000)
            self._record_step("click", label, locator=locator)
            self.steps[-1]["element"] = el_metadata
            return True
        except Exception:
            pass

        # Try dispatching mouseenter on all ancestors (for overlay patterns)
        # This handles cases where the clickable element is inside a hidden overlay
        try:
            self.page.evaluate(
                """
                (selector) => {
                    // Find the element and dispatch mouseenter on it and ancestors
                    const el = document.querySelector(selector);
                    if (!el) return false;

                    // Dispatch mouseenter on the element
                    const mouseEnter = new MouseEvent('mouseenter', { bubbles: true });
                    el.dispatchEvent(mouseEnter);

                    // Also dispatch on parent elements up to body
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
            self._record_step("click", label, locator=locator)
            self.steps[-1]["element"] = el_metadata
            return True
        except Exception:
            pass

        # All hover attempts failed — return None to signal fallback failure
        return None

    def assert_visible(self, locator: str, label: str = "") -> None:
        if not label:
            label = f"Assert visible: {locator}"
        try:
            # Use `first` to avoid strict-mode violations when multiple elements
            # match (common with overlays/duplicate buttons in e-commerce UIs).
            loc = self.page.locator(locator).first
            loc.wait_for(state="visible", timeout=5000)
            matched_text = loc.text_content()
            self._record_step("assertion", label, locator=locator, take_screenshot=True, matched_text=matched_text)
        except Exception as e:
            self._record_step("assertion", label, locator=locator, take_screenshot=True, error=str(e))
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
