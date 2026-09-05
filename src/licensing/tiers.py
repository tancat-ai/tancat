"""Per-deployment tier configuration (Phase 6e, spec §5.5).

A single data-driven table mapping a tier key to its label, feature claims, and
usage limits. The **feature toggles the tier gates are enforcement points that
already exist in the code** (POM flag, Jira export, self-heal, RAG) — this table
is the entitlement side; the gates read ``feature_enabled`` / ``limit_for``.

The proposed split (from spec §5.5, grill question §9 Q1 — data-driven so it
can be re-tuned without code changes):

| Tier      | Claims (additive)                              | Limits                  |
|-----------|------------------------------------------------|-------------------------|
| free      | core generate, evidence export (CSV/JSON/HTML), self-heal, RAG/flow learning | runs 25/mo, exports 10/mo |
| self-serve| + Jira export                                  | unlimited               |
| pro       | + POM mode, multi-site, CI runs                | unlimited               |
| airgap    | + private-network support, support/onboarding  | unlimited               |

Self-healing and RAG stay in the free core (they are already shipped OSS
features — §9 Q1 bias: re-locking shipped work is a retention risk, the paid
claim is support/onboarding).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "TierSpec",
    "DEFAULT_TIERS",
    "FREE_TIER",
    "tier_label",
    "tier_claims",
    "limit_for",
    "feature_required_tier",
    "is_paid_tier",
]


# Canonical feature claim names. Keep in one place so gates and tiers agree.
FEATURES = {
    "generate": "core test generation",
    "evidence_export": "evidence export (CSV/JSON/HTML)",
    "self_heal": "self-healing",
    "rag_learning": "RAG / flow-memory learning",
    "jira_export": "Jira report export",
    "pom": "Page Object Model mode",
    "multi_site": "multi-site suites",
    "ci_runs": "CI / headless runs",
    "private_network": "private-network target support",
    "support": "support + onboarding bundle",
}


@dataclass(frozen=True)
class TierSpec:
    """One tier: label, additive feature claims, and usage limits."""

    key: str
    label: str
    claims: frozenset[str] = field(default_factory=frozenset)
    limits: dict[str, int] = field(default_factory=dict)  # e.g. {"runs_per_month": 25}


FREE_TIER = "free"


def _tiers() -> dict[str, TierSpec]:
    """The default tier table (overridable via ``AITEST_TIERS_JSON``)."""
    free_claims = {"generate", "evidence_export", "self_heal", "rag_learning"}
    return {
        "free": TierSpec(
            "free", "Free", frozenset(free_claims), {"runs_per_month": 25, "evidence_exports_per_month": 10}
        ),
        "self-serve": TierSpec("self-serve", "Self-Serve", frozenset(free_claims | {"jira_export"})),
        "pro": TierSpec("pro", "Pro", frozenset(free_claims | {"jira_export", "pom", "multi_site", "ci_runs"})),
        "airgap": TierSpec(
            "airgap",
            "Air-Gap Premium",
            frozenset(free_claims | {"jira_export", "pom", "multi_site", "ci_runs", "private_network", "support"}),
        ),
    }


def _load_override() -> dict[str, TierSpec]:
    """Apply ``AITEST_TIERS_JSON`` (a JSON file path) if set.

    Lets a deployment re-tune the split without code changes. The override
    must be a dict of tier-key → {label, claims[], limits{}}; defaults merge
    for any tier not present.
    """
    import json
    import os
    from pathlib import Path

    path = os.environ.get("AITEST_TIERS_JSON", "")
    if not path:
        return _tiers()
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return _tiers()
    base = _tiers()
    for key, spec in raw.items():
        base[key] = TierSpec(
            key=key,
            label=str(spec.get("label", key)),
            claims=frozenset(spec.get("claims", [])),
            limits={str(k): int(v) for k, v in spec.get("limits", {}).items()},
        )
    return base


_TIERS_CACHE: dict[str, TierSpec] | None = None


def tiers() -> dict[str, TierSpec]:
    """Current tier table (env override applied once per process)."""
    global _TIERS_CACHE
    if _TIERS_CACHE is None:
        _TIERS_CACHE = _load_override()
    return _TIERS_CACHE


DEFAULT_TIERS: dict[str, TierSpec] = _tiers()


def tier_label(tier: str) -> str:
    return tiers().get(tier, TierSpec(tier, tier)).label


def tier_claims(tier: str) -> frozenset[str]:
    spec = tiers().get(tier)
    return spec.claims if spec else frozenset()


def limit_for(tier: str, limit_name: str, default: int | None = None) -> int | None:
    """Return a tier's numeric limit (e.g. ``runs_per_month``) or *default*."""
    spec = tiers().get(tier)
    if spec is None:
        return default
    return spec.limits.get(limit_name, default)


def feature_required_tier(feature: str) -> str | None:
    """Return the *lowest* tier that grants *feature*, or None if no tier does.

    Used by gates to render "requires Pro tier" (and by `feature_enabled`). The
    tier order is the insertion order of the table (free → airgap).
    """
    for tier in tiers().values():
        if feature in tier.claims:
            return tier.key
    return None


def is_paid_tier(tier: str) -> bool:
    return tier in tiers() and tier != FREE_TIER
