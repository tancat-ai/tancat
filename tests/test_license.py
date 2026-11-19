"""The licence gate: one signed file, verified offline, and the tier it grants (j-0309).

The token format is gone (t-1468). What is left to hold is the gate the rest of the
product asks: ``license_status`` reports a valid signed file or Free, and
``feature_enabled`` answers from the tier table. The signature-level tests live in
``test_signed_licence_file.py``; these tests are about the gate itself.

No network: the licensing package imports no network module, checked there.
"""

from __future__ import annotations

import base64
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.licensing import entitlement, signed_file
from src.licensing import license as _license
from src.licensing.license import (
    VENDORED_PUBLIC_KEY_B64,
    LicenseStatus,
    effective_tier,
    feature_enabled,
    license_status,
    vendor_public_key,
)
from src.licensing.tiers import feature_required_tier, limit_for, tier_claims


def _keypair() -> tuple[bytes, str]:
    private = ed25519.Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = base64.b64encode(
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    return raw, public


@pytest.fixture
def signed_licence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A valid signed licence file in force, verified against a throwaway key."""
    private, public = _keypair()
    monkeypatch.setattr(signed_file, "VENDORED_PUBLIC_KEY_B64", public)
    path = tmp_path / "licence.signed.json"
    purchased = date(2026, 11, 10)
    path.write_text(
        signed_file.signed_file_text(
            {
                "id": "TC-2026-000421",
                "product": "tancat",
                "buyer_ref": "order 421 / buyer@example.com",
                "purchased_at": purchased.isoformat(),
                "window_end": (purchased + timedelta(days=365)).isoformat(),
                "tier": "pro",
            },
            private,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(path))
    return {"path": path, "private": private, "public": public}


def test_no_licence_file_is_the_free_tier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(tmp_path / "absent.json"))
    result = license_status()
    assert result.status == LicenseStatus.UNLICENSED
    assert result.tier == "free"
    assert result.usable, "the free tier must stay usable"
    assert effective_tier() == "free"


def test_a_valid_signed_file_reports_its_tier(signed_licence: dict[str, Any]) -> None:
    result = license_status()
    assert result.status == LicenseStatus.VALID
    assert result.tier == "pro"
    assert result.licence_id == "TC-2026-000421"
    assert result.usable
    assert effective_tier() == "pro"


def test_a_refused_file_is_invalid_and_names_the_reason(
    signed_licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    path: Path = signed_licence["path"]
    path.write_text(path.read_text(encoding="utf-8").replace("TC-2026-000421", "TC-2026-999999"), encoding="utf-8")

    result = license_status()
    assert result.status == LicenseStatus.INVALID
    assert result.tier == "free"
    assert "signature does not verify" in result.reason
    assert "refused" in result.headline.lower()


def test_a_licence_for_another_product_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    private, public = _keypair()
    monkeypatch.setattr(signed_file, "VENDORED_PUBLIC_KEY_B64", public)
    path = tmp_path / "licence.signed.json"
    path.write_text(
        signed_file.signed_file_text(
            {
                "id": "TC-1",
                "product": "not-tancat",
                "buyer_ref": "x",
                "purchased_at": "2026-11-01",
                "window_end": "2027-11-01",
                "tier": "pro",
            },
            private,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(path))
    assert license_status().status == LicenseStatus.INVALID


def test_an_expired_window_still_reports_the_tier_but_blocks_new_builds(
    signed_licence: dict[str, Any],
) -> None:
    """The window is a build gate, not a tier switch - the held version keeps running."""
    state = entitlement.resolve()
    assert state.source == "signed"
    assert state.tier == "pro"

    end = state.window_end
    assert end is not None
    assert not entitlement.startup_check(build_date=end + timedelta(days=30)).allowed
    assert entitlement.startup_check(build_date=end - timedelta(days=1)).allowed


def test_feature_enabled_follows_the_tier(signed_licence: dict[str, Any]) -> None:
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


def test_the_public_surface_has_no_token_route() -> None:
    """One mechanism: nothing here can load, save or verify a token."""
    for gone in ("load_license", "save_license_key", "sign_license", "verify_license", "LicenseClaims"):
        assert not hasattr(_license, gone), f"{gone} still exists - a second verification route"
    assert vendor_public_key() == VENDORED_PUBLIC_KEY_B64
    assert len(base64.b64decode(VENDORED_PUBLIC_KEY_B64)) == 32


def test_the_gate_makes_no_network_call(signed_licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate is pure file reading plus ed25519 maths."""
    import socket

    def _no_socket(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the licence gate tried to open a socket")

    monkeypatch.setattr(socket, "socket", _no_socket)
    monkeypatch.setattr(socket, "create_connection", _no_socket)

    assert license_status().status == LicenseStatus.VALID
    assert effective_tier() == "pro"
