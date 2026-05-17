"""Tests for screenshot capture during scraping."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

from PIL import Image

from src.scraper import ScrapeResult, capture_page_screenshot


class TestCapturePageScreenshot:
    """Test screenshot capture and bounding box extraction."""

    def test_screenshot_returns_valid_png(self, mock_page_with_elements: MagicMock) -> None:
        """Captured screenshot should be valid PNG bytes."""
        screenshot_bytes, _boxes = capture_page_screenshot(mock_page_with_elements, "https://example.com")

        image = Image.open(io.BytesIO(screenshot_bytes))
        assert image.format == "PNG"

    def test_screenshot_captures_full_page(self, mock_page_with_elements: MagicMock) -> None:
        """Full-page screenshot should capture entire page height."""
        capture_page_screenshot(mock_page_with_elements, "https://example.com", full_page=True)

        mock_page_with_elements.screenshot.assert_called_once_with(full_page=True, type="png")

    def test_element_boxes_contains_interactive_elements(self, mock_page_with_elements: MagicMock) -> None:
        """Element boxes should include all visible interactive elements with size."""
        _screenshot_bytes, boxes = capture_page_screenshot(mock_page_with_elements, "https://example.com")

        assert len(boxes) == 1
        assert boxes[0]["selector"] == "#submit"

    def test_element_boxes_filters_zero_size_elements(self, mock_page_with_elements: MagicMock) -> None:
        """Elements with zero width/height should be filtered out."""
        _screenshot_bytes, boxes = capture_page_screenshot(mock_page_with_elements, "https://example.com")

        selectors = {box["selector"] for box in boxes}
        assert "#hidden" not in selectors

    def test_element_boxes_maps_to_scraped_elements(self, mock_page_with_elements: MagicMock) -> None:
        """Each element box should include selector and element index for later matching."""
        _screenshot_bytes, boxes = capture_page_screenshot(mock_page_with_elements, "https://example.com")

        assert boxes[0]["selector"] == "#submit"
        assert boxes[0]["element_index"] == 0

    def test_element_boxes_contains_bounding_box_coords(self, mock_page_with_elements: MagicMock) -> None:
        """Each element box should have x, y, width, height coordinates."""
        _screenshot_bytes, boxes = capture_page_screenshot(mock_page_with_elements, "https://example.com")

        assert boxes[0]["bbox"] == {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
        assert boxes[0]["is_visible"] is True


class TestScrapeResultWithScreenshot:
    """Test ScrapeResult dataclass with screenshot fields."""

    def test_scrape_result_has_screenshot_fields(self) -> None:
        """ScrapeResult should have screenshot_bytes and element_boxes fields."""
        result = ScrapeResult(
            url="https://example.com",
            elements=[],
            screenshot_bytes=b"png",
            element_boxes=[{"selector": "#submit"}],
        )

        assert result.screenshot_bytes == b"png"
        assert result.element_boxes == [{"selector": "#submit"}]

    def test_scrape_result_defaults_screenshot_to_none(self) -> None:
        """By default, screenshot_bytes should be None for backward compatibility."""
        result = ScrapeResult(url="https://example.com", elements=[])

        assert result.screenshot_bytes is None
        assert result.element_boxes is None
