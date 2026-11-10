"""The price and the update policy, in one place (d-0151).

The owner settled these on 2026-11-06:

- **$399 per deployment, one price.** No list price and no introductory wording -
  an introductory price with no honest end date is a claim we cannot back.
- **Renewal: $125 a year**, shown on the pricing page only. It is not a contract
  term and must not appear in the terms.
- **Perpetual for the version received**, including all updates released within
  12 months of purchase; updates after that are not included and may be bought
  separately; nothing renews automatically.

The pages are static HTML, so this module is the single source a test reads to
hold the card and the terms to the same number - the same guard the free export
cap needed after it drifted.
"""

from __future__ import annotations

#: One price, per deployment. No `was`, no `launch offer`.
PRICE_PER_DEPLOYMENT_USD = 399

#: The current renewal price, in dollars per year. Pricing page only.
RENEWAL_PER_YEAR_USD = 125

#: Updates released inside this window are included with the licence.
UPDATES_INCLUDED_MONTHS = 12

#: What the price is for. The card and the terms must say the same thing.
DEPLOYMENT_DEFINITION = "one installation serving one organisation"
