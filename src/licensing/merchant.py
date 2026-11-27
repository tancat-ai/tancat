"""The merchant of record, named in one place (j-0309).

The store that takes the money is a *provider*. But the licence is the store's key,
so the provider is in the purchase path by design - behind our relay, which is the
only thing the product talks to. When the store is approved and named, one constant
changes here and every sentence the product prints follows. Until then the constant
names the role, not a company.

Nothing else in ``src/`` may spell the merchant's name as a literal; a test
enforces that so a rename cannot leave a stale second copy behind.
"""

from __future__ import annotations

#: The merchant of record a buyer's payment goes through, as it appears in copy.
#:
#: Deliberately unnamed: the account is in review, and naming a provider on a buyer
#: page would promise a route that is not live yet. When it is approved, put the name
#: here and the seller sentence follows. Until then the copy says "our merchant of
#: record", which is true and names nobody.
MERCHANT_OF_RECORD = "our merchant of record"

#: The merchant's own terms. Empty until a provider is named: the copy falls back
#: to the plain sentence rather than linking nowhere.
MERCHANT_OF_RECORD_TERMS_URL = ""

__all__ = ["MERCHANT_OF_RECORD", "MERCHANT_OF_RECORD_TERMS_URL"]
