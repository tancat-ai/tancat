"""Phase 6e — offline ed25519 license + tier tests.

Hermetic: sign/verify roundtrip, tamper rejection, expiry + grace, tier claims,
unlicensed = free tier. No network. The trust root is the vendored constant
(B-050: not customer-settable); end-to-end tests monkeypatch that constant.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.licensing import license as _license_module
from src.licensing.license import (
    GRACE_DAYS,
    LicenseClaims,
    LicenseStatus,
    effective_tier,
    feature_enabled,
    license_status,
    sign_license,
    verify_license,
)
from src.licensing.tiers import feature_required_tier, limit_for, tier_claims


def _keypair() -> tuple[bytes, str]:
    import base64

    from cryptography.hazmat.primitives import serialization

    priv = ed25519.Ed25519PrivateKey.generate()
    raw = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return raw, base64.b64encode(pub).decode()


def _claims(tier: str = "pro", **kw: Any) -> LicenseClaims:
    now = datetime.now(UTC)
    data = {
        "deployment_id": kw.get("deployment_id", "test-deploy"),
        "tier": tier,
        "claims": kw.get("claims", ()),
        "issued_at": kw.get("issued_at", now.isoformat()),
        "expires_at": kw.get("expires_at", (now + timedelta(days=30)).isoformat()),
        "issuer": kw.get("issuer", "cat-tan-operations"),
    }
    return LicenseClaims(**data)


def _make_token(private_key: bytes, claims: LicenseClaims) -> str:
    return sign_license(claims, private_key)


# -- sign / verify roundtrip --------------------------------------------------


def test_sign_verify_roundtrip() -> None:
    priv, pub = _keypair()
    token = _make_token(priv, _claims(tier="pro"))
    result = verify_license(token, pub)
    assert result.status == LicenseStatus.VALID
    assert result.tier == "pro"
    assert result.deployment_id == "test-deploy"
    assert result.usable is True
    assert "pom" in tier_claims("pro")
    assert "generate" in tier_claims("free")


def test_tampered_payload_rejected() -> None:
    priv, pub = _keypair()
    token = _make_token(priv, _claims())
    payload, sig = token.split(".", 1)
    # Deterministic forgery: decode → change a JSON field → re-encode.
    import base64
    import json

    payload_json = json.loads(base64.urlsafe_b64decode(payload + "==").decode("utf-8"))
    payload_json["tier"] = "airgap"  # an attacker trying to self-upgrade
    payload_json["expires_at"] = "2999-01-01T00:00:00+00:00"
    forged_payload = base64.urlsafe_b64encode(json.dumps(payload_json).encode("utf-8")).decode("ascii").rstrip("=")
    forged = f"{forged_payload}.{sig}"
    result = verify_license(forged, pub)
    assert result.status == LicenseStatus.INVALID
    assert "Signature" in result.reason


def test_tampered_signature_rejected() -> None:
    priv, pub = _keypair()
    token = _make_token(priv, _claims())
    payload, sig = token.split(".", 1)
    sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    result = verify_license(f"{payload}.{sig}", pub)
    assert result.status == LicenseStatus.INVALID
    assert result.usable is False


def test_wrong_public_key_rejected() -> None:
    priv, _pub = _keypair()
    other_priv, other_pub = _keypair()
    token = _make_token(priv, _claims())
    result = verify_license(token, other_pub)
    assert result.status == LicenseStatus.INVALID


def test_empty_token_is_unlicensed() -> None:
    priv, pub = _keypair()
    token = _make_token(priv, _claims())
    assert verify_license("", pub).status == LicenseStatus.UNLICENSED
    assert verify_license(None, pub).status == LicenseStatus.UNLICENSED
    assert verify_license(token, pub).status == LicenseStatus.VALID


# -- expiry + grace -----------------------------------------------------------


def test_expired_within_grace_is_usable() -> None:
    priv, pub = _keypair()
    past = datetime.now(UTC) - timedelta(days=5)
    token = _make_token(priv, _claims(expires_at=past.isoformat()))
    result = verify_license(token, pub, grace_days=GRACE_DAYS)
    assert result.status == LicenseStatus.EXPIRED_GRACE
    assert result.usable is True
    assert result.grace_until


def test_expired_beyond_grace_blocked() -> None:
    priv, pub = _keypair()
    past = datetime.now(UTC) - timedelta(days=10)
    token = _make_token(priv, _claims(expires_at=past.isoformat()))
    result = verify_license(token, pub, grace_days=7)
    assert result.status == LicenseStatus.EXPIRED_BLOCKED
    assert result.usable is False


def test_valid_timestamp_boundary() -> None:
    priv, pub = _keypair()
    now = int(time.time())
    claims = _claims(expires_at=datetime.fromtimestamp(now + 100, tz=UTC).isoformat())
    result = verify_license(_make_token(priv, claims), pub, now=now)
    assert result.status == LicenseStatus.VALID


# -- tier claims + feature gates ----------------------------------------------


def test_tier_table_shape() -> None:
    assert set(tier_claims("free")) >= {"generate", "evidence_export", "self_heal", "rag_learning"}
    assert "jira_export" in tier_claims("self-serve")
    assert "pom" in tier_claims("pro")
    assert "ci_runs" in tier_claims("pro")
    assert "private_network" in tier_claims("airgap")
    assert limit_for("free", "runs_per_month") == 25
    assert limit_for("pro", "runs_per_month") is None


def test_feature_required_tier() -> None:
    assert feature_required_tier("generate") == "free"
    assert feature_required_tier("jira_export") == "self-serve"
    assert feature_required_tier("pom") == "pro"
    assert feature_required_tier("nope") is None


def test_unlicensed_effective_tier_is_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITEST_LICENSE_KEY", raising=False)
    monkeypatch.delenv("AITEST_LICENSE_FILE", raising=False)
    assert effective_tier() == "free"


def test_feature_enabled_by_tier(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Valid pro license (env inline) → POM enabled. B-050: trust root is the
    # vendored constant (not customer-settable), so patch it to the test key.
    priv, pub = _keypair()
    monkeypatch.setattr(_license_module, "VENDORED_PUBLIC_KEY_B64", pub)
    token = _make_token(priv, _claims(tier="pro"))
    monkeypatch.setenv("AITEST_LICENSE_KEY", token)
    assert feature_enabled("pom") is True
    assert feature_enabled("jira_export") is True
    assert feature_enabled("private_network") is False  # pro has no private-network claim
    assert effective_tier() == "pro"


def test_feature_enabled_free_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AITEST_LICENSE_KEY", raising=False)
    monkeypatch.delenv("AITEST_LICENSE_FILE", raising=False)
    assert feature_enabled("generate") is True
    assert feature_enabled("self_heal") is True
    assert feature_enabled("pom") is False
    assert feature_enabled("jira_export") is False


def test_license_key_file_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    priv, pub = _keypair()
    token = _make_token(priv, _claims(tier="airgap"))
    key_file = tmp_path / "license.key"
    key_file.write_text(token + "\n", encoding="utf-8")
    monkeypatch.setattr(_license_module, "VENDORED_PUBLIC_KEY_B64", pub)  # B-050
    monkeypatch.setenv("AITEST_LICENSE_FILE", str(key_file))
    result = license_status()
    assert result.status == LicenseStatus.VALID
    assert result.tier == "airgap"


def test_expired_blocked_ci_flag_off() -> None:
    priv, pub = _keypair()
    past = datetime.now(UTC) - timedelta(days=10)
    token = _make_token(priv, _claims(tier="pro", expires_at=past.isoformat()))
    result = verify_license(token, pub, grace_days=7)
    assert result.status == LicenseStatus.EXPIRED_BLOCKED
    # Even blocked, the OSS core (generate/self-heal/evidence) stays enabled by
    # tier — feature_enabled reads tier claims, not the blocked flag (spec §7.6).
    assert feature_enabled("generate", tier=result.tier) is True


def test_malformed_token_invalid() -> None:
    priv, pub = _keypair()
    assert verify_license("garbage", pub).status == LicenseStatus.INVALID
    assert verify_license("a.b.c", pub).status == LicenseStatus.INVALID


def test_headline_smoke() -> None:
    from src.licensing.license import LicenseResult

    for status in (
        LicenseStatus.VALID,
        LicenseStatus.EXPIRED_GRACE,
        LicenseStatus.EXPIRED_BLOCKED,
        LicenseStatus.INVALID,
        LicenseStatus.UNLICENSED,
    ):
        h = LicenseResult(status=status).headline
        assert h and len(h) > 5
