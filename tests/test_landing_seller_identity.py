"""The seller identity is one fact, so the two pages must not drift.

``landing/terms.html`` and ``landing/privacy.html`` both name the seller. They are
separate files, so a change of company, number or address is two edits that can
disagree - and the git history keeps whichever was published. This test reads the
company, its number and the registered office out of both pages and requires them
to be identical, and requires neither page to carry a placeholder marker (the rule
is ``check_landing_placeholders`` - the same one the deploy runs).

The seller became a company on 2026-11-11 (j-0299): **Cat Tan Operations Ltd**,
company number **17576111**, registered office Flat 2, Bournehall, 2 Bourne Close,
Bournemouth, BH2 6BW. TanCat is a product of that company, not a sole trader, so
the old "trading name of <person>, a sole-trader business" shape must be gone from
both pages.
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

#: "TanCat is a product of <company>, a company registered in England and Wales"
SELLER = re.compile(
    r"TanCat is a product of (?P<name>[^,<]+),\s*a company registered in England and Wales",
    re.IGNORECASE,
)
#: "(company number 17576111)"
COMPANY_NUMBER = re.compile(r"company number\s*(?P<number>[0-9]+)", re.IGNORECASE)
#: "Registered office: <address>." - up to the full stop that ends the sentence.
ADDRESS = re.compile(r"Registered office:\s*(?P<address>[^.]+)\.", re.IGNORECASE)

EXPECTED_COMPANY = "Cat Tan Operations Ltd"
EXPECTED_NUMBER = "17576111"
EXPECTED_ADDRESS = "Flat 2, Bournehall, 2 Bourne Close, Bournemouth, BH2 6BW"


def _identity(page: Path) -> tuple[str, str, str]:
    """The (company, company number, registered office) a page publishes."""
    text = page.read_text(encoding="utf-8")
    seller = SELLER.search(text)
    number = COMPANY_NUMBER.search(text)
    address = ADDRESS.search(text)
    assert seller is not None, f"{page.name} names no company - the identity block was changed or lost"
    assert number is not None, f"{page.name} gives no company number - the identity block was changed or lost"
    assert address is not None, f"{page.name} gives no registered office - the identity block was changed or lost"
    return seller.group("name").strip(), number.group("number").strip(), address.group("address").strip()


def test_both_pages_publish_the_same_company_number_and_office() -> None:
    terms = _identity(PAGES["terms"])
    privacy = _identity(PAGES["privacy"])

    assert terms == privacy, (
        "the seller identity differs between the two pages, and only one of them is the truth:\n"
        f"  terms.html:   {terms}\n"
        f"  privacy.html: {privacy}"
    )


def test_the_identity_is_the_registered_company() -> None:
    """The owner's company (2026-11-11, j-0299): Cat Tan Operations Ltd, 17576111."""
    company, number, address = _identity(PAGES["terms"])
    assert company == EXPECTED_COMPANY
    assert number == EXPECTED_NUMBER
    assert address == EXPECTED_ADDRESS


def test_neither_page_still_calls_it_a_sole_trader() -> None:
    """A re-introduced sole-trader sentence would be a false legal statement."""
    for name, page in PAGES.items():
        text = page.read_text(encoding="utf-8")
        for phrase in ("sole-trader", "sole trader", "trading name of"):
            assert phrase not in text, f"{name}.html still says {phrase!r}"


def test_the_privacy_page_names_the_company_as_controller() -> None:
    text = PAGES["privacy"].read_text(encoding="utf-8")
    assert "The company is the controller" in text, (
        "the privacy notice must say the company decides why and how personal data is used"
    )


def test_neither_page_carries_a_placeholder() -> None:
    findings = [
        finding for finding in find_placeholders(LANDING) if "terms.html" in finding or "privacy.html" in finding
    ]
    assert findings == [], "a seller page still carries a placeholder:\n  " + "\n  ".join(findings)
