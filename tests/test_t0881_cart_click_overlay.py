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

Each of the three mechanisms is pinned by its OWN test, because they can mask
one another (t-0884 review: deleting the retry, or restoring the old comma
selector, changed no result while the others were in place):

- ``test_the_dismiss_selector_never_resolves_to_the_modal_container`` - the
  shared dismissal itself.
- ``test_the_journey_dismiss_helper_really_dismisses_the_modal`` - the journey
  delegate ``_dismiss_modals`` (catches a revert to the comma-joined selector).
- ``test_a_scrape_does_not_resurrect_a_dismissed_modal`` - the reveal exclusion.
- the four ``click retry`` tests - the retry in isolation (fires once, second
  interception still raises, a non-interception error is not retried, and
  ``_click_selector`` really goes through it).
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from typing import Any, cast

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

import src.browser_utils as browser_utils
from scripts.mock_server import MockServer
from src.browser_utils import MODAL_CONTAINERS, click_with_overlay_retry, dismiss_blocking_modals
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


# ---------------------------------------------------------------------------
# The retry, exercised on its own (t-0884 review: it was masked by the
# dismissal, so mutation "delete the retry" changed no test result)
# ---------------------------------------------------------------------------


def _interception() -> RuntimeError:
    """The error Playwright raises while an overlay covers the click point."""
    return RuntimeError(
        "Locator.click: Timeout 5000ms exceeded.\nCall log:\n"
        '  - <div id="cartModal" class="modal show">...</div> from <section>...</section> '
        "subtree intercepts pointer events"
    )


class _ScriptedLocator:
    """A locator whose ``click`` follows a script: ``None`` succeeds, an error raises."""

    def __init__(self, script: list[Exception | None]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    def click(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        outcome = self._script.pop(0) if self._script else None
        if outcome is not None:
            raise outcome

    def count(self) -> int:
        return 1


class _FakePage:
    """Just enough page for ``JourneyScraper._click_selector``: ``locator(sel).first``."""

    def __init__(self, locator: _ScriptedLocator) -> None:
        self._locator = locator

    def locator(self, _selector: str) -> _FakePage:
        return self

    @property
    def first(self) -> _ScriptedLocator:
        return self._locator

    def wait_for_timeout(self, _ms: int) -> None:
        return None


def _page_double() -> Page:
    """A Page double for the retry tests (B-059 precedent: cast, never a blanket ignore).

    These tests monkeypatch ``dismiss_consent_overlays`` / ``dismiss_blocking_modals``
    on ``src.browser_utils``, so the page is never touched: it is only carried
    through to those two functions. The cast states that the double serves the
    part of ``Page`` the code under test uses.
    """
    return cast(Page, _FakePage(_ScriptedLocator([])))


def test_the_click_retry_fires_once_after_an_interception(monkeypatch: pytest.MonkeyPatch) -> None:
    """One interception -> dismiss -> the SAME click again, once."""
    dismissals: list[str] = []
    monkeypatch.setattr(browser_utils, "dismiss_consent_overlays", lambda _page: dismissals.append("consent"))
    monkeypatch.setattr(browser_utils, "dismiss_blocking_modals", lambda _page: dismissals.append("modal"))
    locator = _ScriptedLocator([_interception(), None])
    logs: list[str] = []

    click_with_overlay_retry(_page_double(), locator, 1000, log=logs.append)

    assert len(locator.calls) == 2, "the retry must attempt exactly one more click"
    assert dismissals == ["consent", "modal"], "the retry must dismiss before the second attempt"
    assert any("intercepted" in line for line in logs)
    for call in locator.calls:
        assert "force" not in call, "the retry must keep full actionability (no force click)"


def test_the_retry_re_raises_on_a_second_interception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A click that still cannot land must raise - never be swallowed."""
    monkeypatch.setattr(browser_utils, "dismiss_consent_overlays", lambda _page: None)
    monkeypatch.setattr(browser_utils, "dismiss_blocking_modals", lambda _page: None)
    locator = _ScriptedLocator([_interception(), _interception()])

    with pytest.raises(RuntimeError, match="intercepts pointer events"):
        click_with_overlay_retry(_page_double(), locator, 1000)

    assert len(locator.calls) == 2, "the retry is one extra attempt, not a loop"


def test_a_non_interception_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry is narrow: a missing/detached element is not re-clicked."""
    dismissals: list[int] = []
    monkeypatch.setattr(browser_utils, "dismiss_consent_overlays", lambda _page: dismissals.append(1))
    monkeypatch.setattr(browser_utils, "dismiss_blocking_modals", lambda _page: dismissals.append(1))
    locator = _ScriptedLocator([RuntimeError("Locator.click: Timeout 5000ms exceeded.\n - locator not found")])

    with pytest.raises(RuntimeError):
        click_with_overlay_retry(_page_double(), locator, 1000)

    assert len(locator.calls) == 1
    assert dismissals == []


def test_click_selector_goes_through_the_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wiring: ``_click_selector`` must use the retry, not a bare second click."""
    seen: dict[str, Any] = {}

    def spy(_page: Any, locator: Any, timeout_ms: int, *, log: Any = None) -> None:  # noqa: ARG001
        seen["called"] = True
        seen["timeout"] = timeout_ms
        return None

    monkeypatch.setattr(browser_utils, "click_with_overlay_retry", spy)
    monkeypatch.setattr(JourneyScraper, "_reveal_hidden_sections", staticmethod(lambda _page: None))
    monkeypatch.setattr(JourneyScraper, "_dismiss_consent_overlays", staticmethod(lambda _page: None))
    monkeypatch.setattr(JourneyScraper, "_dismiss_modals", staticmethod(lambda _page: None))

    page = _FakePage(_ScriptedLocator([_interception()]))
    JourneyScraper(starting_url="http://localhost/")._click_selector(page, "#x", 1000)  # noqa: SLF001

    assert seen.get("called") is True, "_click_selector swallowed the interception instead of retrying"


def test_the_journey_dismiss_helper_really_dismisses_the_modal(browser: Browser) -> None:
    """The journey's ``_dismiss_modals`` itself (a revert to the comma selector fails here).

    ``dismiss_blocking_modals`` is covered directly above; this pins the journey
    delegate, which is where the t-0881 comma-joined selector lived.
    """
    page = _open_products(browser)
    page.click('.add-to-cart[data-product-id="1"]')
    page.wait_for_timeout(200)
    assert page.evaluate(_MODAL_STATE) == "block"

    JourneyScraper._dismiss_modals(page)

    assert page.evaluate(_MODAL_STATE) == "none", "_dismiss_modals clicked the modal box instead of its control"
    page.close()
