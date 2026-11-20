---
description: TanCat licensing and tiers - the free limits, how to install a Pro licence file, and what the paid tiers add to a deployment.
---

# Licensing and tiers

TanCat runs unlicensed on the **Free** tier. A licence file raises the limits and
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
| Licence | Business Source License 1.1 (source-available) | Commercial per-deployment licence: a signed licence file issued by us |
| Price | Free | £399 per deployment |
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

TanCat makes **exactly one automatic call, and no others**: a version check at most once a day if you
leave it on. It carries nothing about you, and settings turns it off. **Licensing never touches the
network** - your licence file is verified offline against a public key built into the product. No
automatic upgrade: you choose when to install one.

## Install a licence file

A licence is a **signed file** we issue to you. Save it and the product reads it; there
is nothing to switch on and no call is made.

1. **`AITEST_LICENCE_FILE`** - a path to your licence file. Best for CI, where you inject
   it from a secret store:

   ```bash
   AITEST_LICENCE_FILE=/etc/tancat/licence.signed.json bash launch_ui.sh
   ```

2. **The default path** `tancat licence status` prints - the settings directory for the
   deployment, `licence.signed.json` inside it.

The file is JSON: its format, a payload (licence id, product, buyer reference, purchase
date, window end and tier) and a signature. The product verifies the signature against
a public key built into it, offline, so nothing about your licence leaves the machine.

If you hold an older token, it still verifies offline and is used when no signed file
is present; we do not document the token routes because the licence is the signed file.

## How the licence is checked

At startup TanCat reads the licence file, verifies its signature against the
public key built into the product, and takes the tier and the update window from
the payload. If there is no file, or it cannot be verified, the app runs on the
Free tier - it does not block you.

Because the tier travels inside the signed payload, an unknown tier is refused
rather than guessed at. That is deliberate: a licence that cannot be understood
never silently grants more than it should.

## Next

- [Evidence and reports](../guides/evidence.md)
- [Back to the docs home](../index.md)
