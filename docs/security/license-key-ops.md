# License Key Operations (Phase 6e)

**Created:** 2026-09-06 (audit follow-up — BACKLOG B-053)
**Owner:** Cat Tan Operations (single-operator signing key holder)
**Scope:** operational security of the ed25519 license signing key. For the validation code, see `src/licensing/license.py`; for the tier table, `src/licensing/tiers.py`; for the spec, `docs/specs/FEATURE_SPEC_phase6_saas.md` §5.4.

---

## 1. What exists today

- **Offline ed25519 signing.** Keys are generated and tokens signed via `python scripts/license_gen.py` (`gen-keys` / `sign`). **No network calls are involved in validation** — the egress audit guarantees the licensing path adds zero outbound HTTP.
- **Vendored public key.** `src/licensing/license.py` ships `VENDORED_PUBLIC_KEY_B64`; it is the trust root for all stock builds and is **not overridable by the customer** (B-050, resolved: the customer-settable trust root was removed). The trust root must not be customer-settable — otherwise a stock build could self-sign its way into paid tier without a fork. Rotation ships with a product release (§5).
- **Token:** `payload_b64 "." signature_b64` (custom format, `cryptography`'s ed25519 primitive). Payload carries `deployment_id`, `tier`, `claims`, `issued_at`, `expires_at`, `issuer`.

## 2. The single-operator risk (why this doc exists)

| Event | Consequence |
|-------|-------------|
| Signing key **lost** | No new licenses can be issued until a new keypair ships (rotation = product release, §5). Existing unexpired licenses keep working. |
| Signing key **leaked** | Anyone can mint valid licenses for any tier, forever, for all stock builds. Offline validation means no revocation mechanism exists (§6). |

Both are existential for the licensing revenue model — this is the highest-value secret in the operation.

## 3. Key generation & storage

1. Generate on an offline machine: `python scripts/license_gen.py gen-keys`.
2. The **private key never enters the repo, cloud storage, or a chat transcript.** Store it in a secrets manager, or on encrypted offline media (LUKS/BitLocker volume, hardware token if available).
3. Record (outside the key material): key ID, creation date, which deployment pubkey it corresponds to, and who holds it. Single-operator today — name a secondary holder *before* launch (even a sealed escrow copy with a lawyer or a co-founder).

## 4. Backup

- Keep **at least two backups on separate media in separate locations** (e.g. one encrypted USB off-site, one secrets-manager entry).
- **Test recovery**, not just backup: on a clean machine, restore the key, sign a test token, and verify it against the vendored pubkey. An untested backup is a hope, not a backup.
- Re-test recovery after any `license_gen.py` format change.

## 5. Rotation (planned key compromise or periodic hygiene)

Rotation is a **product release**, not just a key ceremony:

1. Generate a new keypair; add the new public key to the vendored key(s) in `src/licensing/license.py` (today the code verifies exactly one key — rotation support for a transition window is a small code change; do it *before* you ever need emergency rotation).
2. Ship the release; issue new licenses signed by the new key.
3. Retire the old key after the transition window; update this doc + `VENDORED_PUBLIC_KEY_B64`.

Because the public key is vendored, customers must update the product to trust a new key — **plan an annual or biennial rotation cadence** so it is routine rather than emergency-driven.

## 6. Revocation (offline constraint)

There is no CRL/OCSP possibility in an air-gapped design. Revocation is achieved **contractually + cryptographically-by-expiry**:

- Issue licenses with **short `expires_at` windows** (annual at most; quarterly for high-risk customers). Non-renewal = revocation.
- `GRACE_DAYS` (default 7) means a non-renewed deployment keeps running for up to 7 days past expiry — take this into account when a customer relationship ends (issue the final license with an `expires_at` at contract end, not +12 months).
- If a *signing key* leaks: only rotation (§5) restores security for stock builds. This is why the backup/rotation plan exists before launch, not after.

## 7. Related items

- **B-050** — RESOLVED: the `AITEST_LICENSE_PUBKEY` customer-settable trust root was removed; the trust root is always the vendored key. If per-customer signing keypairs are needed, the on-book path is server-issued offline-verified (a separate item), not a customer-settable key.
- **B-051** — free-tier metering is local and resettable; document honestly.
- Spec: `docs/specs/FEATURE_SPEC_phase6_saas.md` §5.4 (license design contract).
