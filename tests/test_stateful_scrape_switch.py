from __future__ import annotations

import asyncio

import pytest

from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


def test_ensure_scraped_uses_stateful_scraper_for_view_cart(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = TestOrchestrator(TestGenerator(client=None, model_name="test"))  # type: ignore[arg-type]
    orchestrator._starting_url = "https://example.com/"  # noqa: SLF001

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

    monkeypatch.setattr("src.orchestrator.StatefulPageScraper", FakeStateful)
    monkeypatch.setattr(orchestrator.scraper, "scrape_url", fake_stateless)

    scraped: dict[str, list[dict[str, str]]] = {}
    asyncio.run(orchestrator._ensure_scraped("https://example.com/view_cart", scraped))  # noqa: SLF001

    assert "stateful:https://example.com/view_cart" in calls
    assert all(not c.startswith("stateless:") for c in calls)
    assert scraped["https://example.com/view_cart"][0]["selector"] == 'a[href="/checkout"]'


def test_ensure_scraped_falls_back_to_stateless_when_stateful_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = TestOrchestrator(TestGenerator(client=None, model_name="test"))  # type: ignore[arg-type]
    orchestrator._starting_url = "https://example.com/"  # noqa: SLF001

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

    monkeypatch.setattr("src.orchestrator.StatefulPageScraper", FakeStateful)
    monkeypatch.setattr(orchestrator.scraper, "scrape_url", fake_stateless)

    scraped: dict[str, list[dict[str, str]]] = {}
    asyncio.run(orchestrator._ensure_scraped("https://example.com/checkout", scraped))  # noqa: SLF001

    assert "stateful:https://example.com/checkout" in calls
    assert "stateless:https://example.com/checkout" in calls
    assert scraped["https://example.com/checkout"][0]["text"] == "fallback"
