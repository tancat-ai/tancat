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

from datetime import date

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
        if self.status == LicenseStatus.VALID and self.tier == "free":
            # A licence that is valid but no longer Pro: the reason says why
            # (window ended, key expired or disabled), so the sentence is the
            # reason rather than a cheerful "active - pro".
            return self.reason or "Licence key active - free tier."
        if self.status == LicenseStatus.VALID:
            window = f", updates to {self.window_end}" if self.window_end else ""
            return f"Licence key active - {self.tier} tier (activated on this machine{window})."
        if self.status == LicenseStatus.INVALID:
            return f"Stored licence could not be used - running on the free tier: {self.reason}"
        return "No licence key - running on the free tier."

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"LicenseResult(status={self.status!r}, tier={self.tier!r}, licence_id={self.licence_id!r})"


def license_status(build_date: date | None = None) -> LicenseResult:
    """The licence this machine holds, WITH the update window folded in (j-0317).

    This is the one function that decides the tier: ``effective_tier()``,
    ``feature_enabled()``, the usage meter and the sidebar all read it, so the
    window cannot govern the upgrade gate and leave the tier unlimited.

    What a paid licence buys is one version plus 12 months of updates. Past that
    window the licence does not expire - the build that was released inside the
    window keeps working - but the tier is **Free**, with the free limits. The
    window comes from the stored ``created_at`` (purchase date + 12 months), the
    same arithmetic the upgrade gate uses; nothing here calls the network.

    A stored ``status`` of ``expired`` or ``disabled`` drops the tier the same way.

    ``build_date`` is the build's own release date (default: this build's
    ``RELEASE_DATE``), because the question is "was THIS build inside the window",
    not "is it still inside it today".
    """
    from src.licensing.entitlement import resolve
    from src.licensing.tiers import tier_claims
    from src.licensing.window import RELEASE_DATE, RENEWAL_COPY

    state = resolve()
    if state.source == "activated" and state.activation is not None:
        build = build_date or RELEASE_DATE
        stored_status = str(state.activation.status or "").strip().lower()
        window_end = state.window_end.isoformat() if state.window_end else ""
        # The SAME rule as activation (activation.py: only "active" passes): an
        # allow-list of bad words is a list, not a rule - "inactive", "revoked" or
        # a word this build has never seen would otherwise read as permission.
        if stored_status != "active":
            said = f"'{stored_status}'" if stored_status else "(no status)"
            why = (
                f"The store says this licence key is {said} - running on the free tier with the free "
                f"limits. Email hello@tancat.dev and we will sort it out."
            )
            return LicenseResult(
                LicenseStatus.VALID,
                tier="free",
                claims=frozenset(tier_claims("free")),
                licence_id=state.activation.masked_key,
                reason=why,
                window_end=window_end,
            )
        if state.window_end is not None and build > state.window_end:
            from src.version_info import installed_version

            held = installed_version()
            held_text = (
                f"Version {held} keeps working" if held and held != "unknown" else "The version you held keeps working"
            )
            why = (
                f"Your update window ended on {state.window_end.isoformat()}. {held_text} - "
                f"the tier is Free past the window, with the free limits. {RENEWAL_COPY}"
            )
            return LicenseResult(
                LicenseStatus.VALID,
                tier="free",
                claims=frozenset(tier_claims("free")),
                licence_id=state.activation.masked_key,
                reason=why,
                window_end=window_end,
            )
        return LicenseResult(
            LicenseStatus.VALID,
            tier=state.tier,
            claims=frozenset(tier_claims(state.tier)),
            licence_id=state.activation.masked_key,
            reason="Licence key activated on this machine.",
            window_end=window_end,
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
