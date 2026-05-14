# Session 2: Screenshot Capture During Scraping

**AI-027 — Visual Element Enrichment**  
**Created:** 2026-05-13  
**Depends on:** Session 1 (VisionEnricher + vision detection)  
**Original spec:** `docs/specs/FEATURE_SPEC_visual_element_enrichment.md`

---

## Goal

Add screenshot capture and bounding box extraction to the scraping pipeline. This creates the visual data layer that vision enrichment depends on. No LLM calls yet — just capture + store.

**Deliverables:**
- `src/scraper.py` — modified: `capture_page_screenshot()` + integration into scrape flow
- `tests/test_scraper_screenshot.py` — Unit tests for screenshot capture
- Updated documentation

---

## Current State of Relevant Files

### src/scraper.py
- `PageScraper.scrape_url()` — scrapes DOM metadata for a single URL
- `PageScraper.scrape_all()` — orchestrates multi-URL scraping
- Uses Playwright browser context for DOM extraction
- **Needs:** Screenshot capture + bounding box extraction after DOM scrape

### src/vision_enricher.py (from Session 1)
- `VisionEnricher.crop_element_from_screenshot()` — ready to crop elements
- `VisionEnricher.is_vision_capable()` — ready for detection
- **Needs:** Integration with scraper pipeline (done in Session 3)

---

## Implementation Tasks

### Task 1: Add `capture_page_screenshot()` to `src/scraper.py`

```python
def capture_page_screenshot(
    page: Page,
    url: str,
    full_page: bool = True,
) -> tuple[bytes, list[dict[str, Any]]]:
    """Capture a full-page screenshot and extract element bounding boxes.

    This captures the page state AFTER DOM scraping, when all elements
    are in their final rendered positions.

    Args:
        page: Playwright Page object (already navigated to URL).
        url: The URL being scraped (for logging).
        full_page: Whether to capture the full scrollable page.

    Returns:
        (screenshot_bytes, element_boxes) where:
        - screenshot_bytes: PNG bytes of the full-page screenshot
        - element_boxes: List of dicts with keys:
            - "selector": str — CSS selector for the element
            - "bbox": dict — {x, y, width, height} in viewport coords
            - "element_index": int — index in the scraped elements list
            - "is_visible": bool — whether element is visible
    """
```

**Implementation details:**
1. Capture screenshot: `page.screenshot(full_page=full_page, type="png")`
2. Select all interactive elements: `page.locator("button, a, input, select, [onclick], [role=button], [tabindex]")`
3. For each element, call `element.bounding_box()` — returns `{x, y, width, height, height}`
4. Filter out elements with `width == 0 or height == 0`
5. Map each bounding box back to the corresponding scraped element by matching selectors
6. Return screenshot bytes + list of element boxes

### Task 2: Modify `scrape_url()` to capture screenshots

**Modified in `src/scraper.py`:**

After the existing DOM scraping in `scrape_url()`:
1. Call `capture_page_screenshot(page, url)`
2. Store screenshot bytes in a new return field
3. Store element bounding boxes in a new return field
4. Update return type to include optional screenshot data

```python
# New dataclass for scrape result with screenshot data
@dataclass
class ScrapeResult:
    url: str
    elements: list[dict[str, Any]]
    title: str
    html_snippet: str
    # NEW fields:
    screenshot_bytes: bytes | None = None  # Full-page screenshot PNG
    element_boxes: list[dict[str, Any]] | None = None  # Bounding boxes
```

### Task 3: Modify `scrape_all()` to collect screenshots

**Modified in `src/scraper.py`:**

After existing multi-URL scraping:
1. Each URL scrape now optionally returns `ScrapeResult` with screenshot data
2. Collect all `ScrapeResult` objects with screenshot data
3. Return the full list (caller decides whether to enrich)

### Task 4: Create `tests/test_scraper_screenshot.py`

```python
"""Tests for screenshot capture during scraping."""

import pytest

from src.scraper import PageScraper, capture_page_screenshot


class TestCapturePageScreenshot:
    """Test screenshot capture and bounding box extraction."""

    def test_screenshot_returns_valid_png(self, mock_page) -> None:
        """Captured screenshot should be valid PNG bytes."""

    def test_screenshot_captures_full_page(self, mock_page) -> None:
        """Full-page screenshot should capture entire page height."""

    def test_element_boxes_contains_interactive_elements(self, mock_page) -> None:
        """Element boxes should include all interactive elements."""

    def test_element_boxes_filters_zero_size_elements(self, mock_page) -> None:
        """Elements with zero width/height should be filtered out."""

    def test_element_boxes_maps_to_scraped_elements(self, mock_page) -> None:
        """Each element box should map to a scraped element by selector match."""

    def test_element_boxes_contains_bounding_box_coords(self, mock_page) -> None:
        """Each element box should have x, y, width, height coordinates."""


class TestScrapeResultWithScreenshot:
    """Test ScrapeResult dataclass with new screenshot fields."""

    def test_scrape_result_has_screenshot_fields(self) -> None:
        """ScrapeResult should have screenshot_bytes and element_boxes fields."""

    def test_scrape_result_defaults_screenshot_to_none(self) -> None:
        """By default, screenshot_bytes should be None (backward compat)."""
```

### Task 5: Add mock fixtures to `tests/conftest.py`

```python
@pytest.fixture
def mock_page(mock_browser) -> MagicMock:
    """Mock Playwright Page for screenshot testing."""

@pytest.fixture
def mock_page_with_elements(mock_page) -> MagicMock:
    """Mock Page with interactive elements and bounding boxes."""
```

---

## Documentation Updates

### docs/ARCHITECTURE.md
Update `src/scraper.py` entry in "Context Extraction Layer":
```
| `src/scraper.py` (`PageScraper`) | Stateless HTTP scraper. DOM scraping + screenshot capture + bounding box extraction.
|                                   | Returns ScrapeResult with elements, screenshot_bytes, and element_boxes.
```

### docs/PROJECT_KNOWLEDGE.md
Add to "Architecture Decisions":
```
| Screenshot capture | One screenshot per page during scraping. Stored in-memory. Used for vision enrichment.
|                    | Discarded after enrichment completes. No disk I/O.
```

### BACKLOG.md
Update AI-027 status:
```
### AI-027 — Visual Element Enrichment (IN PROGRESS — Session 2 of 4)
**Session 1 complete:** VisionEnricher + vision capability detection
**Session 2 in progress:** Screenshot capture during scraping
```

### CHANGELOG.md
Add entry:
```
| 1.8.0 | 2026-05-13 | AI-027 Session 2: Screenshot capture during scraping
```

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Protected files — DO NOT TOUCH:**
  - `src/llm_client.py`
  - `src/test_generator.py`
  - `src/llm_providers/`
  - `.github/workflows/ci.yml`

---

## Verification Steps

1. `ruff check src/scraper.py` — clean
2. `mypy src/scraper.py` — clean
3. `pytest tests/test_scraper_screenshot.py -v` — all green
4. `pytest tests/ -v` — ALL existing tests still pass
5. End-to-end: Run UAT script against saucedemo — should produce same results as before (no regression, vision not yet active)

---

## Expected Test Count

- `test_scraper_screenshot.py`: 7 tests minimum
  - 6 tests for `capture_page_screenshot()` and bounding boxes
  - 2 tests for `ScrapeResult` dataclass