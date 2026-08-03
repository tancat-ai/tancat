"""Auto-generated page object module."""

from playwright.sync_api import Page
from src.evidence_tracker import EvidenceTracker


class CartPage:
    """Page Object for http://127.0.0.1:8123/cart.html. Scraped elements: 1."""

    URL = "http://127.0.0.1:8123/cart.html"

    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
        self.page = page
        self.tracker = tracker

    def navigate(self) -> None:
        self.tracker.navigate(self.URL)
