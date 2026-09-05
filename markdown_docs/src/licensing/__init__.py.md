---
purpose: >
  Licensing package (Phase 6e): offline ed25519 license validation + per-deployment tier config.
  Open-core honesty — a license key is an entitlement marker, not DRM. Everything is purely
  local, zero network calls (the egress audit enforces that).
lines: ~57
created: "2026-09-05"
---

# `src/licensing/__init__.py`

## High-Level Purpose

Public package surface for the licensing subsystem. Re-exports the tier table and the license
validation API so consumers import from `src.licensing` without knowing the file layout:
- **`tiers`** — `DEFAULT_TIERS`, `TierSpec`, `FREE_TIER`, `tier_label`, `tier_claims`,
  `limit_for`, `feature_required_tier`, `is_paid_tier`.
- **`license`** — `LicenseResult`, `LicenseStatus`, `LicenseClaims`, `sign_license`,
  `verify_license`, `load_license`, `license_status`, `effective_tier`, `feature_enabled`,
  `vendor_public_key`, `GRACE_DAYS`, `LicenseValidationError`, `SigningKeyError`.

## Public API

Nothing defined here — it is a pure re-export module (`__all__` lists every public name).
The real logic lives in `src/licensing/license.py` (validation) and `src/licensing/tiers.py`
(tier table).

## How It Works (internals)

No private logic. Consumers: the usage meter (`effective_tier`, `is_paid_tier`), the UI
sidebar license banner, and `ci_generate --json` (license + usage section).