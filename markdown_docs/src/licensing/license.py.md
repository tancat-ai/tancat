---
purpose: >
  The licence gate: one signed licence file (src/licensing/signed_file.py) verified offline
  against a vendored ed25519 public key, or nothing (free tier). Reports the tier the
  deployment runs under and answers the feature gates. No token format, no activation call,
  no network.
lines: ~150
created: "2026-09-05"
updated: "2026-11-19"
---

# `src/licensing/license.py`

## High-Level Purpose

**Open-core honesty:** this is *entitlement/support marking*, not DRM. A modified fork can strip
it — accepted and documented. The licence's real value is ToS entitlement and honest tier
enforcement for stock builds.

**One mechanism (j-0309 / t-1468).** The entitlement is a signed licence file or nothing:

- a valid signed file → `VALID`, with its tier and licence id;
- a file that exists but does not verify → `INVALID`, with the reason from the verifier;
- no file → `UNLICENSED` (free tier — open core stays usable).

The token format (`payload_b64.signature_b64`), its env vars (`AITEST_LICENSE_KEY`,
`AITEST_LICENSE_FILE`), `scripts/license_gen.py` and the UI paste box are **deleted**. There is
no grace period and no `expires_at`; the only date a licence carries is `window_end`, the last
day a *build* released inside the purchase window may run (the version the buyer holds keeps
working).

**Zero network calls:** this module imports no network code; the AST test over
`src/licensing/` and the egress audit both enforce it.

## Public API

### `VENDORED_PUBLIC_KEY_B64`, `vendor_public_key() -> str`

The trust root the signed file is verified against. Not customer-settable (B-050); rotation ships
with a product release.

### `class LicenseStatus`

String constants: `UNLICENSED`, `VALID`, `INVALID`.

### `class LicenseResult`

`status`, `tier`, `claims` (frozenset), `licence_id`, `reason`. Properties: `usable` (valid or
unlicensed) and `headline` (the one-line banner the UI shows).

### `license_status() -> LicenseResult`

One call to `src.licensing.entitlement.resolve()` - the single place the precedence lives.

### `effective_tier() -> str`

The tier the deployment runs under (free when unlicensed or refused).

### `feature_enabled(feature, tier=None) -> bool`

True when the tier's claims include `feature`; the OSS core claims are free.

## Where the rest lives

- `src/licensing/signed_file.py` — the file format, signing and verification.
- `src/licensing/entitlement.py` — where the file is looked for (`AITEST_LICENCE_FILE`, else the
  settings directory), and the update-window checks.
- `src/licensing/window.py` — the release date, the 12-month window, and the refusal wording.
