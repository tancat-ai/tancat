"""Unit tests for ``scripts/eval/compare_model_baselines.py``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.eval.compare_model_baselines import (
    aggregate_deltas,
    build_report,
    compare,
    index_stories,
    load_baseline,
    story_improved,
    story_regressed,
)


def _baseline(stories: list[dict]) -> dict:
    return {
        "model": "test-model",
        "runtime": {},
        "codebase": {"commit": "abc", "dirty": False},
        "stories_evaluated": len(stories),
        "valid_skeleton_rate": 1.0,
        "criteria_cover_rate": 1.0,
        "hallucinated_login_rate": 0.0,
        "total_skip_lines": 0,
        "total_placeholders": 10,
        "errors": 0,
        "per_story": stories,
    }


def _story(
    head: str,
    *,
    valid: bool = True,
    cover: bool = True,
    login: bool = False,
    skips: int = 0,
    error: str | None = None,
) -> dict:
    return {
        "site": "saucedemo",
        "story_head": head,
        "expected_criteria": 2,
        "valid_skeleton": valid,
        "criteria_cover": cover,
        "hallucinated_login": login,
        "skip_lines": skips,
        "placeholders": 5,
        "duration_s": 1.0,
        "error": error,
    }


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestLoadBaseline:
    def test_accepts_baseline(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "b.json", _baseline([_story("s1")]))
        assert load_baseline(p)["per_story"][0]["story_head"] == "s1"

    def test_rejects_non_baseline(self, tmp_path: Path) -> None:
        p = _write(tmp_path / "b.json", {"foo": 1})
        try:
            load_baseline(p)
        except ValueError as exc:
            assert "not a model baseline file" in str(exc)
        else:
            raise AssertionError("expected ValueError")


class TestIndexStories:
    def test_indexes_by_story_head(self) -> None:
        idx = index_stories(_baseline([_story("s1"), _story("s2")]))
        assert set(idx) == {"s1", "s2"}

    def test_empty(self) -> None:
        assert index_stories(_baseline([])) == {}


class TestAggregateDeltas:
    def test_improvement_not_regression(self) -> None:
        before = _baseline([])
        before["valid_skeleton_rate"] = 0.9
        after = _baseline([])
        after["valid_skeleton_rate"] = 1.0
        rows = aggregate_deltas(before, after)
        row = next(r for r in rows if r["key"] == "valid_skeleton_rate")
        assert row["regression"] is False
        assert abs(row["delta"] - 0.1) < 1e-9

    def test_rate_drop_is_regression(self) -> None:
        before = _baseline([])
        before["valid_skeleton_rate"] = 1.0
        after = _baseline([])
        after["valid_skeleton_rate"] = 0.94
        row = next(r for r in aggregate_deltas(before, after) if r["key"] == "valid_skeleton_rate")
        assert row["regression"] is True

    def test_lower_is_good_metric_regression(self) -> None:
        before = _baseline([])
        before["hallucinated_login_rate"] = 0.0
        after = _baseline([])
        after["hallucinated_login_rate"] = 0.1
        row = next(r for r in aggregate_deltas(before, after) if r["key"] == "hallucinated_login_rate")
        assert row["regression"] is True

    def test_skip_lines_increase_is_regression(self) -> None:
        before = _baseline([])
        before["total_skip_lines"] = 2
        after = _baseline([])
        after["total_skip_lines"] = 7
        row = next(r for r in aggregate_deltas(before, after) if r["key"] == "total_skip_lines")
        assert row["regression"] is True

    def test_placeholder_count_never_regresses(self) -> None:
        before = _baseline([])
        before["total_placeholders"] = 100
        after = _baseline([])
        after["total_placeholders"] = 5
        row = next(r for r in aggregate_deltas(before, after) if r["key"] == "total_placeholders")
        assert row["regression"] is False


class TestStoryVerdicts:
    def test_regressed_on_valid_skeleton_flip(self) -> None:
        assert story_regressed(_story("s", valid=True), _story("s", valid=False)) is True
        assert story_regressed(_story("s", valid=False), _story("s", valid=True)) is False

    def test_regressed_on_login_hallucination(self) -> None:
        assert story_regressed(_story("s", login=False), _story("s", login=True)) is True

    def test_regressed_on_skip_lines_increase(self) -> None:
        assert story_regressed(_story("s", skips=0), _story("s", skips=3)) is True

    def test_regressed_on_error_appearing(self) -> None:
        assert story_regressed(_story("s", error=None), _story("s", error="timeout")) is True

    def test_improved_on_error_resolved(self) -> None:
        assert story_improved(_story("s", error="timeout"), _story("s", error=None)) is True

    def test_improved_on_valid_skeleton_fixed(self) -> None:
        assert story_improved(_story("s", valid=False), _story("s", valid=True)) is True

    def test_no_change_is_neither(self) -> None:
        assert story_regressed(_story("s"), _story("s")) is False
        assert story_improved(_story("s"), _story("s")) is False


class TestBuildReport:
    def test_matches_stories_and_verdict(self, tmp_path: Path) -> None:
        before = _write(tmp_path / "before.json", _baseline([_story("s1"), _story("s2", valid=False)]))
        after = _write(tmp_path / "after.json", _baseline([_story("s1"), _story("s2", valid=True)]))
        report = build_report(before, after)
        assert report["verdict"] == "no-regression"
        assert report["stories_matched"] == 2
        assert len(report["story_improvements"]) == 1
        assert report["story_improvements"][0]["story_head"] == "s2"
        assert report["story_regressions"] == []

    def test_reports_regression_verdict(self, tmp_path: Path) -> None:
        before = _write(tmp_path / "before.json", _baseline([_story("s1")]))
        after = _write(tmp_path / "after.json", _baseline([_story("s1", valid=False)]))
        report = build_report(before, after)
        assert report["verdict"] == "regression"
        assert len(report["story_regressions"]) == 1

    def test_unmatched_after_stories_reported(self, tmp_path: Path) -> None:
        before = _write(tmp_path / "before.json", _baseline([_story("s1")]))
        after = _write(tmp_path / "after.json", _baseline([_story("s1"), _story("s2")]))
        report = build_report(before, after)
        assert report["story_unmatched"] == ["s2"]
        assert report["stories_matched"] == 1


class TestCompareExitCode:
    def test_exit_zero_on_no_regression(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        before = _write(tmp_path / "before.json", _baseline([_story("s1")]))
        after = _write(tmp_path / "after.json", _baseline([_story("s1")]))
        assert compare(before, after) == 0
        out = capsys.readouterr().out
        assert "VERDICT: no regressions" in out

    def test_exit_two_on_regression(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        before = _write(tmp_path / "before.json", _baseline([_story("s1")]))
        after = _write(tmp_path / "after.json", _baseline([_story("s1", valid=False)]))
        assert compare(before, after) == 2
        assert "VERDICT: regressions detected" in capsys.readouterr().out

    def test_json_out_prints_report(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        before = _write(tmp_path / "before.json", _baseline([_story("s1")]))
        after = _write(tmp_path / "after.json", _baseline([_story("s1")]))
        assert compare(before, after, json_out=True) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["verdict"] == "no-regression"
        assert "deltas" in payload


class TestDiscover:
    def test_orders_by_mtime(self, tmp_path: Path) -> None:
        import os
        import time

        from scripts.eval.compare_model_baselines import _discover

        p1 = _write(tmp_path / "model_baseline_old.json", _baseline([_story("s")]))
        p2 = _write(tmp_path / "model_baseline_new.json", _baseline([_story("s")]))
        old_mtime = time.time() - 3600
        os.utime(p1, (old_mtime, old_mtime))
        with patch("scripts.eval.compare_model_baselines.DEFAULT_GLOB", tmp_path / "model_baseline_*.json"):
            before, after = _discover()
        assert before == p1  # older file = before
        assert after == p2

    def test_single_baseline_exits(self, tmp_path: Path) -> None:
        import pytest

        from scripts.eval.compare_model_baselines import _discover

        _write(tmp_path / "model_baseline_only.json", _baseline([_story("s")]))
        with patch("scripts.eval.compare_model_baselines.DEFAULT_GLOB", tmp_path / "model_baseline_*.json"):
            with pytest.raises(SystemExit):
                _discover()
