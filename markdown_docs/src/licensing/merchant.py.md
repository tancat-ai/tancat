---
purpose: >
  The merchant of record, named in one place and deliberately unnamed until the
  account is approved. Every sentence the product or a page prints about the seller
  reads this constant.
lines: ~35
created: "2026-11-26"
updated: "2026-11-26"
---

# `src/licensing/merchant.py`

## High-Level Purpose

The store that takes the money is a provider, and the licence is the store's key - so
the provider is in the purchase path by design, behind our relay. Its **name** still
does not belong on a buyer page until the account is approved.

| Constant | Today | When the store is named |
|---|---|---|
| `MERCHANT_OF_RECORD` | `"our merchant of record"` | the store's name |
| `MERCHANT_OF_RECORD_TERMS_URL` | `""` | the store's terms link |

Nothing else in `src/` may spell the merchant's name as a literal; tests enforce it
(`tests/test_licensing_outbound_wording.py`, `tests/test_terms_and_dpa.py`), so a
rename cannot leave a stale second copy behind.

## Related

- `landing/terms.html`, `landing/privacy.html`, `landing/dpa.html` - the copy that
 
