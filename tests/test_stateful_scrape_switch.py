from __future__ import annotations

import asyncio

import pytest

from src.placeholder_orchestrator import PlaceholderOrchestrator


def test_ensure_scraped_uses_stateful_scraper_for_view_cart(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify stateful scraping is used for cart/checkout pages."""
    placeholder_orch = PlaceholderOrchestrator(starting_url="https://example.com/")

    calls: list[str] = []

    class FakeStateful:
        def __init__(self, starting_url: str) -> None:
            calls.append(f"init:{starting_url}")

        async def scrape_url(self, url: str) -> list[dict[str, str]]:
            calls.append(f"stateful:{url}")
            return [{"selector": 'a[href="/checkout"]', "text": "Proceed To Checkout"}]

    async def fake_stateless(url: str) -> tuple[list[dict[str, str]], str | None, str]:
        calls.append(f"stateless:{url}")
        return [{"selector": "div", "text": "fallback"}], None, url

    monkeypatch.setattr("src.placeholder_orchestrator.StatefulPageScraper", FakeStateful)

    # Mock the stateless scraper on the placeholder orchestrator
    placeholder_orch.scraper.scrape_url = fake_stateless  # type: ignore[assignment]

    scraped: dict[str, list[dict[str, str]]] = {}
    asyncio.run(placeholder_orch._ensure_scraped("https://example.com/view_cart", scraped))

    assert "stateful:https://example.com/view_cart" in calls
    assert all(not c.startswith("stateless:") for c in calls)
    assert scraped["https://example.com/view_cart"][0]["selector"] == 'a[href="/checkout"]'


def test_ensure_scraped_falls_back_to_stateless_when_stateful_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify stateless fallback when stateful scraper returns 0 elements."""
    placeholder_orch = PlaceholderOrchestrator(starting_url="https://example.com/")

    calls: list[str] = []

    class FakeStateful:
        def __init__(self, starting_url: str) -> None:
            calls.append(f"init:{starting_url}")

        async def scrape_url(self, url: str) -> list[dict[str, str]]:
            calls.append(f"stateful:{url}")
            return []

    async def fake_stateless(url: str) -> tuple[list[dict[str, str]], str | None, str]:
        calls.append(f"stateless:{url}")
        return [{"selector": "div", "text": "fallback"}], None, url

    monkeypatch.setattr("src.placeholder_orchestrator.StatefulPageScraper", FakeStateful)

    # Mock the stateless scraper on the placeholder orchestrator
    placeholder_orch.scraper.scrape_url = fake_stateless  # type: ignore[assignment]

    scraped: dict[str, list[dict[str, str]]] = {}
    asyncio.run(placeholder_orch._ensure_scraped("https://example.com/checkout", scraped))

    assert "stateful:https://example.com/checkout" in calls
    assert "stateless:https://example.com/checkout" in calls
    assert scraped["https://example.com/checkout"][0]["text"] == "fallback"
