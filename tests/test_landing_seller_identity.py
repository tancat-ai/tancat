"""j-0289: the seller identity is one fact, so the two pages must not drift.

``landing/terms.html`` and ``landing/privacy.html`` both name the seller. They
are separate files, so a move or a switch of address is two edits that can
disagree - and the git history keeps whichever was published. This test reads
the name and the address out of both pages and requires them to be identical,
and requires neither page to carry a placeholder marker (the rule is
``check_landing_placeholders`` - the same one the deploy runs).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "maintenance"))

from check_landing_placeholders import find_placeholders  # type: ignore[import-not-found]  # noqa: E402

LANDING = REPO_ROOT / "landing"
PAGES = {
    "terms": LANDING / "terms.html",
    "privacy": LANDING / "privacy.html",
}

#: "TanCat is the trading name of <seller>, a sole-trader software business ..."
SELLER = re.compile(
    r"TanCat is the trading name of (?P<name>[^,<]+),\s*a sole-trader software business based in the United Kingdom",
    re.IGNORECASE,
)
#: "Address: <address>." - up to the full stop that ends the sentence.
ADDRESS = re.compile(r"Address:\s*(?P<address>[^.]+)\.", re.IGNORECASE)


def _identity(page: Path) -> tuple[str, str]:
    """The (seller, address) pair a page publishes."""
    text = page.read_text(encoding="utf-8")
    seller = SELLER.search(text)
    address = ADDRESS.search(text)
    assert seller is not None, f"{page.name} names no seller - the identity block was changed or lost"
    assert address is not None, f"{page.name} gives no address - the identity block was changed or lost"
    return seller.group("name").strip(), address.group("address").strip()


def test_both_pages_publish_the_same_seller_and_address() -> None:
    terms = _identity(PAGES["terms"])
    privacy = _identity(PAGES["privacy"])

    assert terms == privacy, (
        "the seller identity differs between the two pages, and only one of them is the truth:\n"
        f"  terms.html:   {terms}\n"
        f"  privacy.html: {privacy}"
    )


def test_the_identity_is_the_owners_supplied_wording() -> None:
    """The owner's words (2026-11-05): his name, and his home address as he wrote it."""
    seller, address = _identity(PAGES["terms"])
    assert seller == "Louis Cattano"
    assert address == "Flat 2, Bournehall, 2 Bourne Close, Bournemouth, BH2 6BW"


def test_neither_page_carries_a_placeholder() -> None:
    findings = [
        finding for finding in find_placeholders(LANDING) if "terms.html" in finding or "privacy.html" in finding
    ]
    assert findings == [], "a seller page still carries a placeholder:\n  " + "\n  ".join(findings)
