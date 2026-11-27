---
purpose: >
  The price and the currency in one place: $499 a deployment, a $125 a year renewal
  that is page copy and not a contract term, and the update policy. Imported by the
  price test only - it is a guard, not a renderer.
lines: ~60
created: "2026-11-26"
updated: "2026-11-26"
---

# `src/licensing/pricing.py`

## High-Level Purpose

The owner settled the price on 2026-11-06, the currency on 2026-11-12, and moved it
to US dollars on 2026-11-24.

| Constant | Value | Rule |
|---|---|---|
| `CURRENCY` | `"USD"` | the store charges in US dollars |
| `CURRENCY_SYMBOL` | `"$"` | what every surface prints |
| `PRICE_PER_DEPLOYMENT` | `499` | one price; no list price, no launch offer |
| `RENEWAL_PER_YEAR` | `125` | page copy only - never in the terms |
| `UPDATES_INCLUDED_MONTHS` | `12` | updates inside the window are included |
| `DEPLOYMENT_DEFINITION` | "one installation serving one organisation" | the card and the terms say the same words |

**The currency is a decision, not a default:** the number and the symbol are one
choice. Changing one without the other writes a price the buyer cannot be charged.

The module renders nothing. `tests/test_landing_price.py` reads it and fails if any
landing page prints a price that is not `$0`, `$499` or `$125`, or prints a pound
sign at all.

## Related

- `tests/test_landing_price.py` - the guard.
- `docs/launch/launch-checklist.html` - the price parity step before a sale.
