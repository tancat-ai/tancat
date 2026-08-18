"""Tests for the eval-runner mock-serving fix (Phase 6 6a follow-up).

The single mock server on :8781 must serve each localhost-mock story from its
own root (golden keys reference root-relative URLs, so ecommerce and banking
cannot share one server). These tests pin the story→dir mapping and the
per-story server swap without touching the network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# eval_runner imports its siblings (eval_metrics, golden_validator) as bare
# modules — the harness normally runs with scripts/eval/ on sys.path.
_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from eval_runner import EvalRunner  # noqa: E402


def _write_dataset(tmp_path: Path, files: dict[str, dict]) -> Path:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    for name, payload in files.items():
        (dataset_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    return dataset_dir


def test_build_mock_dirs_legacy_defaults_to_repo_root(tmp_path: Path) -> None:
    """A localhost dataset without mock_dir is served from the repo root."""
    dataset_dir = _write_dataset(
        tmp_path,
        {"eval-005": {"id": "eval-005", "base_url": "http://localhost:8781/generated_tests/mock_insurance_site.html"}},
    )
    runner = EvalRunner(dataset_dir=dataset_dir, code_dir=tmp_path, db_path=tmp_path / "r.db")
    mock_dirs = runner._build_mock_dirs(repo_root=tmp_path)  # noqa: SLF001
    assert mock_dirs == {"eval-005": str(tmp_path.resolve())}


def test_build_mock_dirs_uses_declared_mock_dir(tmp_path: Path) -> None:
    """mock_dir values resolve against the repo root and win over legacy."""
    dataset_dir = _write_dataset(
        tmp_path,
        {
            "eval-005": {
                "id": "eval-005",
                "base_url": "http://localhost:8781/generated_tests/mock_insurance_site.html",
            },
            "eval-006": {
                "id": "eval-006",
                "base_url": "http://localhost:8781/index.html",
                "mock_dir": "mock_sites/ecommerce",
            },
            "eval-007": {
                "id": "eval-007",
                "base_url": "http://localhost:8781/index.html",
                "mock_dir": "mock_sites/banking",
            },
        },
    )
    runner = EvalRunner(dataset_dir=dataset_dir, code_dir=tmp_path, db_path=tmp_path / "r.db")
    mock_dirs = runner._build_mock_dirs(repo_root=tmp_path)  # noqa: SLF001
    assert mock_dirs["eval-005"] == str(tmp_path.resolve())
    assert mock_dirs["eval-006"] == str(tmp_path / "mock_sites" / "ecommerce")
    assert mock_dirs["eval-007"] == str(tmp_path / "mock_sites" / "banking")


def test_build_mock_dirs_ignores_live_sites(tmp_path: Path) -> None:
    dataset_dir = _write_dataset(
        tmp_path,
        {"eval-001": {"id": "eval-001", "base_url": "https://www.saucedemo.com"}},
    )
    runner = EvalRunner(dataset_dir=dataset_dir, code_dir=tmp_path, db_path=tmp_path / "r.db")
    assert runner._build_mock_dirs() == {}  # noqa: SLF001


class _FakeMockServer:
    """Records the directories it was asked to serve; starts are numbered."""

    started: list[str] = []
    stopped: int = 0

    def __init__(self, directory: str) -> None:
        self.directory = directory
        self.url = f"http://localhost:8781 ({directory})"

    @classmethod
    def start(cls, port: int = 8781, directory: str | Path = ".") -> _FakeMockServer:
        cls.started.append(str(directory))
        return cls(str(directory))

    def stop(self) -> None:
        type(self).stopped += 1


def test_ensure_mock_serves_swaps_per_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        runner = EvalRunner(dataset_dir=Path(td), code_dir=Path(td), db_path=Path(td) / "r.db")
        monkeypatch.setattr("scripts.mock_server.MockServer", _FakeMockServer)
        _FakeMockServer.started = []
        _FakeMockServer.stopped = 0

        # No-op for stories that don't need the mock.
        runner._ensure_mock_serves(None)  # noqa: SLF001
        assert _FakeMockServer.started == []

        # First mock story starts the server on its dir.
        runner._ensure_mock_serves("/mock/a")  # noqa: SLF001
        assert _FakeMockServer.started == ["/mock/a"]

        # Same dir again — no restart.
        runner._ensure_mock_serves("/mock/a")  # noqa: SLF001
        assert _FakeMockServer.started == ["/mock/a"]
        assert _FakeMockServer.stopped == 0

        # Different dir — stop + restart.
        runner._ensure_mock_serves("/mock/b")  # noqa: SLF001
        assert _FakeMockServer.started == ["/mock/a", "/mock/b"]
        assert _FakeMockServer.stopped == 1
