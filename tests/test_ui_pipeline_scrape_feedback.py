"""Tests for src/ui_pipeline.scrape_feedback (F2).

The Streamlit UI renders ``pipeline_scraper_warnings``,
``pipeline_scraper_errors`` and ``pipeline_journey_captured_count``. Before
F2 nothing populated them, so a failed scrape looked clean. These tests pin
the derivation from a pipeline result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.ui_pipeline import scrape_feedback


@dataclass
class _FakeResult:
    """Stand-in for src.orchestrator.PipelineRunResult."""

    scraped_errors: dict[str, str] = field(default_factory=dict)
    scraped_pages: dict[str, list[Any]] = field(default_factory=dict)
    pages_visited: list[str] = field(default_factory=list)
    pipeline_diagnostics: dict[str, Any] = field(default_factory=dict)


def test_none_result_yields_empty_feedback() -> None:
    assert scrape_feedback(None) == ([], [], 0)


def test_per_url_scrape_errors_are_reported_and_blanks_dropped() -> None:
    result = _FakeResult(scraped_errors={"https://a.example/": "timeout", "https://b.example/": ""})
    warnings, errors, captured = scrape_feedback(result)
    assert warnings == []
    assert errors == ["https://a.example/: timeout"]
    assert captured == 0


def test_journey_diagnostics_become_warnings() -> None:
    result = _FakeResult(
        pipeline_diagnostics={
            "journey_error": "login failed",
            "journey_failed_steps": ["fill #user", "click Log in"],
            "auth_redirects": ["https://a.example/login -> https://a.example/home"],
        }
    )
    warnings, errors, captured = scrape_feedback(result)
    assert warnings == [
        "login failed",
        "journey step(s) failed: fill #user, click Log in",
        "redirected to another page: https://a.example/login -> https://a.example/home",
    ]
    assert errors == []
    assert captured == 0


def test_captured_count_prefers_pages_visited() -> None:
    result = _FakeResult(
        pages_visited=["https://a.example/", "https://b.example/"],
        scraped_pages={"https://c.example/": [1]},
    )
    _, _, captured = scrape_feedback(result)
    assert captured == 2


def test_captured_count_falls_back_to_pages_with_elements() -> None:
    result = _FakeResult(
        scraped_pages={"https://a.example/": [1], "https://b.example/": [], "https://c.example/": [1, 2]}
    )
    _, _, captured = scrape_feedback(result)
    assert captured == 2
