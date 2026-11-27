"""The licence gate: the tier an activated key grants, from the cache.

The mechanism changed on 2026-11-26: a key the store issued, activated once through
our relay, then read from disk. What this file holds is the gate the rest of the
product asks - ``license_status`` reports an activated key or Free, and
``feature_enabled`` answers from the tier table.

Activation and update behaviour live in ``test_licence_key_activation.py``. These
tests are about the gate, and about the promise that the gate itself is local.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.licensing import entitlement
from src.licensing import license as _license
from src.licensing.license import (
    LicenseStatus,
    effective_tier,
    feature_enabled,
    license_status,
)
from src.licensing.tiers import feature_required_tier, limit_for, tier_claims


def _write_licence(path: Path, *, created_at: str = "2026-11-26T00:04:47.460Z", status: str = "active") -> None:
    path.write_text(
        json.dumps(
            {
                "key": "00000-00000-00000-00000-00000",
                "instance_id": "lki_testinstance000000000000",
                "instance_name": "acme-laptop",
                "status": status,
                "created_at": created_at,
                "expires_at": "",
                "activation_limit": 1,
                "last_checked": created_at,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def licence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An activated key in force, on a path this test owns."""
    path = tmp_path / "licence.json"
    _write_licence(path)
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(path))
    return path


def test_no_stored_licence_is_the_free_tier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(tmp_path / "absent.json"))
    result = license_status()
    assert result.status == LicenseStatus.UNLICENSED
    assert result.tier == "free"
    assert result.usable, "the free tier must stay usable"
    assert effective_tier() == "free"


def test_an_activated_key_reports_its_tier(licence: Path) -> None:
    result = license_status()
    assert result.status == LicenseStatus.VALID
    assert result.tier == "pro"
    assert result.licence_id == "00000-...-00000", "the screenshot-safe form hides the middle"
    assert result.window_end == "2027-11-26"
    assert result.usable
    assert effective_tier() == "pro"


def test_a_damaged_cache_is_invalid_and_names_the_reason(licence: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITEST_LICENCE_FILE", raising=False)
    licence.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence))

    result = license_status()
    assert result.status == LicenseStatus.INVALID
    assert result.tier == "free"
    assert "not valid JSON" in result.reason
    assert "could not be used" in result.headline.lower()


def test_an_incomplete_cache_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "licence.json"
    path.write_text(json.dumps({"key": "00000-00000-00000-00000-00000"}), encoding="utf-8")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(path))
    assert license_status().status == LicenseStatus.INVALID


def test_an_expired_window_still_reports_the_tier_but_blocks_new_builds(licence: Path) -> None:
    """The window is a build gate, not a tier switch - the held version keeps running."""
    state = entitlement.resolve()
    assert state.source == "activated"
    assert state.tier == "pro"

    end = state.window_end
    assert end is not None
    assert not entitlement.startup_check(build_date=end + timedelta(days=30)).allowed
    assert entitlement.startup_check(build_date=end - timedelta(days=1)).allowed


def test_the_window_comes_from_the_key_date_not_the_install_date(licence: Path) -> None:
    state = entitlement.resolve()
    assert state.activated_on == date(2026, 11, 26)
    assert state.window_end == date(2027, 11, 26)


def test_feature_enabled_follows_the_tier(licence: Path) -> None:
    assert feature_enabled("jira_export")
    assert "jira_export" in tier_claims("pro")


def test_feature_enabled_free_tier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(tmp_path / "absent.json"))
    # The OSS core claims are free; the paid ones are not.
    assert feature_enabled("evidence_export")
    assert not feature_enabled("jira_export")


def test_the_tier_table_shape() -> None:
    from src.licensing.tiers import tiers

    free = tiers()["free"]
    assert "runs_per_month" in dict(free.limits)
    assert (limit_for("free", "runs_per_month") or 0) > 0
    assert feature_required_tier("jira_export") is not None


def test_the_public_surface_has_no_second_verification_route() -> None:
    """One mechanism: nothing here can sign, verify or smuggle a second licence."""
    for gone in (
        "load_license",
        "save_license_key",
        "sign_license",
        "verify_license",
        "LicenseClaims",
        "VENDORED_PUBLIC_KEY_B64",
        "vendor_public_key",
    ):
        assert not hasattr(_license, gone), f"{gone} still exists - a second verification route"


def test_the_gate_makes_no_network_call(licence: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading the licence is file I/O plus arithmetic - no socket, ever."""

    def _no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the licence gate tried to reach the network")

    from src.licensing import activation as keys

    monkeypatch.setattr(keys.urllib.request, "urlopen", _no_network)

    assert license_status().status == LicenseStatus.VALID
    assert effective_tier() == "pro"
