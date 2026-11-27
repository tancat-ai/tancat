---
description: TanCat licensing and tiers - the free limits, how to activate a Pro licence key, and what the paid tiers add to a deployment.
---

# Licensing and tiers

TanCat runs unlicensed on the **Free** tier. A licence key raises the limits and
unlocks the paid features. A licence is an entitlement marker, not DRM - it
tells the app what the deployment is allowed to do.

## Tiers

| | Free | Pro |
|---|---|---|
| Core test generation | Yes | Yes |
| Evidence export (CSV / NDJSON / JUnit / HTML) | Yes | Yes |
| Self-healing | Yes | Yes |
| RAG / flow-memory learning | Yes | Yes |
| Jira report export | - | Yes |
| Page Object Model mode | - | Yes |
| Multi-site suites | - | Yes |
| CI / headless runs | - | Yes |
| Licence | Business Source License 1.1 (source-available) | Commercial per-deployment licence: a licence key issued with your order |
| Price | Free | $499 per deployment |
| Support | - | Email support and setup help - direct from the developer |
| Updates | - | All updates released within 12 months of purchase; later updates optional and paid |
| Runs | 25 per 30 days | Unlimited |
| Evidence exports | 10 per 30 days | Unlimited |

**Support.** Support is provided by email at hello@tancat.dev, by the developer who builds TanCat. You get help with installation, licensing, and defects in TanCat. We aim to reply within two working days, Monday to Friday, UK business hours. Support does not include custom development, third-party systems, or on-site work, and we do not offer telephone or out-of-hours support. A contractual service level is available on request.

The two counters are shown live in the UI sidebar.

![The License & Usage panel in the sidebar: the current tier, the run counter,
the evidence-export counter and storage used.](../assets/streamlit-license-usage.png)

*The License & Usage panel. The counters reset every 30 days.*

## Updates

A licence is **perpetual for the version you receive**. It does not expire.

It includes all updates released within 12 months of purchase. Updates released
after that are not included and can be bought separately if you want them.

**Nothing renews automatically.** You will not be charged again unless you choose
to buy. Security fixes and bug fixes for the version you hold are provided at no
charge.

The software is licensed under the **Business Source License 1.1**: free to read,
modify and use, including production use for any internal purpose, and it
converts to Apache-2.0 four years after each version's release.

Updates are released as installable Python packages on the
[releases page](https://github.com/tancat-ai/tancat/releases), and you upgrade the
way you upgrade any Python tool. You choose when to install one.

TanCat calls our licence service at two moments in a licence's life and at no
others: when you activate your key, and when you install a new version. Between
those moments it works offline and makes no licensing call. It also makes a
version check at most once a day if you leave it on, which carries nothing about
you and that settings turns off. No automatic upgrade: you choose when to install
one.

## Activate your licence key

Your key is in your order email.

1. Run:

   ```bash
   tancat licence activate XXXX-XXXX-XXXX-XXXX-XXXX
   ```

   The product sends the key and this machine's name to our licence service, which
   records the activation against your purchase. On success the key and the
   activation are stored on this machine.

2. In the UI, the sidebar's **License & Usage** panel has the same field and the
   same result.

3. Confirm it:

   ```bash
   tancat licence status
   ```

   It prints the instance, the activation date, the tier and when the update window
   ends.

One key covers one deployment, and the store sets how many machines may use it. To
move the licence, release it on the old machine first
(`tancat licence release`), then activate on the new one.

### If activation fails

Each answer is one sentence, and none of them asks you to pay again:

| What happened | What you see |
|---|---|
| The key is on its maximum number of machines | release it on the other machine, or email support |
| The key is not recognised | check it against your order email; nothing on this machine changed |
| The machine was already released from this key | enter the key again to activate it here |
| The licence service cannot be reached | the product runs on the free tier until you connect and retry |

A refused activation never removes a licence this machine already holds. For CI,
store the licence file (the path `tancat licence status` prints) and point at it
with `AITEST_LICENCE_FILE=/etc/tancat/licence.json`.

## When the licence is checked

Two moments only:

- **Activation.** The key is checked with the store and stored here.
- **Update.** When you install a new version, the key is checked again. If the store
  reports it as revoked or expired, the upgrade is refused and the version you are
  running keeps working. If the check cannot be made, the upgrade goes ahead on the
  licence stored here.

Everything else - startup, runs, premium features - reads the stored licence. A key
the store disables is therefore noticed at your next update, not before. That is the
accepted trade for a product that works offline.

## Next

- [Evidence and reports](../guides/evidence.md)
- [Back to the docs home](../index.md)
