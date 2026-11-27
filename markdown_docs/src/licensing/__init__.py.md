---
purpose: >
  Licensing package: licence keys activated once through our relay, checked at
  update, read from the cache in between, plus the per-deployment tier table.
  Open-core honesty - a licence is an entitlement marker, not DRM.
lines: ~75
created: "2026-09-05"
updated: "2026-11-26"
---

# `src/licensing/__init__.py`

## High-Level Purpose

Public package surface for the licensing subsystem, so consumers import from
`src.licensing` without knowing the file layout:

- **`tiers`** - `DEFAULT_TIERS`, `TierSpec`, `FREE_TIER`, `tier_label`,
  `tier_claims`, `limit_for`, `feature_required_tier`, `is_paid_tier`.
- **`license`** - `LicenseResult`, `LicenseStatus`, `license_status`,
  `effective_tier`, `feature_enabled`.
- **`activation`** - `Activation`, `ActivationResult`, `ValidationResult`,
  `activate`, `validate`, `deactivate`.

There are two mechanisms in a buyer's life and they are the same one: a key the
store issues with the order, activated once through `services/licence-relay`, then
cached. Activation and the update check are the only calls; everything else reads
`~/.ai-test-gen/licence.json`.

The token API and the **signed-file** API (`VENDORED_PUBLIC_KEY_B64`,
`vendor_public_key`, `signed_file`) are gone - deleted with the Ed25519 mechanism on
2026-11-26. A test asserts no second verification route survives.

## Related

- `activation.py.md`, `entitlement.py.md`, `license.py.md`, `merchant.py.md`,
  `pricing.py.md`, `tiers.py.md`, `window.py.md` in this directory.
