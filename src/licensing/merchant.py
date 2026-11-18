"""The merchant of record, named in one place (j-0309).

The store that takes the money is a *provider*, not a dependency of the licence:
the product's entitlement comes from a signed licence file we issue ourselves.
When the store changes - and it will, Lemon Squeezy has announced its shutdown -
one constant changes here, and every sentence the product prints follows.

Nothing else in ``src/`` may spell the merchant's name as a literal; a test
enforces that so a rename cannot leave a stale second copy behind.
"""

from __future__ import annotations

#: The merchant of record a buyer's payment goes through, as it appears in copy.
MERCHANT_OF_RECORD = "Lemon Squeezy"

#: The merchant's own terms, for the sentence that says who handles the payment.
MERCHANT_OF_RECORD_TERMS_URL = "https://www.lemonsqueezy.com/terms"

__all__ = ["MERCHANT_OF_RECORD", "MERCHANT_OF_RECORD_TERMS_URL"]
