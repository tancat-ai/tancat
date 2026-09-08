"""Phase 6e — usage meter + free-tier cap tests.

Hermetic: monthly run counts from a seeded run_results.sqlite, export ledger,
storage accounting, free-tier hard stop + upgrade prompt, paid-tier no-cap,
env overrides (AITEST_FREE_TIER_RUNS / AITEST_ENFORCE_FREE_TIER).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.licensing import license as _license_module
from src.licensing.license import LicenseClaims, sign_license
from src.usage_meter import FreeTierLimitError, UsageMeter, monthly_window


def _now() -> datetime:
    return datetime.now(UTC)


def _seed_run_db(db_path: Path, count: int, *, days_ago: int = 0, run_id_offset: int = 0) -> None:
    """Create a run_results.sqlite with `count` runs at `days_ago` ago."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, test_package TEXT, total INTEGER, "
        "passed INTEGER, failed INTEGER, skipped INTEGER, errors INTEGER, duration REAL, "
        "raw_output TEXT, created_at TEXT)"
    )
    ts = (_now() - timedelta(days=days_ago)).isoformat()
    for i in range(count):
        conn.execute(
            "INSERT INTO runs (run_id, test_package, total, passed, failed, skipped, errors, duration, raw_output, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"run-{i + run_id_offset}", f"pkg-{i}", 1, 1, 0, 0, 0, 1.0, "", ts),
        )
    conn.commit()
    conn.close()


def _meter(tmp_path: Path, **kw: Any) -> UsageMeter:
    env = {"AITEST_ENFORCE_FREE_TIER": "1", **kw.pop("env", {})}
    return UsageMeter(
        run_db_path=tmp_path / "run_results.sqlite",
        ledger_path=tmp_path / "evidence" / ".usage_ledger.json",
        storage_root=tmp_path,
        env=env,
        **kw,
    )


def test_monthly_window_shape() -> None:
    start, end = monthly_window()
    assert start < end
    assert start.endswith("+00:00") or "Z" in start


def test_count_runs_this_month(tmp_path: Path) -> None:
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 3)
    m = _meter(tmp_path)
    assert m.count_runs_this_month(_now()) == 3


def test_runs_outside_window_excluded(tmp_path: Path) -> None:
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 2, days_ago=0)
    _seed_run_db(db, 5, days_ago=45, run_id_offset=100)
    m = _meter(tmp_path)
    assert m.count_runs_this_month(_now()) == 2


def test_no_run_db_counts_zero(tmp_path: Path) -> None:
    m = _meter(tmp_path)
    assert m.summary().runs_used == 0


def test_export_ledger_roundtrip(tmp_path: Path) -> None:
    m = _meter(tmp_path)
    m.record_export("csv", "evidence/failed.csv")
    m.record_export("ndjson", "evidence/all.ndjson")
    assert m.count_exports_this_month(_now()) == 2
    assert m.summary().exports_used == 2


def test_export_outside_window_excluded(tmp_path: Path) -> None:
    m = _meter(tmp_path)
    m.record_export("csv", "old.csv")
    # Backdate the ledger entry to 45 days ago.
    ledger = tmp_path / "evidence" / ".usage_ledger.json"
    data = json.loads(ledger.read_text(encoding="utf-8"))
    data["exports"][0]["at"] = (_now() - timedelta(days=45)).isoformat()
    ledger.write_text(json.dumps(data), encoding="utf-8")
    assert m.count_exports_this_month(_now()) == 0


def test_free_tier_hard_stop(tmp_path: Path) -> None:
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 25)  # at the limit (AITEST_FREE_TIER_RUNS=25)
    m = _meter(tmp_path)
    with pytest.raises(FreeTierLimitError) as exc:
        m.assert_run_allowed()
    assert "upgrade" in str(exc.value).lower() or "Upgrade" in exc.value.upgrade_prompt
    assert exc.value.run_remaining == 0


def test_free_tier_runs_remaining(tmp_path: Path) -> None:
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 10)
    m = _meter(tmp_path)
    m.assert_run_allowed()  # 15 remaining — allowed
    summary = m.summary()
    assert summary.runs_remaining == 15


def test_free_tier_cap_configurable(tmp_path: Path) -> None:
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 12)
    m = _meter(tmp_path, env={"AITEST_FREE_TIER_RUNS": "10"})
    with pytest.raises(FreeTierLimitError):
        m.assert_run_allowed()
    m2 = _meter(tmp_path, env={"AITEST_FREE_TIER_RUNS": "25"})
    m2.assert_run_allowed()  # 12 < 25


def test_enforcement_off_disables_cap(tmp_path: Path) -> None:
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 100)
    m = _meter(tmp_path, env={"AITEST_ENFORCE_FREE_TIER": "0"})
    m.assert_run_allowed()  # no hard stop


def _paid_license(monkeypatch: pytest.MonkeyPatch, tier: str = "self-serve") -> None:
    """Install a valid license in the real env via monkeypatch."""
    import base64

    from cryptography.hazmat.primitives import serialization

    priv = ed25519.Ed25519PrivateKey.generate()
    raw = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_b64 = base64.b64encode(
        priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    now = _now()
    token = sign_license(
        LicenseClaims(
            deployment_id="paid-deploy",
            tier=tier,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(days=30)).isoformat(),
        ),
        raw,
    )
    monkeypatch.setenv("AITEST_LICENSE_KEY", token)
    # B-050: trust root is the vendored constant (not customer-settable); patch
    # it to the test key so the self-signed token verifies end-to-end.
    monkeypatch.setattr(_license_module, "VENDORED_PUBLIC_KEY_B64", pub_b64)


def test_paid_tier_has_no_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paid_license(monkeypatch, tier="pro")
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 1000)
    m = _meter(tmp_path)
    m.assert_run_allowed()  # pro tier — no free-tier cap
    assert m.summary().runs_limit is None


def test_storage_bytes(tmp_path: Path) -> None:
    (tmp_path / "generated_tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "generated_tests" / "a.py").write_text("x" * 100, encoding="utf-8")
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence" / "b.json").write_text("y" * 50, encoding="utf-8")
    m = _meter(tmp_path)
    assert m.storage_bytes() == 150


def test_summary_json_shape(tmp_path: Path) -> None:
    db = tmp_path / "run_results.sqlite"
    _seed_run_db(db, 2)
    m = _meter(tmp_path)
    d = m.summary().to_dict()
    assert d["runs"]["used"] == 2
    assert d["runs"]["limit"] == 25
    assert d["runs"]["remaining"] == 23
    assert d["tier"] == "free"
    assert "storage_bytes" in d


def test_export_gate_jira_only_on_free(tmp_path: Path) -> None:
    m = _meter(tmp_path)
    # Core formats pass; Jira is capped on the free tier.
    m.assert_export_allowed("csv")
    m.assert_export_allowed("json")
    # Fill the export cap.
    for _ in range(10):
        m.record_export("jira", "report.html")
    with pytest.raises(FreeTierLimitError):
        m.assert_export_allowed("jira")


def test_export_never_blocked_on_paid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _paid_license(monkeypatch, tier="self-serve")
    m = _meter(tmp_path)
    for _ in range(100):
        m.record_export("jira", "r.html")
    m.assert_export_allowed("jira")  # self-serve grants jira_export → no cap
