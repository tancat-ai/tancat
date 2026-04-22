import json
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page


class EvidenceTracker:
    def __init__(
        self,
        page: Page,
        test_name: str,
        condition_ref: str = "unknown",
        story_ref: str = "unknown",
        *,
        evidence_root: Path | None = None,
    ) -> None:
        self.page = page
        self.test_name = test_name
        self.condition_ref = condition_ref
        self.story_ref = story_ref

        self.steps: list[dict[str, Any]] = []
        self.start_time = time.time()
        # Anchor evidence artifacts to the repo root so Streamlit and pytest agree
        # regardless of current working directory. Allow tests/tools to override.
        repo_root = evidence_root if evidence_root is not None else Path(__file__).resolve().parents[1]
        self.evidence_dir = repo_root / "evidence"
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

        self.steps.append(
            {
                "step": step_idx + 1,
                "type": step_type,
                "label": self._clean_label(label),
                "locator": locator,
                "value": value,
                "screenshot": screenshot_path,
                "element": element_data,
                "result": {
                    "status": "failed" if error else "passed",
                    "elapsed_ms": 0,  # Could bracket logic above via time.time() to grab real ms
                    "run_count": step_run_count,
                    "matched_text": matched_text,
                    "error": error,
                },
            }
        )

    def navigate(self, url: str) -> None:
        try:
            self.page.goto(url)
            self._dismiss_consent_overlays()
            self._record_step("navigate", f"Navigate to {url}", value=url, take_screenshot=True)
        except Exception as e:
            self._record_step("navigate", f"Navigate to {url}", value=url, take_screenshot=True, error=str(e))
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
            loc.click()
            self._record_step("click", label, locator=locator)
            self.steps[-1]["element"] = el_metadata
        except Exception as e:
            # Always screenshot on click failure; this is the single most useful
            # artifact for evidence viewer + heatmaps.
            self._record_step("click", label, locator=locator, take_screenshot=True, error=str(e))
            raise

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
