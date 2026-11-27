# Licence Operations

**Created:** 2026-09-06 as signing-key operations; rewritten 2026-11-26 for licence keys.
**Owner:** Cat Tan Operations Ltd (company number 17576111)
**Scope:** the secret that makes licensing work, and the two moments the product uses it.
Code: `src/licensing/activation.py` (the product side), `services/licence-relay/` (the
relay), `src/licensing/tiers.py` (the tier table).

---

## 1. What exists today

- **A key the store issues with the order.** The store's licence-key feature creates one key
  per purchase, with an activation limit (1) and no expiry. The buyer sees it on the
  confirmation page, in the receipt and in the customer portal.
- **One activation, at the prompt.** The buyer runs `tancat licence activate <KEY>` (or
  uses the sidebar field). The product sends the key and an instance name to our relay;
  the relay holds the store's **merchant API key** and answers. The product never holds
  the merchant key and never addresses the store directly.
- **One check, at update.** When a new version is installed, the product asks the relay
  to validate the stored key and instance. A revoked or expired key refuses the upgrade;
  an unreachable relay lets it proceed on the cached licence.
- **Nothing in between.** Startup, runs and premium features read
  `~/.ai-test-gen/licence.json` (or `AITEST_LICENCE_FILE`). There is no periodic check.
- **No signed file, no vendored key, no signer.** The Ed25519 mechanism was deleted on
  2026-11-26; `scripts/maintenance/issue_licence.py` and `signed_file.py` are gone.

## 1a. The store's error codes, as observed

Read this, not the reference page's table: the store does not use the statuses its
docs imply. Observed on the live test API on **2026-11-26**:

| What happened | Status | Body |
|---|---|---|
| the single activation was already used | **400** (not 403) | `{"status":400,"error":"Bad Request","message":"Activation limit reached"}` |
| the instance was already released | **400** (not 409) | `{"status":400,"error":"Bad Request","message":"License key instnace is already deactivated"}` - their spelling |

The relay therefore classifies on the **message** as well as the status, and answers
`{"error": code}` only, never the store's text. The recorded bodies are replayed
through the Worker by `tests/test_licence_relay_contract.py`
(`tests/fixtures/relay/store-error-bodies.json`), so a change in their wording shows
up as a failing test rather than as a wrong sentence to a buyer.

## 2. The one secret

The **merchant API key** is the whole security boundary. It lives:

- in the store's dashboard, under Settings -> API;
- in the relay only, as a Cloudflare secret (`npx wrangler secret put API_KEY`);
- on this machine as a backup in the password manager, never in the repository.

It is **not** in the product, not in a config file, not in CI and not in a wheel.

Rotate it: create a new key in the store, `wrangler secret put API_KEY`, deploy, then
revoke the old one. A rotation needs no product release, because the product never had
the key.

If the key leaks, an attacker can activate and deactivate keys. They cannot change what
a deployment already holds, because the product reads its own cache between updates.

## 3. The relay

`services/licence-relay` (Cloudflare Worker). Three endpoints - `activate`, `validate`,
`deactivate` - each a thin, named translation of the store's answer into our codes. The
README holds the deploy steps and the smoke test.

Why it exists: the store's licence API needs the merchant key, and a key in a shipped
package is a key in every customer's hands.

## 4. A buyer's two moments

| Moment | What is sent | What happens on failure |
|---|---|---|
| Activation | key + instance name | one sentence naming the reason; the cache is untouched; the product stays on the free tier |
| Update | key + instance id | revoked/expired/unknown refuses the upgrade and names the version that keeps working; no answer proceeds on the cached licence |

## 5. Moving a machine

`tancat licence release` asks the relay to free the instance, then deletes the cache. A
failed *activation* never deletes a working cache; a release deletes it whichever way the
relay answers, because a buyer moving machines must not be stuck.

## 6. The accepted trade, stated plainly

There is no periodic check. A key the store disables today is noticed at the buyer's next
update, not before. That is the price of a product that works offline, and the buyer
documents say so.

## 7. What this does not protect against

- A fork of the source can delete the check or write its own cache file. This is
  entitlement marking, not DRM.
- A buyer with the store's activation limit raised can activate on more machines.
- Anyone holding the merchant key can activate anything. That is why it is a secret and
  not a constant.
