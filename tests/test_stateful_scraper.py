from __future__ import annotations

import asyncio
import json
from subprocess import CompletedProcess
from typing import Any

import pytest

from src.stateful_scraper import StatefulPageScraper


def test_scrape_urls_uses_subprocess_payload_and_parses_output(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        payload = {
            "https://example.com/view_cart": [{"selector": "#checkout", "text": "Checkout"}],
        }
        return CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("src.stateful_scraper.subprocess.run", fake_run)

    scraper = StatefulPageScraper("https://example.com/")
    result = asyncio.run(scraper.scrape_urls(["https://example.com/view_cart"]))

    assert result["https://example.com/view_cart"][0]["selector"] == "#checkout"
    kwargs = captured["kwargs"]
    assert json.loads(kwargs["input"]) == {
        "starting_url": "https://example.com/",
        "timeout_ms": 30000,
        "urls": ["https://example.com/view_cart"],
    }


def test_scrape_urls_returns_empty_results_when_subprocess_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        return CompletedProcess(args=args[0], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("src.stateful_scraper.subprocess.run", fake_run)

    scraper = StatefulPageScraper("https://example.com/")
    result = asyncio.run(scraper.scrape_urls(["https://example.com/checkout"]))

    assert result == {"https://example.com/checkout": []}
