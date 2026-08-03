"""Auto-generated page object module."""

from playwright.sync_api import Page
from src.evidence_tracker import EvidenceTracker


class HomePage:
    """Page Object for http://127.0.0.1:8123/index.html. Scraped elements: 2."""

    URL = "http://127.0.0.1:8123/index.html"

    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
        self.page = page
        self.tracker = tracker

    def navigate(self) -> None:
        self.tracker.navigate(self.URL)

    def click(self, description: str, selector: str | None = None) -> None:
        """Click by semantic description — delegate to tracker with resolved selector."""
        self.tracker.click(selector, label=description)

    def click_go_to_cart(self) -> None:
        self.tracker.click('#go-cart', label='go to cart')
