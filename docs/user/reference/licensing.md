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
| Support and onboarding bundle | - | Yes |
| Runs | 25 per 30 days | Unlimited |
| Evidence exports | 10 per 30 days | Unlimited |

The two counters are shown live in the UI sidebar.

![The License & Usage panel in the sidebar: the current tier, the run counter,
the evidence-export counter and storage used.](../assets/streamlit-license-usage.png)

*The License & Usage panel. The counters reset every 30 days.*

## Install a licence key

There are three routes, checked in this order:

1. **`AITEST_LICENSE_KEY`** - the token inline. Best for CI, where you inject it
   from a secret store:

   ```bash
   AITEST_LICENSE_KEY=<token> bash launch_ui.sh
   ```

2. **`AITEST_LICENSE_FILE`** - a path to a file containing the token:

   ```bash
   AITEST_LICENSE_FILE=/etc/tancat/license.key bash launch_ui.sh
   ```

3. **`~/.ai-test-gen/license.key`** - the default key file for the deployment.
   Save the token there once and the app finds it on every start.

When a valid key is loaded, the UI reports the tier and the deployment it is
signed for.

## How the licence is checked

At startup TanCat reads the key, verifies its signature against the vendored
trust root, and reads the tier from the payload. If no key is present, or the
key cannot be verified, the app runs on the Free tier - it does not block you.

Because the tier travels inside the signed payload, an unknown tier key is
treated as Free. That is deliberate: a licence that cannot be understood never
silently grants more than it should.

## Next

- [Evidence and reports](../guides/evidence.md)
- [Back to the docs home](../index.md)
