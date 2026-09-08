"""Offline ed25519-signed license validation (Phase 6e, spec §5.4).

**Open-core honesty:** this is *entitlement/support marking*, not DRM. A
modified fork can strip it — accepted and documented. The key's value is ToS
entitlement, honest tier enforcement for stock builds, and the air-gap premium
bundle.

**Token format** (JWT-ish, no JWT lib — hand-rolled, matches ``cryptography``
which is already a dependency)::

    payload_b64 "." signature_b64

where ``payload_b64`` is ``base64url(json.dumps(payload))`` and
``signature_b64`` is the ed25519 signature of ``payload_b64``.

Payload: ``{deployment_id, tier, claims[], issued_at, expires_at, issuer}``.

**Validation contract (zero network calls):**

- No key configured → ``UNLICENSED`` (free tier — open core stays usable).
- Signature invalid / payload malformed → ``INVALID``.
- Signature valid && now ≤ expires_at → ``VALID``.
- Signature valid && expires_at < now ≤ expires_at + grace → ``EXPIRED_GRACE``
  (still usable; banner + log).
- Signature valid && now > expires_at + grace → ``EXPIRED_BLOCKED`` (runs and
  CI blocked; evidence/export stays read-only).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.licensing.tiers import tier_claims, tiers

logger = logging.getLogger(__name__)

__all__ = [
    "GRACE_DAYS",
    "LicenseClaims",
    "LicenseResult",
    "LicenseStatus",
    "LicenseValidationError",
    "SigningKeyError",
    "sign_license",
    "verify_license",
    "load_license",
    "license_status",
    "effective_tier",
    "feature_enabled",
    "vendor_public_key",
]

# Default grace period after expiry before runs/CI are blocked (spec §5.4, 7
# days — overridable via AITEST_LICENSE_GRACE_DAYS).
GRACE_DAYS: int = 7

# The deployment's shipped public key. The vendor holds the signing key (Cat
# Tan Operations); this public key ships in the repo and is the trust root for
# all stock builds. It is deliberately NOT overridable by the customer: the
# trust root must not be customer-settable (that would let a stock build
# self-sign its way into paid tier without a fork). Rotation ships with a
# product release (docs/security/license-key-ops.md). See B-050.
VENDORED_PUBLIC_KEY_B64 = "QOzKE23yF9PBbrlN//ncQVPL+DIONBk8/bEo02IIz7w="


class LicenseValidationError(ValueError):
    """Raised when a license token is structurally invalid."""


class SigningKeyError(RuntimeError):
    """Raised when the vendor signing key cannot be loaded (license_gen)."""


@dataclass(frozen=True)
class LicenseClaims:
    """The claims a signed license carries."""

    deployment_id: str
    tier: str
    claims: tuple[str, ...] = ()
    issued_at: str = ""
    expires_at: str = ""
    issuer: str = "cat-tan-operations"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LicenseClaims:
        try:
            return cls(
                deployment_id=str(data["deployment_id"]),
                tier=str(data["tier"]),
                claims=tuple(str(c) for c in data.get("claims", [])),
                issued_at=str(data.get("issued_at", "")),
                expires_at=str(data.get("expires_at", "")),
                issuer=str(data.get("issuer", "cat-tan-operations")),
            )
        except (KeyError, TypeError) as exc:
            raise LicenseValidationError(f"License payload missing/invalid field: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "tier": self.tier,
            "claims": list(self.claims),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "issuer": self.issuer,
        }


def _now_ts() -> int:
    return int(time.time())


def _ts(iso: str) -> int:
    """Parses an ISO timestamp to epoch; tolerates naive/UTC-flagged input."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


class LicenseStatus:
    """Enum-ish statuses for license_state (string constants)."""

    UNLICENSED = "unlicensed"
    VALID = "valid"
    EXPIRED_GRACE = "expired_grace"
    EXPIRED_BLOCKED = "expired_blocked"
    INVALID = "invalid"


@dataclass
class LicenseResult:
    """Outcome of verifying a license token."""

    status: str  # LicenseStatus.*
    tier: str = "free"
    claims: frozenset[str] = frozenset()
    deployment_id: str = ""
    expires_at: str = ""
    grace_until: str = ""
    reason: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """True when runs/CI are allowed (valid, grace, or unlicensed-free)."""
        return self.status in (LicenseStatus.VALID, LicenseStatus.EXPIRED_GRACE, LicenseStatus.UNLICENSED)

    @property
    def headline(self) -> str:
        if self.status == LicenseStatus.VALID:
            return f"License valid — {self.tier} tier (deployment {self.deployment_id or '?'})."
        if self.status == LicenseStatus.EXPIRED_GRACE:
            return f"License expired — running on grace until {self.grace_until or 'soon'}."
        if self.status == LicenseStatus.EXPIRED_BLOCKED:
            return "License expired — new runs blocked; evidence is read-only."
        if self.status == LicenseStatus.INVALID:
            return "License invalid — running unlicensed (free tier)."
        return "No license — running on the free tier."


# ---------------------------------------------------------------------------
# Signing (vendor / tests)
# ---------------------------------------------------------------------------


