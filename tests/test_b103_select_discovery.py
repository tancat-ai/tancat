"""Tests for B-103 — journey discovery clicks the dropdown, not the submit button.

BACKLOG B-103: the eval-010 journey step "select item" (a skeleton-invented
replay step) resolved to #place-order, a type=submit button, because the
CLICK role whitelist in JourneyScraper._discover_selector penalised
role=select (-20) while the submit button stayed whitelisted. The journey
then submitted the mock form (default qty=1 is valid) and navigated to
success.html before the quantity fill and the real "Place Order" step, so
every later step replayed on the wrong page.

Live tests drive the real discovery pipeline against mock_sites/ambiguous
(the mock built for the 2026-10-16 trace — see
scripts/archive/debug_scripts/debug_journey_select_item.py); unit tests
cover the select-intent / select-element predicates.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Page

from src.journey_scraper import JourneyScraper

# Unique per test file — xdist runs files in parallel workers (B-094 note in
# tests/adversarial: shared ports race with "Address already in use").
PORT = 8897
BASE_URL = f"http://localhost:{PORT}"


@pytest.fixture(scope="module")
def mock_server() -> Iterator[None]:
    from scripts.mock_server import MockServer

    with MockServer.start(port=PORT, directory="mock_sites/ambiguous"):
        yield


@pytest.fixture(scope="module")
def page(mock_server: None) -> Iterator[Page]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        yield pg
        browser.close()


def _scraper() -> JourneyScraper:
    return JourneyScraper(starting_url=f"{BASE_URL}/index.html")


class TestB103DiscoverSelectorOnAmbiguousMock:
    """The trace case, live: discovery on the ambiguous mock's index.html."""

    def test_select_item_resolves_to_the_dropdown_not_submit(self, page: Page) -> None:
        """'select item' must pick the <select id="item"> dropdown.

        Pre-fix: #item (role select) took the -20 whitelist penalty (raw 6 ->
        -14) and #place-order (role submit) won at 6 by iteration order.
        Post-fix: #item is whitelisted and gets the select-intent bonus.
        """
        page.goto(f"{BASE_URL}/index.html", wait_until="networkidle")
        page.wait_for_timeout(300)

        sel = _scraper()._discover_selector(page, "click", "select item")  # noqa: SLF001

        assert sel is not None
        assert sel == "#item", f"expected the #item dropdown, got {sel!r}"

    def test_place_order_still_resolves_to_the_submit_button(self, page: Page) -> None:
        """Regression: the real 'Place Order' step keeps its submit button.

        The whitelist addition and the select-intent bonus must not steal
        the submit button from a non-select description.
        """
        page.goto(f"{BASE_URL}/index.html", wait_until="networkidle")
        page.wait_for_timeout(300)

        sel = _scraper()._discover_selector(page, "click", "Place Order")  # noqa: SLF001

        assert sel is not None
        assert sel == "#place-order", f"expected the #place-order button, got {sel!r}"


class TestB103SelectIntentPredicates:
    """The bonus applies only to select-intent descriptions on dropdowns."""

    def test_has_select_intent_positive(self) -> None:
        assert JourneyScraper._has_select_intent("select item") is True
        assert JourneyScraper._has_select_intent("Choose an account") is True
        assert JourneyScraper._has_select_intent("pick a plan from the dropdown") is True

    def test_has_select_intent_negative(self) -> None:
        assert JourneyScraper._has_select_intent("Place Order") is False
        assert JourneyScraper._has_select_intent("click on a product") is False
        assert JourneyScraper._has_select_intent("add to cart") is False

    def test_is_select_element_positive(self) -> None:
        assert JourneyScraper._is_select_element({"tag": "select", "role": "select"}) is True
        # Accessibility enrichers may report the computed ARIA role.
        assert JourneyScraper._is_select_element({"tag": "select", "role": "combobox"}) is True
        assert JourneyScraper._is_select_element({"tag": "div", "role": "combobox"}) is True

    def test_is_select_element_negative(self) -> None:
        assert JourneyScraper._is_select_element({"tag": "button", "role": "submit"}) is False
        assert JourneyScraper._is_select_element({"tag": "a", "role": "link"}) is False
        assert JourneyScraper._is_select_element({"tag": "p", "role": "paragraph"}) is False

    def test_bonus_is_select_only_on_the_ambiguous_mock(self, page: Page) -> None:
        """A non-select description must NOT get the dropdown as its answer.

        'Place Order' (no select intent) on index.html resolves to the submit
        button, proving the +10 bonus is gated on the description as well as
        the element.
        """
        page.goto(f"{BASE_URL}/index.html", wait_until="networkidle")
        page.wait_for_timeout(300)

        sel = _scraper()._discover_selector(page, "click", "Place Order")  # noqa: SLF001

        assert sel is not None
        assert sel != "#item"
