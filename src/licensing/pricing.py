"""The price and the update policy, in one place (d-0151, d-0167).

The owner settled these on 2026-11-06, and set the currency on 2026-11-12:

- **£399 per deployment, one price.** No list price and no introductory wording -
  an introductory price with no honest end date is a claim we cannot back.
- **Renewal: £125 a year**, shown on the pricing page only. It is not a contract
  term and must not appear in the terms.
- **Perpetual for the version received**, including all updates released within
  12 months of purchase; updates after that are not included and may be bought
  separately; nothing renews automatically.
- **The store charges in pounds.** The product is priced and sold in GBP, so every
  surface prints ``£`` - never ``$``. The names below carry no currency on purpose
  (``..._USD`` could be renamed to ``..._GBP`` later and leave the symbol behind);
  the currency lives in ``CURRENCY`` and ``CURRENCY_SYMBOL``, and the price test
  fails if a page prints a dollar sign next to a price.

The pages are static HTML. **This module does not render them, and nothing in
``src/`` imports it** - the only importer is ``tests/test_landing_price.py``.
What it gives you is a guard, not a renderer: change a number here and the price
test fails until every page (and the order PDF) is updated to match. That is a
weaker claim than "one source feeds both pages", and it is the true one - the same
guard the free export cap needed after it drifted.
"""

from __future__ import annotations

#: The currency the store charges in, as an ISO 4217 code.
CURRENCY = "GBP"

#: The symbol a page must print in front of a price. Written as an escape so this
#: file stays ASCII; every surface must render it as the pound sign.
CURRENCY_SYMBOL = "\N{POUND SIGN}"

#: One price, per deployment, in ``CURRENCY``. No `was`, no `launch offer`.
PRICE_PER_DEPLOYMENT = 399

#: The current renewal price, per year, in ``CURRENCY``. Pricing page only.
RENEWAL_PER_YEAR = 125

#: Updates released inside this window are included with the licence.
UPDATES_INCLUDED_MONTHS = 12

#: What the price is for. The card and the terms must say the same thing.
DEPLOYMENT_DEFINITION = "one installation serving one organisation"
