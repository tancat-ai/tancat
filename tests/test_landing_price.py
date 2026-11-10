"""d-0151: the price and the update policy, held to one source.

The same drift the free export cap had: a number typed in two places. The owner's
settled position (2026-11-06) is in ``src/licensing/pricing.py``; these tests hold
the pricing card and the terms to it, and forbid the claims he rejected.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.licensing.pricing import (
    DEPLOYMENT_DEFINITION,
    PRICE_PER_DEPLOYMENT_USD,
    RENEWAL_PER_YEAR_USD,
    UPDATES_INCLUDED_MONTHS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX = REPO_ROOT / "landing" / "index.html"
TERMS = REPO_ROOT / "landing" / "terms.html"

#: Claims the owner refused: an introductory price with no honest end date, a
#: list price he never charged, and a launch offer.
FORBIDDEN_CLAIMS = (
    "introductory",
    "was $",
    "limited time",
    "launch offer",
    "special price",
    # j-0297: the install page said "billed monthly or yearly", which contradicts
    # a one-off price and "nothing renews automatically". The old test missed the
    # words that would have caught it.
    "monthly",
    "yearly",
    "billed",
)

#: The PDF that ships with an order, rendered from the source HTML.
INSTALL_PDF = REPO_ROOT / "landing" / "tancat-pro-install-and-licence.pdf"


def _pdf_text(path: Path = INSTALL_PDF) -> str:
    """The PDF's text as one line, so a phrase check reads what a buyer reads."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        text = "\n".join(page.get_textpage().get_text_range() for page in pdf)
    finally:
        pdf.close()
    return " ".join(text.split())


def _flat(path: Path) -> str:
    """The page as one line of collapsed whitespace, for phrase matching."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_card_carries_the_price_from_the_one_source() -> None:
    page = _flat(INDEX)
    assert f"${PRICE_PER_DEPLOYMENT_USD}" in page, "the Pro card does not show the settled price"
    assert "Pricing announced at launch" not in page, "the placeholder price is still on the page"


def test_the_terms_carry_the_price_from_the_one_source() -> None:
    page = _flat(TERMS)
    assert f"${PRICE_PER_DEPLOYMENT_USD} per deployment" in page, "the terms do not state the settled price"
    # And no second number that could pass for a price.
    prices = {int(match) for match in re.findall(r"\$(\d[\d,]*)", page)}
    assert prices == {PRICE_PER_DEPLOYMENT_USD}, f"the terms quote more than one price: {sorted(prices)}"


def test_the_card_and_the_terms_define_a_deployment_the_same_way() -> None:
    for path in (INDEX, TERMS):
        assert DEPLOYMENT_DEFINITION in _flat(path), f"{path.name} does not carry the deployment definition"


def test_the_card_states_the_update_window_from_the_one_source() -> None:
    page = _flat(INDEX)
    assert f"{UPDATES_INCLUDED_MONTHS} months of purchase" in page


def test_the_renewal_price_is_on_the_pricing_page_and_not_in_the_terms() -> None:
    """Owner's decision: the renewal price is a page figure, not a contract term."""
    assert f"${RENEWAL_PER_YEAR_USD} a year" in _flat(INDEX), "the pricing page does not state the renewal"
    terms = _flat(TERMS)
    assert f"${RENEWAL_PER_YEAR_USD}" not in terms, "the renewal price leaked into the terms"
    assert "a year" not in terms, "the terms talk about a yearly figure"


def test_no_claim_the_owner_rejected_appears_on_the_site() -> None:
    for path in sorted((REPO_ROOT / "landing").glob("*.html")):
        page = _flat(path).lower()
        for claim in FORBIDDEN_CLAIMS:
            assert claim not in page, f"{path.name} carries a claim the owner rejected: {claim!r}"


def test_the_terms_state_the_four_settled_sentences_and_the_security_line() -> None:
    page = _flat(TERMS)
    settled = (
        "This licence is perpetual for the version you receive. It does not expire.",
        f"It includes all updates released within {UPDATES_INCLUDED_MONTHS} months of purchase.",
        "Updates released after that are not included and can be bought separately if you want them.",
        "Nothing renews automatically. You will not be charged again unless you choose to buy.",
        "Security fixes and bug fixes for the version you hold are provided at no charge.",
    )
    for sentence in settled:
        assert sentence in page, f"the terms do not carry the settled sentence: {sentence!r}"


def test_the_terms_promise_nothing_about_future_years() -> None:
    page = _flat(TERMS).lower()
    for phrase in ("grandfathered", "price held", "prices will", "future price", "will not increase"):
        assert phrase not in page, f"the terms promise something about future pricing: {phrase!r}"


def test_the_order_pdf_carries_the_settled_sentences_not_the_old_ones() -> None:
    """j-0297: the PDF ships with every order and had fallen behind the site."""
    text = _pdf_text()

    for sentence in (
        "perpetual for the version you receive",
        f"all updates released within {UPDATES_INCLUDED_MONTHS} months of purchase",
        "Updates released after that are not included",
        "Nothing renews automatically",
        "Security fixes and bug fixes for the version you hold are provided at no charge",
    ):
        assert sentence in text, f"the shipped PDF does not carry: {sentence!r}"

    for stale in ("perpetual for the version you buy", "Updates after the first 12 months are paid"):
        assert stale not in text, f"the shipped PDF still carries the old wording: {stale!r}"

    lowered = text.lower()
    for claim in FORBIDDEN_CLAIMS:
        assert claim not in lowered, f"the shipped PDF carries a claim the owner rejected: {claim!r}"


def test_the_order_pdf_price_matches_the_one_source() -> None:
    text = _pdf_text()
    if f"${PRICE_PER_DEPLOYMENT_USD}" in text:
        return  # stated, and it is the settled number
    # Not every order PDF states the price; then it must not state another one.
    assert not re.search(r"\$\d", text), f"the PDF states a price that is not the settled one: {text[:200]}"
