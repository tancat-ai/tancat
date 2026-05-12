"""Screenshot capture and annotation utilities."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page


def generate_screenshot_path(output_dir: Path, label: str, index: int = 0) -> Path:
    """Return a unique screenshot path based on label and timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = _sanitize_label(label)
    return output_dir / f"{safe_label}_{index}_{timestamp}.png"


def _sanitize_label(label: str) -> str:
    """Convert a label to a safe filename component."""
    sanitized = ""
    for ch in label.lower():
        if ch.isalnum():
            sanitized += ch
        elif ch in (" ", "/", "."):
            sanitized += "_"
    return sanitized.strip("_") or "screenshot"


def capture_screenshot(
    page: Page,
    label: str,
    output_dir: Path,
    index: int = 0,
    full_page: bool = False,
) -> str:
    """Capture a screenshot and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = generate_screenshot_path(output_dir, label, index)
    page.screenshot(path=str(path), full_page=full_page)
    return str(path)


def capture_element_screenshot(
    page: Page,
    selector: str,
    label: str,
    output_dir: Path,
    index: int = 0,
) -> str | None:
    """Capture a screenshot of a specific element."""
    try:
        el = page.locator(selector).first
        if el.is_visible():
            output_dir.mkdir(parents=True, exist_ok=True)
            path = generate_screenshot_path(output_dir, f"{label}_element", index)
            el.screenshot(path=str(path))
            return str(path)
    except Exception:
        pass
    return None


def get_element_metadata(page: Page, selector: str) -> dict[str, Any] | None:
    """Extract metadata about a page element for diagnostic purposes."""
    try:
        el = page.locator(selector).first
        if not el.is_visible():
            return None
        return {
            "tag_name": el.evaluate("e => e.tagName.toLowerCase()"),
            "text_content": el.evaluate("e => e.textContent || ''")[:200],
            "aria_label": el.get_attribute("aria-label") or "",
            "id": el.get_attribute("id") or "",
            "name": el.get_attribute("name") or "",
            "class": el.get_attribute("class") or "",
            "placeholder": el.get_attribute("placeholder") or "",
            "type": el.get_attribute("type") or "",
            "visible": el.is_visible(),
            "enabled": el.is_enabled(),
        }
    except Exception:
        return None


def capture_on_failure(
    page: Page,
    error: str,
    output_dir: Path,
    step_label: str,
    index: int = 0,
) -> dict[str, Any]:
    """Capture diagnostics when a step fails."""
    result: dict[str, Any] = {
        "error": error,
        "url": page.url,
        "title": page.title(),
    }
    try:
        result["screenshot"] = capture_screenshot(page, f"failure_{step_label}", output_dir, index, full_page=True)
    except Exception:
        result["screenshot"] = None
    try:
        result["console_logs"] = page.evaluate("() => []")  # placeholder
    except Exception:
        pass
    return result
