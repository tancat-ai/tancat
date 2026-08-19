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


def test_sampling_identity_records_pinned_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    """New runs record what sampling the pipeline actually delivered.

    Graph runs always send 0; linear runs send AITEST_LLM_TEMPERATURE or the
    0.0 pipeline default. server_defaults falls back to {} when the endpoint
    isn't reachable (no network in tests).
    """
    import tempfile

    from eval_metrics import StoryResult
    from eval_runner import persist_results

    story = StoryResult(
        story_id="eval-sample",
        site="mock",
        total_criteria=1,
        criteria_with_skeletons=1,
    )
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "runs.db"

        monkeypatch.delenv("AITEST_LLM_TEMPERATURE", raising=False)
        run_ids = persist_results(
            db_path, [story], "static", temperature_sent=0.0, server_defaults="{}", thinking="off"
        )
        assert run_ids

        import sqlite3

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT temperature_sent, server_defaults, thinking FROM eval_runs LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 0.0
        assert row[1] == "{}"
        assert row[2] == "off"

        # Graph pipeline → agents pin temperature=0 regardless of env.
        monkeypatch.setenv("AITEST_LLM_TEMPERATURE", "0.7")
        run_ids = persist_results(db_path, [story], "static", pipeline="graph", temperature_sent=0.0)
        assert run_ids


def test_legacy_eval_runs_table_is_migrated() -> None:
    """Pre-existing databases get the new columns without data loss."""
    import sqlite3
    import tempfile

    from eval_runner import _ensure_eval_table

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        # Emulate the pre-fix schema (no sampling columns).
        conn.execute(
            """
            CREATE TABLE eval_runs (
                run_id TEXT PRIMARY KEY,
                story_id TEXT NOT NULL,
                site TEXT NOT NULL,
                placeholders_total INTEGER NOT NULL DEFAULT 0,
                placeholders_correct INTEGER NOT NULL DEFAULT 0,
                resolution_accuracy REAL NOT NULL DEFAULT 0.0,
                test_pass_rate REAL NOT NULL DEFAULT 0.0,
                false_positive_rate REAL NOT NULL DEFAULT 0.0,
                skeleton_completeness REAL NOT NULL DEFAULT 0.0,
                generation_duration REAL NOT NULL DEFAULT 0.0,
                mode TEXT NOT NULL DEFAULT 'static',
                raw_report TEXT,
                created_at TEXT NOT NULL,
                pipeline TEXT NOT NULL DEFAULT 'linear',
                generation_mode TEXT NOT NULL DEFAULT 'captured',
                rag_enabled INTEGER NOT NULL DEFAULT 0,
                pom_mode INTEGER NOT NULL DEFAULT 0,
                provider TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                git_commit TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO eval_runs (run_id, story_id, site, created_at) VALUES ('legacy-1', 's1', 'site', '2026-08-17')"
        )
        conn.commit()

        _ensure_eval_table(conn)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(eval_runs)").fetchall()]
        assert "temperature_sent" in cols
        assert "server_defaults" in cols
        assert "thinking" in cols
        # Row data survives the migration and new columns are NULL for legacy
        # rows. Note: SQLite on Windows keeps the file lock until the single
        # connection is fully closed, so all queries share one connection.
        row = conn.execute("SELECT run_id, temperature_sent FROM eval_runs WHERE run_id='legacy-1'").fetchone()
        conn.close()
        assert row == ("legacy-1", None)


def test_sampling_identity_hits_origin_props(monkeypatch: pytest.MonkeyPatch) -> None:
    """/props is fetched at the origin, not under the /v1 OpenAl base URL.

    Providers expose base_url as ``<origin>/v1``; llama.cpp's /props endpoint
    lives at the origin. The snapshot must come from the origin URL.
    """
    import tempfile

    captured: list[str] = []

    class _FakeProvider:
        provider_name = "openai-local"
        base_url = "http://localhost:8080/v1"

        def get_loaded_model(self, timeout: int = 5) -> str:
            return "fake-model"

    def _fake_get(url: str, timeout: float = 5) -> object:
        captured.append(url)
        return _FakeResponse()

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "default_generation_settings": {"params": {"temperature": 1.0, "top_p": 0.95}},
                "n_ctx": 262144,
            }

    monkeypatch.setattr("src.llm_providers.auto_detect_provider", lambda: _FakeProvider())
    monkeypatch.setattr("httpx.get", _fake_get)

    with tempfile.TemporaryDirectory() as td:
        runner = EvalRunner(dataset_dir=Path(td), code_dir=Path(td), db_path=Path(td) / "r.db")
        temp_sent, defaults, thinking = runner._sampling_identity(use_graph=False)  # noqa: SLF001
        _, _, graph_thinking = runner._sampling_identity(use_graph=True)  # noqa: SLF001

    assert captured == [
        "http://localhost:8080/props",
        "http://localhost:8080/slots",
        "http://localhost:8080/props",
        "http://localhost:8080/slots",
    ]
    assert temp_sent == 0.0
    assert "temperature" in defaults
    # Thinking policy is recorded like temperature — never silent: linear
    # structured calls send enable_thinking=False explicitly; graph stages
    # currently inherit the model default (per-stage opt-in is future work).
    assert thinking == "off"
    assert graph_thinking == "model-default"


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
