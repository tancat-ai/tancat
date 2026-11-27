"""The licence: an activated key cached on this machine, and the tier it grants.

**One mechanism (owner, 2026-11-26).** The entitlement is a licence key the store
issued with the order, activated once through our relay and then cached. Whatever the
cache says is the truth between updates; there is no second verification route and no
token format.

**What this module publishes** (the whole public surface):

- :class:`LicenseStatus` - ``UNLICENSED`` / ``VALID`` / ``INVALID``.
- :class:`LicenseResult` - the status, the tier, the licence id, the reason, and a
  ``headline`` for the UI.
- :func:`license_status` - read the cache (or find none) and report.
- :func:`effective_tier` and :func:`feature_enabled` - the tier the deployment runs
  under, and the feature gates the rest of the product asks for.

**No network calls here.** Activation and the update check live in
``src/licensing/activation.py``; everything else reads the cache.

**Open-core honesty:** this is entitlement/support marking, not DRM. A fork can strip
it. The value is honest tier enforcement for stock builds and an enforceable ToS.
"""

from __future__ import annotations

__all__ = [
    "LicenseResult",
    "LicenseStatus",
    "effective_tier",
    "feature_enabled",
    "license_status",
]


class LicenseStatus:
    """Enum-ish statuses for the licence state (string constants)."""

    UNLICENSED = "unlicensed"
    VALID = "valid"
    INVALID = "invalid"


class LicenseResult:
    """Outcome of reading the licence cache."""

    def __init__(
        self,
        status: str,
        *,
        tier: str = "free",
        claims: frozenset[str] = frozenset(),
        licence_id: str = "",
        reason: str = "",
        window_end: str = "",
    ) -> None:
        self.status = status
        self.tier = tier
        self.claims = claims
        self.licence_id = licence_id
        self.reason = reason
        self.window_end = window_end

    @property
    def usable(self) -> bool:
        """True when runs/CI are allowed (an active licence, or the free tier)."""
        return self.status in (LicenseStatus.VALID, LicenseStatus.UNLICENSED)

    @property
    def headline(self) -> str:
        if self.status == LicenseStatus.VALID:
            window = f", updates to {self.window_end}" if self.window_end else ""
            return f"Licence key active - {self.tier} tier (activated on this machine{window})."
        if self.status == LicenseStatus.INVALID:
            return f"Stored licence could not be used - running on the free tier: {self.reason}"
        return "No licence key - running on the free tier."

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"LicenseResult(status={self.status!r}, tier={self.tier!r}, licence_id={self.licence_id!r})"


def license_status() -> LicenseResult:
    """The licence this machine holds: an activated key in the cache, or nothing."""
    from src.licensing.entitlement import resolve
    from src.licensing.tiers import tier_claims

    state = resolve()
    if state.source == "activated" and state.activation is not None:
        return LicenseResult(
            LicenseStatus.VALID,
            tier=state.tier,
            claims=frozenset(tier_claims(state.tier)),
            licence_id=state.activation.masked_key,
            reason="Licence key activated on this machine.",
            window_end=state.window_end.isoformat() if state.window_end else "",
        )
    if state.problem:
        return LicenseResult(LicenseStatus.INVALID, reason=state.problem)
    return LicenseResult(LicenseStatus.UNLICENSED, reason="No licence key - running on the free tier.")


def effective_tier() -> str:
    """The tier the deployment currently runs under (free when unlicensed)."""
    return license_status().tier


def feature_enabled(feature: str, tier: str | None = None) -> bool:
    """True when *feature* is granted by the current (or given) tier.

    An unlicensed deployment is the free tier; the OSS core claims (generate,
    evidence export, self-heal, RAG learning) are always enabled there. A refused
    licence is *not* a downgrade of the OSS core either - only CI/headless *runs* are
    withheld until a valid licence is present (licence presence is an upgrade, never
    a lockout).
    """
    from src.licensing.tiers import tier_claims

    if tier is None:
        tier = license_status().tier
    return feature in tier_claims(tier)
