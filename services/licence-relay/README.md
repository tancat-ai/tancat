# TanCat licence relay

The only piece of ours between a buyer and the store. The product must never ship a
merchant API key, so activation and the update-time check go through this Worker,
which holds the key as a secret and forwards three operations.

## Endpoints

| Method | Path | Body | Success |
|---|---|---|---|
| POST | `/activate` | `{ "key": "...", "instance_name": "..." }` | `200 { "activation": { key, status, created_at, expires_at, activation_limit, instance: { id, name, status } } }` |
| POST | `/validate` | `{ "key": "...", "instance_id": "..." }` | `200 { "status": "active", "expires_at": "" }` |
| POST | `/deactivate` | `{ "key": "...", "instance_id": "..." }` | `200 { "released": true }` |

Failures answer `{"error": "<code>"}` with the upstream status, and the product maps
the code to a sentence:

| Code | Meaning | Upstream status |
|---|---|---|
| `activation_limit` | the key is on its maximum number of machines | 403 |
| `not_recognised` | the key is not one of ours | 404 |
| `already_released` | this machine was already released | 409 |
| `revoked_or_expired` | the key is disabled or expired | 410 |
| `not_found` | key/instance pair unknown (validate) | 404 |
| `upstream_error` | anything else - the product treats it as unreachable | 5xx / none |

No provider name appears in a response body: these strings can reach a buyer's screen.

## Deploy

```bash
cd services/licence-relay
npx wrangler login                       # once per machine
npx wrangler secret put API_KEY          # paste the merchant API key; never commit it
npx wrangler deploy                      # prints the Worker URL
```

Set `API_BASE` in `wrangler.toml` to the store's test or live API base for the
environment you are deploying (`[env.test]` / `[env.production]` sections if you want
both at once). Set `ALLOWED_ORIGIN` to the docs site; nothing else gets CORS headers.

Then point the product at it:

```bash
export AITEST_LICENCE_RELAY_URL="https://tancat-licence-relay.<account>.workers.dev"
tancat licence activate <KEY>
tancat licence status
```

The default in `src/licensing/activation.py` is `https://licence.tancat.dev`; deploy
a custom route there when the domain is ready, or set the variable on each machine.

## Smoke test

```bash
curl -s -X POST "$RELAY/activate" -H 'content-type: application/json' \
  -d '{"key":"<test key>","instance_name":"smoke test"}'
curl -s -X POST "$RELAY/validate" -H 'content-type: application/json' \
  -d '{"key":"<test key>","instance_id":"<id from activate>"}'
curl -s -X POST "$RELAY/deactivate" -H 'content-type: application/json' \
  -d '{"key":"<test key>","instance_id":"<id from activate>"}'
```

## What it does NOT protect against

Say this plainly rather than implying a guarantee:

- **It is not DRM.** The product is source-available; a fork can delete the check,
  or write its own cache file. The relay makes the honest path honest, it does not
  stop a determined customer.
- **It does not detect a shared key between updates.** With no periodic check, a key
  activated on one machine keeps working until that machine installs an update. A key
  that is revoked the day after activation is noticed at the next update, not before.
  That is the accepted trade, and it is stated in the buyer documents.
- **It does not stop key sharing beyond the activation limit.** The limit is the
  store's; a buyer with the limit raised can activate on more machines.
- **It does not verify the goods.** Payment, refunds, tax and the order record are
  the store's; this Worker only asks about a key.
- **It is a single point of failure for activation.** If the Worker or the store is
  down, a *new* activation fails (the product says so and stays on the free tier). An
  already-activated machine is unaffected, because it reads its cache.
- **The API key is the whole security boundary.** Anyone who can read the Worker's
  secret can activate and deactivate keys. Rotate it in the store's dashboard and run
  `npx wrangler secret put API_KEY` again.
