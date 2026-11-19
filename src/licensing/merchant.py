"""The merchant of record, named in one place (j-0309).

The store that takes the money is a *provider*, not a dependency of the licence:
the product's entitlement comes from a signed licence file we issue ourselves.
When the store is named - Polar is the intended provider, pending approval - one
constant changes here, and every sentence the product prints follows. Until then the
constant names the role, not a company, because we have not sold a licence yet.

Nothing else in ``src/`` may spell the merchant's name as a literal; a test
enforces that so a rename cannot leave a stale second copy behind.
"""

from __future__ import annotations

#: The merchant of record a buyer's payment goes through, as it appears in copy.
#:
#: Deliberately unnamed: no provider is signed yet, and no licence has ever been
#: sold. The store is expected to be Polar (pending approval) - when the account is
#: live, put its name here and the seller sentence follows. Until then the copy says
#: "our merchant of record", which is true and names nobody.
MERCHANT_OF_RECORD = "our merchant of record"

#: The merchant's own terms. Empty until a provider is named: the copy falls back
#: to the plain sentence rather than linking nowhere.
MERCHANT_OF_RECORD_TERMS_URL = ""

__all__ = ["MERCHANT_OF_RECORD", "MERCHANT_OF_RECORD_TERMS_URL"]