def sign_license(claims: LicenseClaims, private_key: bytes) -> str:
    """Sign *claims* with an ed25519 *private_key* (raw bytes); returns the token.

    The key is the vendor's signing key. Raising :class:`SigningKeyError` keeps
    ``license_gen`` honest — signing never silently falls back.
    """
    if len(private_key) != 32:
        raise SigningKeyError("ed25519 private key must be 32 raw bytes.")
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)
    payload_b64 = base64.urlsafe_b64encode(json.dumps(claims.to_dict()).encode("utf-8")).decode("ascii")
    signature = priv.sign(payload_b64.encode("ascii"))
    sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii")
    return f"{payload_b64}.{sig_b64}"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _b64decode(data: str) -> bytes:
    """base64url-decode, tolerating missing ``=`` padding."""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _decode_public_key(public_key_b64: str) -> ed25519.Ed25519PublicKey:
    try:
        raw = base64.b64decode(public_key_b64)
    except (ValueError, TypeError) as exc:
        raise LicenseValidationError("Invalid public-key encoding (expected base64).") from exc
    if len(raw) != 32:
        raise LicenseValidationError("ed25519 public key must be 32 raw bytes.")
    return ed25519.Ed25519PublicKey.from_public_bytes(raw)


def vendor_public_key() -> str:
    """The deployment's trust root — always the vendored key.

    Deliberately not overridable by the customer (B-050): the trust root must
    not be customer-settable, or a stock build could self-sign its way into
    paid tier. Rotation ships with a product release.
    """
    return VENDORED_PUBLIC_KEY_B64


def verify_license(
    token: str | None, public_key: str | None = None, *, now: int | None = None, grace_days: int | None = None
) -> LicenseResult:
    """Verify *token* offline; return a :class:`LicenseResult`.

    *now* (epoch) overrides the clock for tests. *grace_days* overrides the
    default (7). A missing/empty token → ``UNLICENSED`` (free tier).
    """
    if not token or not token.strip():
        return LicenseResult(LicenseStatus.UNLICENSED, reason="No license key configured — running on the free tier.")

    pk_b64 = public_key or VENDORED_PUBLIC_KEY_B64
    try:
        pub = _decode_public_key(pk_b64)
    except LicenseValidationError as exc:
        return LicenseResult(LicenseStatus.INVALID, reason=str(exc))

    try:
        payload_b64, sig_b64 = token.strip().split(".", 1)
        payload = json.loads(_b64decode(payload_b64))
        claims = LicenseClaims.from_dict(payload)
    except (ValueError, json.JSONDecodeError, binascii.Error, LicenseValidationError) as exc:
        return LicenseResult(LicenseStatus.INVALID, reason=f"Token malformed: {exc}")

    # Signature check — the hard gate.
    try:
        pub.verify(_b64decode(sig_b64), payload_b64.encode("ascii"))
    except InvalidSignature, ValueError:
        return LicenseResult(LicenseStatus.INVALID, reason="Signature does not verify — the key was altered or forged.")

    # Well-formed claims (tier must exist in the tier table; unknown tier is
    # demoted to free with a warning rather than hard-failing validity).
    tier = claims.tier if claims.tier in tiers() else "free"
    tier_spec = tiers().get(tier)
    effective_claims = frozenset(claims.claims) | (tier_spec.claims if tier_spec is not None else frozenset())

    now_ts = now if now is not None else _now_ts()
    expires = _ts(claims.expires_at)
    grace = grace_days if grace_days is not None else GRACE_DAYS
    grace_until = _iso(expires + grace * 86400)

    if expires and now_ts > expires + grace * 86400:
        status = LicenseStatus.EXPIRED_BLOCKED
        reason = "License expired and the grace period has ended — new runs and CI generations are blocked."
    elif expires and now_ts > expires:
        status = LicenseStatus.EXPIRED_GRACE
        reason = "License expired — within the grace period; runs still allowed."
    else:
        status = LicenseStatus.VALID
        reason = "License signature valid."

    return LicenseResult(
        status=status,
        tier=tier,
        claims=effective_claims,
        deployment_id=claims.deployment_id,
        expires_at=claims.expires_at,
        grace_until=grace_until if status in (LicenseStatus.EXPIRED_GRACE, LicenseStatus.EXPIRED_BLOCKED) else "",
        reason=reason,
        data=claims.to_dict(),
    )


def load_license() -> str | None:
    """Load the license token from env/file in this order:

    1. ``AITEST_LICENSE_KEY`` — inline token (CI-friendly).
    2. ``AITEST_LICENSE_FILE`` — path to a token file.
    3. ``~/.ai-test-gen/license.key`` — the deployment's settings-dir key file.
    """
    inline = os.environ.get("AITEST_LICENSE_KEY", "").strip()
    if inline:
        return inline

    from pathlib import Path

    file_path = os.environ.get("AITEST_LICENSE_FILE", "").strip()
    if not file_path:
        try:
            from src.secure_config import _config_dir

            file_path = str(_config_dir() / "license.key")
        except Exception:  # pragma: no cover - config dir is always creatable
            return None
    path = Path(file_path)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    return None


def license_status(now: int | None = None) -> LicenseResult:
    """The effective license state of this deployment (env/file → verify)."""
    return verify_license(load_license(), now=now)


def effective_tier(now: int | None = None) -> str:
    """The tier the deployment currently runs under (free when unlicensed)."""
    return license_status(now=now).tier


def feature_enabled(feature: str, tier: str | None = None, now: int | None = None) -> bool:
    """True when *feature* is granted by the current (or given) tier.

    An unlicensed deployment is the free tier; the OSS core claims (generate,
    evidence export, self-heal, RAG learning) are always enabled there. An
    expired-beyond-grace or invalid license is *not* a downgrade of the OSS
    core either — only CI/headless *runs* are withheld until a valid license is
    present (spec §5.4 failure UX: license presence is an upgrade, never a
    lockout).
    """
    if tier is None:
        result = license_status(now=now)
        tier = result.tier
    return feature in tier_claims(tier)
