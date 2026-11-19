"""The licence: one signed file we issue, verified offline, and the tier it grants.

**One mechanism, not two (j-0309).** The entitlement is a signed licence file
(``src/licensing/signed_file.py``) or nothing, in which case the deployment is Free.
There is no token format, no key file written by an activation step, and no
environment variable carrying a secret key. Two verification routes for one thing is
how the next person changes one and not the other.

**What this module publishes** (the whole public surface):

- :data:`VENDORED_PUBLIC_KEY_B64` and :func:`vendor_public_key` - the trust root the
  signed file is verified against. Not customer-settable (B-050).
- :class:`LicenseStatus` - ``UNLICENSED`` / ``VALID`` / ``INVALID``.
- :class:`LicenseResult` - the status, the tier, the licence id, the reason, and a
  ``headline`` for the UI.
- :func:`license_status` - read the signed file (or find none) and report.
- :func:`effective_tier` and :func:`feature_enabled` - the tier the deployment runs
  under, and the feature gates the rest of the product asks for.

**Open-core honesty:** this is entitlement/support marking, not DRM. A fork can strip
it. The value is honest tier enforcement for stock builds and an enforceable ToS.

**No network calls:** this module imports no network code, and the AST test over
``src/licensing/`` proves the package cannot call out.
"""

from __future__ import annotations

__all__ = [
    "LicenseResult",
    "LicenseStatus",
    "VENDORED_PUBLIC_KEY_B64",
    "effective_tier",
    "feature_enabled",
    "license_status",
    "vendor_public_key",
]

# The deployment's shipped public key. The vendor holds the signing key (Cat Tan
# Operations); this public key ships in the repo and is the trust root for all stock
# builds. Deliberately NOT overridable by the customer: a customer-settable trust root
# would let a stock build sign its way into paid tier (B-050). Rotation ships with a
# product release - see docs/security/license-key-ops.md.
VENDORED_PUBLIC_KEY_B64 = "8E9jcDty0vLC8W6jzovJE9m/aHTFcLYtOEno/00b/S4="


class LicenseStatus:
    """Enum-ish statuses for the licence state (string constants)."""

    UNLICENSED = "unlicensed"
    VALID = "valid"
    INVALID = "invalid"


class LicenseResult:
    """Outcome of reading the licence file."""

    def __init__(
        self,
        status: str,
        *,
        tier: str = "free",
        claims: frozenset[str] = frozenset(),
        licence_id: str = "",
        reason: str = "",
    ) -> None:
        self.status = status
        self.tier = tier
        self.claims = claims
        self.licence_id = licence_id
        self.reason = reason

    @property
    def usable(self) -> bool:
        """True when runs/CI are allowed (a valid licence, or the free tier)."""
        return self.status in (LicenseStatus.VALID, LicenseStatus.UNLICENSED)

    @property
    def headline(self) -> str:
        if self.status == LicenseStatus.VALID:
            return f"License valid — {self.tier} tier (licence {self.licence_id or '?'})."
        if self.status == LicenseStatus.INVALID:
            return f"License file refused — running unlicensed (free tier): {self.reason}"
        return "No license file — running on the free tier."

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"LicenseResult(status={self.status!r}, tier={self.tier!r}, licence_id={self.licence_id!r})"


def vendor_public_key() -> str:
    """The deployment's trust root - always the vendored key.

    Deliberately not overridable by the customer (B-050): the trust root must not be
    customer-settable, or a stock build could self-sign its way into paid tier.
    Rotation ships with a product release.
    """
    return VENDORED_PUBLIC_KEY_B64


def license_status() -> LicenseResult:
    """The licence this deployment holds: a verified signed file, or nothing."""
    from src.licensing.entitlement import resolve
    from src.licensing.tiers import tier_claims

    state = resolve()
    if state.source == "signed" and state.licence is not None:
        return LicenseResult(
            LicenseStatus.VALID,
            tier=state.tier,
            claims=frozenset(tier_claims(state.tier)),
            licence_id=state.licence.id,
            reason="Signed licence file verified offline.",
        )
    if state.problem:
        return LicenseResult(LicenseStatus.INVALID, reason=state.problem)
    return LicenseResult(LicenseStatus.UNLICENSED, reason="No licence file — running on the free tier.")


def effective_tier() -> str:
    """The tier the deployment currently runs under (free when unlicensed)."""
    return license_status().tier


def feature_enabled(feature: str, tier: str | None = None) -> bool:
    """True when *feature* is granted by the current (or given) tier.

    An unlicensed deployment is the free tier; the OSS core claims (generate,
    evidence export, self-heal, RAG learning) are always enabled there. A refused
    licence is *not* a downgrade of the OSS core either — only CI/headless *runs* are
    withheld until a valid licence is present (licence presence is an upgrade, never
    a lockout).
    """
    from src.licensing.tiers import tier_claims

    if tier is None:
        tier = license_status().tier
    return feature in tier_claims(tier)
