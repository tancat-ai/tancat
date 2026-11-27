"""The update window: what it is, and whether a build is inside it (j-0309).

Nothing here talks to a store or to the network. The window comes from the licence
key's **creation date**, recorded at activation (``activation.py``): the store creates
the key seconds after the order, on the same UTC date, so the key's date is the
purchase date. This module holds the policy constants, and the arithmetic that turns
that date into the last build the licence covers.

A build released after the window refuses to start, and names the window end and
the version that keeps working. Nothing on disk is modified: the buyer's existing
install is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

__all__ = [
    "RELEASE_DATE",
    "RENEWAL_COPY",
    "WINDOW_MONTHS",
    "WindowDecision",
    "add_months",
    "window_end",
]

#: The date this build was released. Refreshed with each release; it is the
#: package's own date, and the clock the window is compared against.
RELEASE_DATE: date = date(2026, 11, 13)

#: How long a purchase includes updates for.
WINDOW_MONTHS: int = 12

#: Where a buyer goes when the window has closed and they want a newer build.
RENEWAL_COPY = "Renew at https://tancat.dev/#pricing when a renewal is available, or email hello@tancat.dev."


@dataclass(frozen=True)
class WindowDecision:
    """Whether this build may run, and what to say when it may not."""

    allowed: bool
    message: str
    window_end: date | None = None


def add_months(start: date, months: int) -> date:
    """*start* plus *months*, clamped to the end of the target month."""
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = start.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def window_end(purchase_date: date) -> date:
    """The last day a build released inside the update window may be."""
    return add_months(purchase_date, WINDOW_MONTHS)
