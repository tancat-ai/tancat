"""Pytest configuration and fixtures for test suite."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Configure anyio backend for async tests."""
    return "asyncio"


@pytest.fixture
def mock_browser() -> MagicMock:
    """Mock Playwright browser for scraper tests."""
    return MagicMock()


@pytest.fixture
def mock_page(mock_browser: MagicMock) -> MagicMock:
    """Mock Playwright Page for screenshot testing."""
    page = MagicMock()
    page.screenshot.return_value = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
        b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return page


@pytest.fixture
def mock_page_with_elements(mock_page: MagicMock) -> MagicMock:
    """Mock Page with interactive elements and bounding boxes."""
    locator_collection = MagicMock()
    first = MagicMock()
    first.bounding_box.return_value = {"x": 10, "y": 20, "width": 100, "height": 30}
    first.evaluate.return_value = "#submit"
    first.is_visible.return_value = True

    second = MagicMock()
    second.bounding_box.return_value = {"x": 5, "y": 60, "width": 0, "height": 20}
    second.evaluate.return_value = "#hidden"
    second.is_visible.return_value = False

    locator_collection.count.return_value = 2
    locator_collection.nth.side_effect = [first, second]
    mock_page.locator.return_value = locator_collection
    return mock_page
