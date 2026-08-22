"""AI-052 Session 2: plumb the observed trail into the resolver (no behaviour change)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.journey_models import JourneyStep, ObservedStep, ObservedTrail
from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator


def _make_trail() -> ObservedTrail:
    return ObservedTrail(
        steps=[
            ObservedStep(0, "navigate", to_url="http://a", navigated=True, scraped=True),
            ObservedStep(1, "click", from_url="http://a", to_url="http://b", navigated=True, scraped=True),
        ]
    )


def _make_test_journey(name: str = "test_journey") -> TestJourney:
    placeholder = PlaceholderUse(token="{{GOTO:x}}", action="GOTO", description="x", line_number=1, raw_line="step")
    step = TestStep(line_number=1, raw_line="step", placeholders=[placeholder])
    return TestJourney(test_name=name, start_line=1, end_line=2, steps=[step])


def _orch() -> PlaceholderOrchestrator:
    return PlaceholderOrchestrator()


def test_scrape_journeys_statefully_returns_trail() -> None:
    from src import orchestrator as orch_mod
    from src.orchestrator import TestOrchestrator

    orchestrator = TestOrchestrator.__new__(TestOrchestrator)
    orchestrator._starting_url_list = ["http://a"]  # type: ignore[attr-defined]
    orchestrator._debug = lambda msg: None  # type: ignore[method-assign,assignment]
    # _resolver is a property backed by _placeholder_orchestrator.resolver -
    # patch the backing attribute (the property has no setter).
    orchestrator._placeholder_orchestrator = type("P", (), {})()  # type: ignore[attr-defined]
    orchestrator._placeholder_orchestrator.resolver = type(  # type: ignore[attr-defined]
        "R", (), {"resolve_url": staticmethod(lambda *a, **kw: "http://b")}
    )()

    known_trail = _make_trail()

    async def fake_scrape_journey(self: Any, steps: list[JourneyStep], **_kw: Any) -> dict[str, list[dict[str, Any]]]:
        return {"http://a": [], "http://b": []}

    def fake_get_pages_visited(self: Any) -> list[str]:
        return ["http://a", "http://b"]

    def fake_get_observed_trail(self: Any) -> ObservedTrail:
        return known_trail

    with (
        patch.object(orch_mod.JourneyScraper, "scrape_journey", fake_scrape_journey),
        patch.object(orch_mod.JourneyScraper, "get_pages_visited", fake_get_pages_visited),
        patch.object(orch_mod.JourneyScraper, "get_observed_trail", fake_get_observed_trail),
    ):
        scraped_data, pages_visited, observed_trails = asyncio.run(
            orchestrator._scrape_journeys_statefully([_make_test_journey("test_alpha")], "http://a")
        )

    assert "test_alpha" in observed_trails
    assert observed_trails["test_alpha"].pages_visited == ["http://a", "http://b"]
    assert scraped_data == {"http://a": [], "http://b": []}
    assert pages_visited == ["http://a", "http://b"]


def test_replace_placeholders_logs_observed_trail(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_DEBUG", "1")
    orch = _orch()
    orch._resolve_placeholder_for_page = AsyncMock(return_value=("http://b", "http://b", None))  # type: ignore[method-assign]
    journey = _make_test_journey("test_alpha")
    skeleton = "def test_alpha():\n    pass\n"

    asyncio.run(
        orch._replace_placeholders_sequentially(
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=["http://a"],
            scraped_data={"http://a": []},
            observed_trails={"test_alpha": _make_trail()},
        )
    )

    captured = capsys.readouterr()
    assert "observed trail" in captured.err
    assert "test_alpha" in captured.err
    assert "http://a" in captured.err
    assert "http://b" in captured.err
    assert "->" in captured.err


def test_replace_placeholders_no_trail_log_without_debug_flag(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trail line is gated on PIPELINE_DEBUG (matches pipeline convention)."""
    monkeypatch.delenv("PIPELINE_DEBUG", raising=False)
    orch = _orch()
    orch._resolve_placeholder_for_page = AsyncMock(return_value=("http://b", "http://b", None))  # type: ignore[method-assign]
    journey = _make_test_journey("test_alpha")
    skeleton = "def test_alpha():\n    pass\n"

    asyncio.run(
        orch._replace_placeholders_sequentially(
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=["http://a"],
            scraped_data={"http://a": []},
            observed_trails={"test_alpha": _make_trail()},
        )
    )
    captured = capsys.readouterr()
    assert "observed trail" not in captured.err


def test_replace_placeholders_back_compat_no_trails() -> None:
    orch = _orch()
    orch._resolve_placeholder_for_page = AsyncMock(return_value=("http://b", "http://b", None))  # type: ignore[method-assign]
    journey = _make_test_journey("test_backcompat")
    skeleton = "def test_backcompat():\n    pass\n"

    result = asyncio.run(
        orch._replace_placeholders_sequentially(
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=["http://a"],
            scraped_data={"http://a": []},
        )
    )
    assert isinstance(result, str)


def test_pipeline_run_result_carries_observed_trails() -> None:
    from src.orchestrator import PipelineRunResult

    result = PipelineRunResult()
    assert result.observed_trails == {}
    result2 = PipelineRunResult(observed_trails={"t": _make_trail()})
    assert result2.observed_trails["t"].pages_visited == ["http://a", "http://b"]
