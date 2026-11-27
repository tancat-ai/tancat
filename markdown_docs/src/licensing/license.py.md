---
purpose: >
  The licence gate: the activated key in this machine's cache, the tier it grants,
  and the feature gates the rest of the product asks. No network - activation and
  the update check live in activation.py.
lines: ~130
created: "2026-09-05"
updated: "2026-11-26"
---

# `src/licensing/license.py`

## High-Level Purpose

**Open-core honesty:** this is *entitlement/support marking*, not DRM. A modified fork
can strip it - accepted and documented. The value is honest tier enforcement for
stock builds and an enforceable ToS.

**One mechanism (owner, 2026-11-26).** The entitlement is a licence key the store
issued with the order, activated once through our relay and then cached:

- an activated key in the cache -> `VALID`, with its tier and masked key;
- a cache file that exists but cannot be used -> `INVALID`, with the reason;
- no cache -> `UNLICENSED` (free tier - open core stays usable).

The signed-file mechanism (`signed_file.py`, the vendored public key, the signer) is
**deleted**, not dormant. A test asserts no second verification route exists.

## `LicenseStatus`

String constants: `UNLICENSED`, `VALID`, `INVALID`.

## `LicenseResult`

`status`, `tier`, `claims`, `licence_id` (the masked key), `reason`, `window_end`,
plus:

- `usable` - true for a valid licence and for the free tier;
- `headline` - the sentence the sidebar shows.

## Functions

- `license_status() -> LicenseResult` - read the cache (never the network).
- `effective_tier() -> str` - the tier the deployment runs under, `free` when none.
- `feature_enabled(feature, tier=None) -> bool` - `feature in tier_claims(tier)`.

## What it does not do

- It does not validate the key: `activation.validate()` does that, at update time.
- It does not write anything: the cache belongs to `activation.py`.
- It never blocks the free core - only CI/headless runs are withheld when
  `AITEST_ENFORCE_LICENSING=1` and no activated key is present.

## Related

- `src/licensing/activation.py` - the calls and the cache.
- `src/licensing/entitlement.py` - `resolve()`, which this reads.
- `src/usage_meter.py` - the caps, which follow this tier.
