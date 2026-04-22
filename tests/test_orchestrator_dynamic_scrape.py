from __future__ import annotations

import asyncio

import pytest

from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


def test_resolve_placeholder_scrapes_current_url_on_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    """If a journey lands on a URL not yet scraped, orchestrator should scrape it."""
    orchestrator = TestOrchestrator(TestGenerator(client=None, model_name="test"))  # type: ignore[arg-type]

    calls: list[str] = []

    async def fake_scrape_url(url: str) -> tuple[list[dict[str, str]], str | None, str]:
        calls.append(url)
        return (
            [{"selector": 'a[href="/products"]', "text": "Products", "href": "https://example.com/products"}],
            None,
            url,
        )

    monkeypatch.setattr(orchestrator.scraper, "scrape_url", fake_scrape_url)

    scraped_data: dict[str, list[dict[str, str]]] = {}
    _selector, next_url = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            "CLICK",
            "products link",
            "https://example.com/",
            scraped_data,
        )
    )

    assert calls[0] == "https://example.com/"
    assert "https://example.com/" in scraped_data
    assert next_url in (None, "https://example.com/products")
