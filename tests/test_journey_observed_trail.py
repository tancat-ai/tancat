"""AI-052 Session 1: observed transition trails (JourneyScraper capture).

Pure-capture tests: journey steps produce a typed ObservedTrail where every
URL is a fact read from ``page.url`` — never inferred. The live-faithful test
drives the real ``_scrape_journey_sync`` loop with a fake page object, and a
subprocess contract test covers the ``__trail__`` payload embedding.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from src.journey_models import JourneyResult, JourneyStep, ObservedStep, ObservedTrail
from src.journey_scraper import JourneyScraper

# ─── Fake Playwright stand-ins (faithful enough for the real loop) ───────────


class FakePage:
    """A fake Playwright page whose ``url`` and ``content()`` change on click.

    ``goto`` raises ``FakeGotoError`` for the "boom" URL so the retry/early-end
    path can be exercised. Clicking the title link simulates a real navigation
    (page.url changes), like saucedemo's product-title links.
    """

    def __init__(self) -> None:
        self.url = "http://fake"
        self._navigations = 0

    def set_default_timeout(self, _ms: int) -> None:
        return None

    def on(self, _event: str, _handler: Any = None) -> None:
        return None

    def goto(self, url: str, wait_until: str = "networkidle", timeout: int = 0) -> None:
        if "boom" in url:
            raise RuntimeError("boom")
        self.url = url
        return None

    def content(self) -> str:
        return "<html><body></body></html>"

    def title(self) -> str:
        return "fake"

    def wait_for_timeout(self, _ms: int) -> None:
        return None

    def wait_for_load_state(self, _state: str, timeout: int = 0) -> None:
        return None

    def evaluate(self, _code: Any) -> Any:
        return None

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def query_selector_all(self, _selector: str) -> list[Any]:
        return []

    def click(self, selector: str, timeout: int = 0) -> None:
        if selector == "#title_link":
            # Real transition: the click changes the page URL.
            self._navigations += 1
            self.url = "http://fake/inventory-item.html?id=4"


class FakeLocator:
    def __init__(self, page: FakePage, selector: str) -> None:
        self._page = page
        self._selector = selector

    def first(self) -> FakeLocator:
        return self

    def count(self) -> int:
        return 0 if "missing" in self._selector else 1

    def is_visible(self, timeout: int = 0) -> bool:
        return False

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        return None

    def click(self, timeout: int = 0) -> None:
        self._page.click(self._selector)

    def fill(self, _text: str) -> None:
        return None


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self) -> None:
        self.context = FakeContext()

    def new_context(self) -> FakeContext:
        return self.context

    def close(self) -> None:
        return None


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = self

    def launch(self, headless: bool = True) -> FakeBrowser:
        return FakeBrowser()

    def __enter__(self) -> FakePlaywright:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def _make_scraper() -> JourneyScraper:
    """A JourneyScraper whose scraping machinery is stubbed to no-ops."""
    scraper = JourneyScraper(starting_url="http://fake/home", max_retries=2, base_backoff_ms=0)
    scraper._scrape_current_page = lambda page, url, context=None: [{"selector": "a", "text": "x"}]  # type: ignore[method-assign]
    scraper._dismiss_consent_overlays = staticmethod(lambda page: None)  # type: ignore[method-assign,assignment]
    scraper._dismiss_modals = staticmethod(lambda page: None)  # type: ignore[method-assign]
    scraper._discover_selector = lambda page, action, desc: "#title_link"  # type: ignore[method-assign,assignment]
    scraper._discover_selector_relaxed = lambda page, action, desc: None  # type: ignore[method-assign,assignment]
    scraper._infer_url_from_description = staticmethod(lambda desc, url: None)  # type: ignore[method-assign,assignment]
    scraper._try_quantity_stepper_fallback = lambda page, step: False  # type: ignore[method-assign,assignment]
    scraper._click_selector = staticmethod(lambda page, sel, ms: page.click(sel))  # type: ignore[method-assign,assignment]
    scraper._fill_selector = staticmethod(lambda page, sel, text, ms: None)  # type: ignore[method-assign,assignment]
    # No DNS in tests: the SSRF guard resolves the starting host eagerly.
    scraper._url_guard_patched = True  # type: ignore[attr-defined]
    return scraper


# ─── Data model ───────────────────────────────────────────────────────────────


def test_observed_step_fields() -> None:
    step = ObservedStep(
        index=0,
        action="click",
        description="add to cart",
        selector_used="#add",
        from_url="http://a",
        to_url="http://b",
        navigated=True,
        scraped=True,
        error=None,
    )
    assert step.index == 0
    assert step.action == "click"
    assert step.selector_used == "#add"
    assert step.navigated is True
    assert step.scraped is True
    assert step.error is None


def test_observed_trail_pages_visited_ordered_deduped() -> None:
    trail = ObservedTrail(
        steps=[
            ObservedStep(0, "navigate", to_url="http://a", navigated=True, scraped=True),
            ObservedStep(1, "click", from_url="http://a", to_url="http://b", navigated=True, scraped=True),
            ObservedStep(2, "scrape", from_url="http://b", to_url="http://b"),
        ]
    )
    assert trail.pages_visited == ["http://a", "http://b"]


def test_observed_trail_empty_when_no_steps() -> None:
    trail = ObservedTrail()
    assert trail.steps == []
    assert trail.pages_visited == []


def test_observed_trail_to_dict_round_trip() -> None:
    trail = ObservedTrail(steps=[ObservedStep(0, "click", description="x", to_url="http://b", error="nope")])
    restored = ObservedTrail.from_dict(trail.to_dict())
    assert restored.steps[0].to_url == "http://b"
    assert restored.steps[0].error == "nope"


def test_journey_result_carries_trail_round_trip() -> None:
    result = JourneyResult(
        success=True,
        captured_pages={"http://b": []},
        failed_steps=[],
        trail=ObservedTrail(steps=[ObservedStep(0, "navigate", to_url="http://b")]),
    )
    restored = JourneyResult.from_dict(result.to_dict())
    assert restored.trail is not None
    assert restored.trail.pages_visited == ["http://b"]


def test_journey_result_from_dict_without_trail_key() -> None:
    # Back-compat: payloads from older processes have no "trail" key.
    restored = JourneyResult.from_dict({"success": True, "captured_pages": {}, "failed_steps": []})
    assert restored.trail is None


# ─── Live-faithful capture through the real _scrape_journey_sync loop ────────


def test_trail_captures_navigate_click_scrape_sequence() -> None:
    """navigate -> click(navigates) -> scrape yields 3 steps with correct URLs."""
    scraper = _make_scraper()

    import src.journey_scraper as js_mod

    real_sync_playwright = js_mod.sync_playwright
    js_mod.sync_playwright = lambda: FakePlaywright()  # type: ignore[assignment,return-value]
    try:
        output = scraper._scrape_journey_sync(
            [
                JourneyStep(action="navigate", url="http://fake/products", description="products"),
                JourneyStep(action="click", description="view product"),
                JourneyStep(action="scrape", description="final page state"),
            ]
        )
    finally:
        js_mod.sync_playwright = real_sync_playwright

    trail = scraper.get_observed_trail()
    assert [s.index for s in trail.steps] == [0, 1, 2]

    nav, click, scrape = trail.steps
    # Step 0: navigate from the starting page to /products.
    assert nav.action == "navigate"
    assert nav.from_url == "http://fake/home"
    assert nav.to_url == "http://fake/products"
    assert nav.navigated is False  # from_url == to_url is False here, but step 0 is special
    assert nav.scraped is True
    assert nav.error is None
    # Step 1: the click caused a real navigation (title link -> detail page).
    assert click.action == "click"
    assert click.from_url == "http://fake/products"
    assert click.to_url == "http://fake/inventory-item.html?id=4"
    assert click.navigated is True
    assert click.scraped is True  # destination page was scraped into output
    assert click.selector_used == "#title_link"
    # Step 2: scrape does not navigate.
    assert scrape.action == "scrape"
    assert scrape.to_url == "http://fake/inventory-item.html?id=4"
    assert scrape.navigated is False
    assert scrape.scraped is True

    # The trail agrees with the scraped output and the legacy getter.
    # The starting page is in output but not in the trail (it was scraped
    # before any journey step ran) — that's by design.
    assert set(trail.pages_visited).issubset(set(output.keys()))
    assert trail.pages_visited == [u for u in scraper.get_pages_visited() if u != "http://fake/home"]


def test_trail_early_end_on_locator_failure() -> None:
    """A click that finds no locator records an error step and the trail ends."""
    scraper = _make_scraper()
    scraper._discover_selector = lambda page, action, desc: None  # type: ignore[method-assign,assignment]

    import src.journey_scraper as js_mod

    real_sync_playwright = js_mod.sync_playwright
    js_mod.sync_playwright = lambda: FakePlaywright()  # type: ignore[assignment,return-value]
    try:
        output = scraper._scrape_journey_sync(
            [
                JourneyStep(action="click", description="checkout button"),
                JourneyStep(action="scrape", description="final page state"),
            ]
        )
    finally:
        js_mod.sync_playwright = real_sync_playwright

    trail = scraper.get_observed_trail()
    assert len(trail.steps) == 2
    failed = trail.steps[0]
    assert failed.action == "click"
    assert failed.error is not None  # recorded from the exception path
    # A skipped click never navigates.
    assert failed.navigated is False
    # The skip is also visible in the legacy context log.
    assert any(e.get("event") == "step_skipped" for e in scraper._context_log)
    assert set(output.keys()) == set(trail.pages_visited)


def test_trail_error_set_when_navigation_raises() -> None:
    """A step that raises after retries records the error on the trail step."""
    scraper = _make_scraper()

    import src.journey_scraper as js_mod

    real_sync_playwright = js_mod.sync_playwright
    js_mod.sync_playwright = lambda: FakePlaywright()  # type: ignore[assignment,return-value]
    try:
        scraper._scrape_journey_sync([JourneyStep(action="navigate", url="http://fake/boom", description="broken")])
    finally:
        js_mod.sync_playwright = real_sync_playwright

    trail = scraper.get_observed_trail()
    assert len(trail.steps) == 1
    step = trail.steps[0]
    assert step.error is not None
    assert "boom" in step.error
    assert step.navigated is False


def test_get_observed_trail_empty_before_journey() -> None:
    scraper = _make_scraper()
    assert scraper.get_observed_trail().steps == []
    assert scraper.get_observed_trail().pages_visited == []


# ─── Subprocess contract ──────────────────────────────────────────────────────


def test_subprocess_embeds_trail_in_payload() -> None:
    """The subprocess entry embeds the trail under ``__trail__`` in stdout."""
    import io
    from contextlib import redirect_stdout

    import src.journey_subprocess as jp_mod

    real_sync = JourneyScraper._scrape_journey_sync

    def fake_sync(self: JourneyScraper, steps: list[JourneyStep], **_kw: Any) -> dict:
        return {"http://a": [{"selector": "a"}]}

    JourneyScraper._scrape_journey_sync = fake_sync  # type: ignore[assignment]

    payload = {
        "starting_url": "",
        "steps": [{"action": "scrape", "description": "x"}],
        "timeout_ms": 1000,
    }
    real_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            jp_mod.run_journey_subprocess_entry()
    finally:
        sys.stdin = real_stdin
        JourneyScraper._scrape_journey_sync = real_sync  # type: ignore[assignment]

    data = json.loads(buf.getvalue())
    assert "__trail__" in data
    assert data["__trail__"]["steps"] == []
    assert data["http://a"] == [{"selector": "a"}]
