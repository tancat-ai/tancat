"""t-0881: the cart link's click must land - an open confirmation modal used to eat it.

Found by the 2026-10-24 measurement (j-0196). The journey resolved the cart
link, logged ``Attempting to click selector: a[href="/cart.html"]``, and then
died with ``Locator.click: Timeout 5000ms exceeded`` because the page's own
"Added to cart" modal (``#cartModal``) - opened by the preceding click - was
still covering the header:

    <div id="cartModal" class="modal show">...</div> from <section>...</section>
    subtree intercepts pointer events

Two causes, each pinned by its own test here:

1. ``JourneyScraper._dismiss_modals`` built ONE selector string -
   ``"#cartModal, .modal, [role='dialog'], .modal-dialog, .modal-content
   button:has-text('Continue Shopping')"``. CSS reads that as a selector LIST,
   so ``.first`` was the modal ``div`` itself: the "dismiss" clicked the modal
   box, returned, and the modal kept intercepting.
2. ``_reveal_hidden_sections`` (run by every scrape) forced every inline
   ``display: none`` element back to ``block`` - including a modal that had
   just been dismissed - so the overlay came back before the next click.

The last test is the control: an overlay nobody can dismiss must still make the
click RAISE. The retry added here uses the same actionability rules as the
first attempt (no ``force=True``) and never turns an unlanded click into a pass.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from scripts.mock_server import MockServer
from src.browser_utils import MODAL_CONTAINERS, dismiss_blocking_modals
from src.journey_models import JourneyStep, ObservedStep
from src.journey_scraper import JourneyScraper

PORT = 8791
BASE = f"http://localhost:{PORT}"

_MODAL_STATE = (
    "() => { const m = document.getElementById('cartModal'); return m ? getComputedStyle(m).display : null; }"
)


@pytest.fixture(scope="module")
def mock_site() -> Iterator[None]:
    with MockServer.start(port=PORT, directory="mock_sites/ecommerce"):
        yield


@pytest.fixture(scope="module")
def browser(mock_site: None) -> Generator[Browser]:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _open_products(browser: Browser) -> Page:
    page = browser.new_page()
    page.goto(f"{BASE}/products.html", wait_until="networkidle")
    return page


def _scraper() -> JourneyScraper:
    scraper = JourneyScraper(starting_url=f"{BASE}/products.html")
    # Localhost mock: the SSRF guard is for internal endpoints, not tests.
    scraper._url_guard_patched = True  # type: ignore[attr-defined]
    return scraper


def test_the_dismiss_selector_never_resolves_to_the_modal_container(browser: Browser) -> None:
    """Cause 1: the dismiss control must be the button, not the modal box.

    The old comma-joined selector made ``.first`` the ``#cartModal`` div, and
    clicking a container is a no-op - so the modal was never dismissed.
    """
    page = _open_products(browser)
    page.click('.add-to-cart[data-product-id="1"]')
    page.wait_for_timeout(200)
    assert page.evaluate(_MODAL_STATE) == "block"

    assert dismiss_blocking_modals(page) is True
    assert page.evaluate(_MODAL_STATE) == "none", "the dismissal clicked the modal box, not its control"

    # Every container constant must still be usable on its own (a comma-joined
    # string is what broke this before).
    for container in MODAL_CONTAINERS:
        page.locator(f"{container} button").count()  # must not raise a CSS error
    page.close()


def test_a_scrape_does_not_resurrect_a_dismissed_modal(browser: Browser) -> None:
    """Cause 2: revealing hidden SPA sections must leave overlays hidden."""
    page = _open_products(browser)
    page.click('.add-to-cart[data-product-id="1"]')
    page.wait_for_timeout(200)
    page.click("#cartModal .close-modal")
    page.wait_for_timeout(200)
    assert page.evaluate(_MODAL_STATE) == "none"

    JourneyScraper._reveal_hidden_sections(page)

    assert page.evaluate(_MODAL_STATE) == "none", "the scrape re-opened the dismissed modal"
    page.close()


def _run_cart_journey() -> tuple[dict[str, list[dict[str, Any]]], list[ObservedStep]]:
    """Run the real sync journey loop (own thread: it starts its own sync Playwright)."""
    trail: list[ObservedStep] = []
    output = _scraper()._scrape_journey_sync(  # noqa: SLF001
        [
            JourneyStep(
                action="click",
                selector='.add-to-cart[data-product-id="1"]',
                description="Add to cart",
            ),
            JourneyStep(action="click", selector='a[href="/cart.html"]', description="Cart"),
        ],
        _observed_trail_out=trail,
    )
    return output, trail


def test_cart_link_click_lands_and_the_cart_page_is_captured(mock_site: None) -> None:
    """The defect itself: add to cart -> scrape -> click Cart must navigate."""
    # The sync Playwright API cannot be entered on a thread that already owns an
    # event loop (pytest-asyncio), and production runs this loop in a subprocess
    # anyway - so give it its own thread, as the real pipeline does.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        output, trail = pool.submit(_run_cart_journey).result(timeout=180)

    assert f"{BASE}/cart.html" in output, f"the cart page was never captured (pages: {sorted(output)})"
    cart_step = trail[-1]
    assert cart_step.description == "Cart"
    assert cart_step.navigated is True, "the cart click was recorded as a non-navigation"
    assert cart_step.to_url == f"{BASE}/cart.html"
    # The page really is the cart page, not a stale products page under a new URL.
    assert any(el.get("selector", "").startswith("#cart") for el in output[f"{BASE}/cart.html"]) or any(
        "cart" in str(el.get("text", "")).lower() for el in output[f"{BASE}/cart.html"]
    )


def test_an_undismissable_overlay_still_fails_loudly(browser: Browser) -> None:
    """Control: no force click, no swallowing - a blocked click still raises."""
    page = _open_products(browser)
    page.evaluate(
        """
        () => {
            const wall = document.createElement('div');
            wall.id = 'undismissable-wall';
            wall.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.2)';
            document.body.appendChild(wall);
        }
        """
    )
    scraper = _scraper()
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - playwright's error type varies by version
        scraper._click_selector(page, 'a[href="/cart.html"]', 1000)  # noqa: SLF001
    assert "intercepts pointer events" in str(excinfo.value)
    assert not page.url.endswith("/cart.html"), "the click passed although the link was covered"
    page.close()
