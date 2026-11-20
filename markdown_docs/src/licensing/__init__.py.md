---
purpose: >
  Licensing package (Phase 6e): offline ed25519 license validation + per-deployment tier config.
  Open-core honesty — a license key is an entitlement marker, not DRM. Everything is purely
  local, zero network calls (the egress audit enforces that).
lines: ~40
created: "2026-09-05"
updated: "2026-11-19"
---

# `src/licensing/__init__.py`

## High-Level Purpose

Public package surface for the licensing subsystem. Re-exports the tier table and the
one-licence-mechanism API so consumers import from `src.licensing` without knowing the file layout:

- **`tiers`** — `DEFAULT_TIERS`, `TierSpec`, `FREE_TIER`, `tier_label`, `tier_claims`,
  `limit_for`, `feature_required_tier`, `is_paid_tier`.
- **`license`** — `VENDORED_PUBLIC_KEY_B64`, `LicenseResult`, `LicenseStatus`, `license_status`,
  `effective_tier`, `feature_enabled`, `vendor_public_key`.

The token API (`LicenseClaims`, `sign_license`, `verify_license`, `load_license`,
`save_license_key`, `GRACE_DAYS`, `LicenseValidationError`, `SigningKeyError`) is **gone**
(t-1468): a signed licence file is the only mechanism, verified offline.
