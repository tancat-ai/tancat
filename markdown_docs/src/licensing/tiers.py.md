---
purpose: >
  Per-deployment tier configuration (Phase 6e, spec §5.5): one data-driven table mapping a tier
  key (free / self-serve / pro / airgap) to its label, additive feature claims, and usage
  limits. The feature toggles the tier gates are enforcement points that already exist in the
  code (POM flag, Jira export, self-heal, RAG) — this table is the entitlement side.
lines: ~157
created: "2026-09-05"
---

# `src/licensing/tiers.py`

## High-Level Purpose

The proposed split (spec §5.5, grill question §9 Q1), data-driven so it can be re-tuned without
code changes:

| Tier | Claims (additive) | Limits |
|------|-------------------|--------|
| `free` | generate, evidence_export, self_heal, rag_learning | runs 25/mo, exports 10/mo |
| `self-serve` | + jira_export | unlimited |
| `pro` | + pom, multi_site, ci_runs | unlimited |
| `airgap` | + private_network, support | unlimited |

Self-healing and RAG stay in the free core (already shipped OSS features — §9 Q1 bias:
re-locking shipped work is a retention risk; the paid claim is support/onboarding).

## Public API

### `class TierSpec(key, label, claims: frozenset[str], limits: dict[str, int])`
One tier: additive feature claims + numeric usage limits.

### `tiers() -> dict[str, TierSpec]`
The current table (env override `AITEST_TIERS_JSON` applied once per process).

### Lookups
- `tier_label(tier)` / `tier_claims(tier)` — display label / claim set (empty for unknown tiers).
- `limit_for(tier, limit_name, default=None)` — a tier's numeric limit (e.g. `runs_per_month`).
- `feature_required_tier(feature) -> str | None` — the LOWEST tier granting the feature (used
  by gates to render "requires Pro tier" and by `feature_enabled`).
- `is_paid_tier(tier)` — any tier other than `free`.

### Constants
- `FEATURES` — canonical feature-claim names (single source so gates and tier tables agree).
- `FREE_TIER = "free"`, `DEFAULT_TIERS` — the default table (no env override applied).

## How It Works (internals)

### `tiers()` / `_load_override()` / `_TIERS_CACHE` — env override
`AITEST_TIERS_JSON` (a JSON file path) can re-tune the split without code changes: keys are tier
names, values `{label, claims[], limits{}}`; defaults merge for any tier not present. A corrupt
or missing file silently falls back to `_tiers()`. The result is cached in `_TIERS_CACHE` once
per process.

### `feature_required_tier(feature)` — the lowest-granting tier
Iterates the table in insertion order (free → airgap) and returns the first tier whose claims
contain the feature — the "requires X tier" message source.

### Internal utilities
- `_tiers()` — the hardcoded default table the override layer merges with.