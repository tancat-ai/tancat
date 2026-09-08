---
purpose: >
  Offline ed25519-signed license validation (Phase 6e, spec §5.4). A JWT-ish token
  (payload_b64.signature_b64, no JWT library — hand-rolled base64 + the existing cryptography
  dependency) carrying {deployment_id, tier, claims, issued_at, expires_at, issuer}. Validated
  at startup and before CI runs with ZERO network calls; 7-day grace; unlicensed = free tier.
lines: ~340
created: "2026-09-05"
---

# `src/licensing/license.py`

## High-Level Purpose

**Open-core honesty:** this is *entitlement/support marking*, not DRM. A modified fork can strip
it — accepted and documented. The key's real value is ToS entitlement, honest tier enforcement
for stock builds, and the air-gap premium bundle.

Validation contract (zero network calls):
- No key configured → `UNLICENSED` (free tier — open core stays usable).
- Signature invalid / payload malformed → `INVALID`.
- now ≤ expires_at → `VALID`; expires_at < now ≤ expires_at + grace → `EXPIRED_GRACE` (usable,
  banner); past grace → `EXPIRED_BLOCKED` (runs/CI blocked, evidence read-only).

## Public API

### `class LicenseClaims(deployment_id, tier, claims=(), issued_at="", expires_at="", issuer="cat-tan-operations")`
Payload model with `from_dict` / `to_dict` (JSON round-trip).

### `sign_license(claims, private_key: bytes) -> str`
Vendor/tests: ed25519-sign the claims (raw 32-byte private key); returns `payload_b64.sig_b64`.

### `verify_license(token, public_key=None, *, now=None, grace_days=None) -> LicenseResult`
The hard gate: empty token → `UNLICENSED`; malformed → `INVALID`; signature verify → `INVALID`;
then expiry vs `now` (+ grace) → `VALID` / `EXPIRED_GRACE` / `EXPIRED_BLOCKED`. Unknown tier is
demoted to free with a warning (never hard-fails validity). `now`/`grace_days` override for tests.

### `LicenseResult` (dataclass)
`status`, `tier`, `claims` (frozenset), `deployment_id`, `expires_at`, `grace_until`, `reason`,
`data`. `usable` = valid/grace/unlicensed; `headline` = one-line banner text.

### Accessors
- `load_license() -> str | None` — `AITEST_LICENSE_KEY` → `AITEST_LICENSE_FILE` →
  `~/.ai-test-gen/license.key`.
- `license_status(now=None) -> LicenseResult` — the deployment's effective state.
- `effective_tier(now=None) -> str` — tier under which the deployment runs (free when
  unlicensed).
- `feature_enabled(feature, tier=None, now=None) -> bool` — claim check. A blocked/invalid
  license is NOT a downgrade of the OSS core — only CI/headless runs are withheld until a valid
  license exists (spec §5.4: license presence is an upgrade, never a lockout).
- `vendor_public_key() -> str` — the trust root, always the vendored key (not customer-settable, B-050).

## How It Works (internals)

### `verify_license(token, ...)` — the verification ladder
1. `_decode_public_key(public_key_b64)` — base64 → 32 raw bytes → `Ed25519PublicKey`;
   bad encoding/size → `VALIDATION INVALID`.
2. Split `payload_b64 "." sig_b64`; `_b64decode` (padding-tolerant) → JSON → `LicenseClaims`
   (`from_dict` raises `LicenseValidationError` on missing fields).
3. `pub.verify(_b64decode(sig_b64), payload_b64)` — the hard signature gate; bad sig →
   `INVALID` ("the key was altered or forged").
4. Well-formedness: tier must exist in the tier table (else demoted to free); effective claims =
   token claims ∪ tier table claims.
5. Expiry: `_ts(expires_at)` vs `now_ts` (grace = `grace_days` or `GRACE_DAYS`=7) →
   blocked / grace / valid; `grace_until` reported for the two expired states.

### `_b64decode(data)` — base64url decode, tolerating missing `=` padding
Real-world tokens frequently strip padding; the verifier pads to a multiple of 4 before decode.

### `sign_license(claims, private_key)` — token minting
Base64url(json payload) + ed25519 signature over the payload string; `SigningKeyError` if the
key isn't 32 raw bytes (the vendor tool never silently falls back).

### Internal utilities
- `_now_ts()` / `_ts(iso)` / `_iso(ts)` — epoch↔ISO conversion (naive timestamps assumed UTC).
- `VENDORED_PUBLIC_KEY_B64` — the shipped default public key (Cat Tan Operations holds the
  signing side — the vendor tool `scripts/license_gen.py` can mint a fresh keypair).