---
purpose: >
  Licence keys: activated once through our relay, checked again only when a new
  version is installed, and read from this machine's cache at every other moment.
  The only file in the licensing package that can reach the network.
lines: ~470
created: "2026-11-26"
updated: "2026-11-26"
---

# `src/licensing/activation.py`

## High-Level Purpose

The owner's design (2026-11-26): a licence is a **key the store issues with the
order**. It is activated once, checked again at update, and offline in between.

| Moment | Call | Failure |
|---|---|---|
| Activation | `POST {relay}/activate` with the key and an instance name | one sentence naming the reason; the cache is untouched; the free tier keeps working |
| Update | `POST {relay}/validate` with the stored key and instance id | revoked/expired/unknown refuses the upgrade; no answer proceeds on the cache |
| Everything else | none | - |

The relay (`services/licence-relay`) holds the merchant API key. The product never
holds it and never addresses the store directly, so a provider change is a relay
deploy, not a release.

## The cache

`~/.ai-test-gen/licence.json`, or `AITEST_LICENCE_FILE`:

`key`, `instance_id`, `instance_name`, `status`, `created_at`, `expires_at`,
`activation_limit`, `last_checked`, `tier`.

`created_at` is the store's key-creation time. The store creates the key seconds
after the order, on the same UTC date, so this is the purchase date the 12-month
window runs from (verified 2026-11-26: order 00:04:01Z, key 00:04:47Z).

## Validation: only `active` passes

A `200` answer naming any other state is a refusal, and so is an answer this build
cannot read (t-1505 - the earlier code read `inactive` as a pass and defaulted a
missing status to `active`):

| Answer | Code | Meaning |
|---|---|---|
| `200 {"status": "active"}` | `ok` | the gate opens |
| `200 {"status": "inactive"}` | `inactive` | the store disabled the key |
| `200 {"status": "disabled"}` | `disabled` | same, named by the store |
| `200 {"status": "expired"}` | `expired` | past the store's expiry |
| `200` with no status, or an unknown word | `unknown_status` | "an answer this version does not understand - check for an update" |
| `404` / `410` | `not_found` / `revoked_or_expired` | the key is gone or dead |
| `403` with no relay code | `blocked_at_edge` | "blocked before it reached us (edge error 1010) - a fault at our end"; email support |
| no answer | `network` | the caller proceeds on the cache and says so |

An edge block is treated like an unreachable service at update time: the upgrade
proceeds, because our edge must not block a paid upgrade.

## The user agent

Every call sends `TanCat/<version> (+https://tancat.dev)`, built from
`src/version_info.py`. Cloudflare's edge rejects Python's default `Python-urllib/x`
agent with `403 error code: 1010` before the request reaches the Worker, so a default
agent would block every activation while looking like a network failure (t-1506).

A refusal never rewrites the cache, so the licence the buyer held is still there.

## Activation errors

The **relay** turns the store's answer into one of our codes; the product maps the
code to a sentence. The store does **not** use the status codes its reference page
implies - observed on the live test API on **2026-11-26**:

| What happened | The store actually answered | Our code |
|---|---|---|
| the single activation was already used | `400 {"error":"Bad Request","message":"Activation limit reached"}` | `activation_limit` |
| the instance was already released | `400 {"message":"License key instnace is already deactivated"}` | `already_released` |
| the key does not exist | `404` | `not_recognised` (activate) / `not_found` (validate) |
| the key was revoked or expired | `410` | `revoked_or_expired` |
| anything else | `5xx`, or a message naming no cause | `upstream_error` |

Because the status alone is misleading, `codeFor()` in the Worker reads **both** the
status and the message. The store's text never reaches a buyer: the body is
`{"error": code}` only. The recorded bodies, misspelling included, live in
`tests/fixtures/relay/store-error-bodies.json` and are replayed through the real
Worker on every run.

The sentences the product prints:

| Code | Sentence (short form) |
|---|---|
| `activation_limit` | used on its maximum number of machines |
| `not_recognised` | not recognised; nothing on this machine changed |
| `already_released` | this machine was already released |
| `revoked_or_expired` | no longer active: revoked or expired |
| `blocked_at_edge` | blocked before it reached us - a fault at our end |
| `unreachable` | runs on the free tier until you connect and retry |

No refusal asks a buyer to pay again; a test asserts every message for that.

## Functions

- `activate(key, instance_name="", *, path=None) -> ActivationResult`
- `validate(*, path=None) -> ValidationResult`
- `deactivate(*, path=None) -> tuple[bool, str]`
- `load(path=None)`, `save(activation, path=None)`, `clear(path=None)`
- `default_path()`, `relay_url()`, `default_instance_name()`

## Related

- `services/licence-relay/` - the Worker, held to this module by
  `tests/test_licence_relay_contract.py` (a real exchange, not a string match).
- `src/licensing/entitlement.py` - the gate built on this cache.
- `docs/security/license-key-ops.md` - the merchant key, rotation, the accepted trade.
