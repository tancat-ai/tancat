from __future__ import annotations

import asyncio
import json
from subprocess import CompletedProcess
from typing import Any

import pytest

from src.journey_scraper import CredentialProfile
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
    parsed_input = json.loads(kwargs["input"])
    assert parsed_input["starting_url"] == "https://example.com/"
    assert parsed_input["timeout_ms"] == 30000
    assert parsed_input["urls"] == ["https://example.com/view_cart"]


def test_scrape_urls_returns_empty_results_when_subprocess_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        return CompletedProcess(args=args[0], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("src.stateful_scraper.subprocess.run", fake_run)

    scraper = StatefulPageScraper("https://example.com/")
    result = asyncio.run(scraper.scrape_urls(["https://example.com/checkout"]))

    assert result == {"https://example.com/checkout": []}


def test_init_with_credential_profile() -> None:
    profile = CredentialProfile(label="saucedemo", username="standard_user", password="secret_sauce")
    scraper = StatefulPageScraper("https://www.saucedemo.com", credential_profile=profile)

    assert scraper._credential_profile is profile
    # Access through the profile variable to avoid mypy narrowing issues
    assert profile.username == "standard_user"
    assert profile.password == "secret_sauce"


def test_init_without_credential_profile() -> None:
    scraper = StatefulPageScraper("https://example.com/")

    assert scraper._credential_profile is None


def test_scrape_urls_passes_credential_profile_to_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        payload = {
            "https://example.com/": [{"selector": "#hero", "text": "Hero", "role": "region"}],
        }
        return CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("src.stateful_scraper.subprocess.run", fake_run)

    profile = CredentialProfile(label="test", username="testuser", password="testpass")
    scraper = StatefulPageScraper("https://example.com/", credential_profile=profile)
    asyncio.run(scraper.scrape_urls(["https://example.com/"]))

    parsed_input = json.loads(captured["kwargs"]["input"])
    assert parsed_input["credential_profile"] == {
        "label": "test",
        "username": "testuser",
        "password": "testpass",
    }


def test_scrape_urls_omits_credential_profile_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        payload: dict[str, list[dict[str, str]]] = {"https://example.com/": []}
        return CompletedProcess(args=args[0], returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("src.stateful_scraper.subprocess.run", fake_run)

    scraper = StatefulPageScraper("https://example.com/")
    asyncio.run(scraper.scrape_urls(["https://example.com/"]))

    parsed_input = json.loads(captured["kwargs"]["input"])
    assert "credential_profile" not in parsed_input
