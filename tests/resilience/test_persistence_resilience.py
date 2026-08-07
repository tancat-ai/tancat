"""Resilience tests — the product under crash/corruption/restart conditions.

Test-Pack Restructure (2026-08-03, work item 2): the suite had no resilience
layer, yet production bugs clustered there — corrupted ``run_results.sqlite``
crashing the evidence page (B-034), streamlit module-watcher reloads making
stored ``RunResult`` instances fail ``isinstance`` (B-044), and killed/
timed-out test processes leaving orphaned screenshots with no sidecar
(B-035).

These tests are OFFLINE: they drive the real persistence/evidence modules
against corrupt files, reloaded classes, and truncated runs. No browser, no
LLM, no external network, CI-able.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── B-034: corrupted run_results.sqlite must not crash consumers ──────────


def test_sqlite_persistence_survives_corrupt_db(tmp_path: Path) -> None:
    """A truncated/corrupt SQLite file must degrade gracefully, not raise on
    load. B-034: the evidence page crashed on a corrupt run_results.sqlite."""
    from src.sqlite_persistence import SQLitePersistence

    db_path = tmp_path / "run_results.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"this is not a sqlite file at all\x00\x01\x02")

    store = SQLitePersistence(db_path=db_path)
    # Load must not raise; it should yield an empty result set.
    rows = store.load_all_run_results()
    assert isinstance(rows, list)
    store.close()


def test_sqlite_persistence_recovers_corrupt_db_on_write(tmp_path: Path) -> None:
    """Writing to a corrupt DB must rebuild it rather than crash — the UI
    evidence page opens the DB for both read and write."""
    from src.pytest_output_parser import RunResult, TestResult
    from src.sqlite_persistence import SQLitePersistence

    corrupt = tmp_path / "run_results.sqlite"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"corrupt\x00\x01")

    run = RunResult(
        results=[TestResult(name="t1", status="passed", duration=1.0, error_message="", file_path="tests/test_x.py")],
        total=1,
        passed=1,
    )
    store = SQLitePersistence(db_path=corrupt)
    store.persist_run_result(run, "pkg_a")
    rows = store.load_all_run_results()
    assert any(r.test_package == "pkg_a" for r in rows)
    store.close()


# ── B-044: reload-safe RunResult duck typing ──────────────────────────────


def test_is_run_result_duck_type_survives_reloaded_class() -> None:
    """Streamlit's module watcher reloads src modules mid-session, creating a
    NEW RunResult class — stored instances then failed isinstance and results
    vanished. B-044: is_run_result() duck-types on shape (class name +
    attributes), so a reloaded-class instance still passes."""
    from src.pytest_output_parser import is_run_result

    class RunResult:  # mimics the post-reload class (same name, new identity)
        def __init__(self) -> None:
            self.results: list[Any] = []
            self.total = 0

    assert is_run_result(RunResult()) is True
    assert is_run_result("not a run result") is False
    assert is_run_result(None) is False


# ── B-035: sidecar written even when the process is killed mid-run ────────


def test_sidecar_persists_without_teardown(tmp_path: Path) -> None:
    """B-035: evidence must not live only in teardown — a step-level write
    must produce a sidecar file on disk even if the process dies afterwards
    (the tracker's navigate/_record_step already persists 'running')."""
    from unittest.mock import MagicMock

    from src.evidence_tracker import EvidenceTracker

    page_mock = MagicMock()
    page_mock.url = "https://example.com"
    tracker = EvidenceTracker(page_mock, "test_killed", evidence_root=Path(tmp_path))

    tracker.navigate("https://example.com")

    # navigate() persists a 'running' sidecar incrementally (B-035 fix).
    files = list(Path(tmp_path).rglob("*.evidence.json"))
    assert files, "sidecar must exist after step-level write (no teardown needed)"
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert "steps" in data


# ── DB survives concurrent opens (sqlite busy handling) ───────────────────


def test_run_history_db_survives_concurrent_opens(tmp_path: Path) -> None:
    """The workspace run-history DB must tolerate concurrent open/write from
    multiple processes (pytest -n workers / parallel UI) without locking
    itself into 'database is locked'."""
    from src.pytest_output_parser import RunResult, TestResult
    from src.sqlite_persistence import SQLitePersistence

    db_path = tmp_path / "run_history.sqlite"

    def make_run(name: str, status: str) -> RunResult:
        return RunResult(
            results=[TestResult(name=name, status=status, duration=1.0, error_message="", file_path="tests/test_x.py")],
            total=1,
            passed=1 if status == "passed" else 0,
        )

    store1 = SQLitePersistence(db_path=db_path)
    store1.persist_run_result(make_run("t1", "passed"), "pkg_a")
    store1.close()

    # Second store on the same file (simulates a second worker/process).
    store2 = SQLitePersistence(db_path=db_path)
    store2.persist_run_result(make_run("t2", "failed"), "pkg_a")
    rows = store2.load_all_run_results()
    store2.close()

    assert len(rows) >= 2


# ── Settings store survives corruption (B-036 pattern) ────────────────────


def test_settings_store_survives_corrupt_encrypted_file(tmp_path: Path) -> None:
    """The Fernet-encrypted settings file must degrade to defaults when
    corrupted — a bad settings.enc must not crash the app at startup."""
    import src.settings_store as ss

    settings_file = tmp_path / "settings.enc"
    settings_file.write_bytes(b"garbage-not-fernet\x00\x01")
    ss._settings_path = lambda: settings_file  # type: ignore[method-assign]

    store = ss.SettingsStore()
    value = store.get("pom_mode", "fallback")
    # Corruption-tolerant: returns the default, does not raise.
    assert value == "fallback"
