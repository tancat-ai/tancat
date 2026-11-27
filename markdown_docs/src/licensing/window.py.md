---
purpose: >
  The update window: how long a purchase includes updates for, the arithmetic that
  turns a key's creation date into the last build it covers, and the copy shown when
  a build is past it.
lines: ~70
created: "2026-11-26"
updated: "2026-11-26"
---

# `src/licensing/window.py`

## High-Level Purpose

Nothing here talks to a store or to the network. The window is a policy constant and
two functions.

| Name | Meaning |
|---|---|
| `RELEASE_DATE` | the date this build was released - refreshed with each release |
| `WINDOW_MONTHS` | 12 |
| `RENEWAL_COPY` | where a buyer goes when the window has closed |
| `add_months(date, months)` | month arithmetic, clamped to the end of the target month |
| `window_end(purchase_date)` | the last build date the licence covers |
| `WindowDecision` | `allowed`, `message`, `window_end` |

The start date is the licence key's `created_at` (see `activation.py`), recorded when
the buyer activated it - the store creates the key seconds after the order, on the
same UTC date.

A build released after `window_end` refuses to start, names the window end and the
version that keeps working, and changes nothing on disk.

## Related

- `src/licensing/entitlement.py` - the two decisions that use this.
