"""d-0151, d-0167: the price, the currency and the update policy, held to one source.

The same drift the free export cap had: a number typed in two places. The owner's
settled position (2026-11-06, currency set 2026-11-12) is in
``src/licensing/pricing.py``; these tests hold the pricing card, the terms, the
install page and the docs to it, and forbid the claims he rejected.

The store charges in **pounds**, so a price line that carries a dollar sign is a
wrong price even when the number is right. The scan therefore reads amounts with
either symbol and fails on the dollar one.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

from src.licensing import pricing
from src.licensing.pricing import (
    CURRENCY,
    CURRENCY_SYMBOL,
    DEPLOYMENT_DEFINITION,
    PRICE_PER_DEPLOYMENT,
    RENEWAL_PER_YEAR,
    UPDATES_INCLUDED_MONTHS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX = REPO_ROOT / "landing" / "index.html"
TERMS = REPO_ROOT / "landing" / "terms.html"
INSTALL = REPO_ROOT / "landing" / "install.html"
LANDING = REPO_ROOT / "landing"
DOCS_LICENSING = REPO_ROOT / "docs" / "user" / "reference" / "licensing.md"

#: The sentences the owner settled, compared WHOLE - a page or the order PDF that
#: paraphrases them is a different document from the terms.
SETTLED_SENTENCES = (
    "This licence is perpetual for the version you receive. It does not expire.",
    f"It includes all updates released within {UPDATES_INCLUDED_MONTHS} months of purchase.",
    "Updates released after that are not included and can be bought separately if you want them.",
    "Nothing renews automatically. You will not be charged again unless you choose to buy.",
    "Security fixes and bug fixes for the version you hold are provided at no charge.",
)

#: Every amount any landing page may show: the free tier, the price, the renewal.
ALLOWED_AMOUNTS = {0, PRICE_PER_DEPLOYMENT, RENEWAL_PER_YEAR}

#: A price with either symbol, in a page a buyer reads.
MONEY = re.compile(r"([$" + re.escape(CURRENCY_SYMBOL) + r"])\s?([\d][\d,]*)")

#: A dollar sign in front of a number: a wrong currency, whatever the digits say.
DOLLAR_PRICE = re.compile(r"\$\s?\d")

#: Claims the owner refused: an introductory price with no honest end date, a
#: list price he never charged, and a launch offer.
FORBIDDEN_CLAIMS = (
    "introductory",
    "was $",
    "was £",
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
    """The PDF's text as one line, so a phrase check reads what a buyer reads.

    pypdfium2 lives in the ``[pdf]`` extra, so a contributor on a plain
    ``uv sync`` does not have it. The house convention is importorskip.
    """
    pdfium = pytest.importorskip("pypdfium2", reason="pypdfium2 is in the [pdf] extra")

    pdf = pdfium.PdfDocument(str(path))
    try:
        text = "\n".join(page.get_textpage().get_text_range() for page in pdf)
    finally:
        pdf.close()
    return " ".join(text.split())


def _flat(path: Path) -> str:
    """The page as one line of collapsed whitespace, entities decoded.

    Decoded, because the HTML writes the pound sign as ``&pound;`` and the buyer
    reads ``£``. A check on the raw source would pass a page that renders wrong.
    """
    return " ".join(html.unescape(path.read_text(encoding="utf-8")).split())


def _amounts(text: str) -> dict[str, set[int]]:
    """Every amount in *text*, grouped by the symbol in front of it."""
    found: dict[str, set[int]] = {}
    for symbol, digits in MONEY.findall(text):
        found.setdefault(symbol, set()).add(int(digits.replace(",", "")))
    return found


def test_the_currency_is_stated_once_and_no_name_carries_it() -> None:
    """The symbol cannot be left behind: the constant names are currency-neutral."""
    assert CURRENCY == "GBP", "the store charges in pounds"
    assert CURRENCY_SYMBOL == "\N{POUND SIGN}", "the symbol a page prints must be the pound sign"

    offenders = [name for name in vars(pricing) if re.search(r"usd|gbp|dollar|pound", name, re.IGNORECASE)]
    assert offenders == [], (
        f"a currency in a constant name is the symbol left behind: rename it and read CURRENCY instead - {offenders}"
    )


def test_the_card_carries_the_price_from_the_one_source() -> None:
    page = _flat(INDEX)
    assert f"{CURRENCY_SYMBOL}{PRICE_PER_DEPLOYMENT}" in page, "the Pro card does not show the settled price"
    assert "Pricing announced at launch" not in page, "the placeholder price is still on the page"


def test_the_terms_carry_the_price_from_the_one_source() -> None:
    page = _flat(TERMS)
    assert f"{CURRENCY_SYMBOL}{PRICE_PER_DEPLOYMENT} per deployment" in page, "the terms do not state the settled price"
    # And no second number that could pass for a price.
    pounds = _amounts(page).get(CURRENCY_SYMBOL, set())
    assert pounds == {PRICE_PER_DEPLOYMENT}, f"the terms quote more than one price: {sorted(pounds)}"


def test_the_card_and_the_terms_define_a_deployment_the_same_way() -> None:
    for path in (INDEX, TERMS):
        assert DEPLOYMENT_DEFINITION in _flat(path), f"{path.name} does not carry the deployment definition"


def test_every_page_that_states_a_price_states_the_settled_one() -> None:
    """The install page shipped the price unguarded - changing it to $499 passed.

    Any amount on any landing page must be the free tier's zero, the settled
    price, or the renewal, **in pounds**; and the page that ships with the order
    must state the price itself, not merely avoid a wrong one.
    """
    wrong: dict[str, dict[str, set[int]]] = {}
    dollars: dict[str, str] = {}
    for path in sorted(LANDING.glob("*.html")):
        page = _flat(path)
        found = _amounts(page)
        unexpected = {symbol: amounts - ALLOWED_AMOUNTS for symbol, amounts in found.items()}
        unexpected = {symbol: amounts for symbol, amounts in unexpected.items() if amounts}
        if unexpected:
            wrong[path.name] = unexpected
        if DOLLAR_PRICE.search(page):
            dollars[path.name] = DOLLAR_PRICE.search(page).group(0)  # type: ignore[union-attr]

    assert wrong == {}, f"page(s) quoting a price the constant does not hold: {wrong}"
    assert dollars == {}, f"page(s) pricing in dollars, but the store charges in {CURRENCY}: {dollars}"

    assert f"{CURRENCY_SYMBOL}{PRICE_PER_DEPLOYMENT} per deployment" in _flat(INSTALL), (
        "the install page does not state the settled price"
    )


def test_the_docs_state_the_price_in_pounds() -> None:
    """The reference page is the one docs surface that prints the number."""
    page = _flat(DOCS_LICENSING)
    assert f"{CURRENCY_SYMBOL}{PRICE_PER_DEPLOYMENT} per deployment" in page, (
        "the licensing reference does not state the settled price"
    )
    assert not DOLLAR_PRICE.search(page), "the licensing reference prices in dollars"


def test_the_card_states_the_update_window_from_the_one_source() -> None:
    page = _flat(INDEX)
    assert f"{UPDATES_INCLUDED_MONTHS} months of purchase" in page


def test_the_renewal_price_is_on_the_pricing_page_and_not_in_the_terms() -> None:
    """Owner's decision: the renewal price is a page figure, not a contract term."""
    assert f"{CURRENCY_SYMBOL}{RENEWAL_PER_YEAR} a year" in _flat(INDEX), "the pricing page does not state the renewal"
    terms = _flat(TERMS)
    assert f"{CURRENCY_SYMBOL}{RENEWAL_PER_YEAR}" not in terms, "the renewal price leaked into the terms"
    assert "a year" not in terms, "the terms talk about a yearly figure"


def test_no_claim_the_owner_rejected_appears_on_the_site() -> None:
    for path in sorted((REPO_ROOT / "landing").glob("*.html")):
        page = _flat(path).lower()
        for claim in FORBIDDEN_CLAIMS:
            assert claim not in page, f"{path.name} carries a claim the owner rejected: {claim!r}"


def test_the_terms_state_the_four_settled_sentences_and_the_security_line() -> None:
    page = _flat(TERMS)
    for sentence in SETTLED_SENTENCES:
        assert sentence in page, f"the terms do not carry the settled sentence: {sentence!r}"


def test_the_terms_promise_nothing_about_future_years() -> None:
    page = _flat(TERMS).lower()
    for phrase in ("grandfathered", "price held", "prices will", "future price", "will not increase"):
        assert phrase not in page, f"the terms promise something about future pricing: {phrase!r}"


def test_the_order_pdf_carries_the_settled_sentences_verbatim() -> None:
    """Whole sentences, not fragments: the order document is kept by the buyer."""
    text = _pdf_text()

    for sentence in SETTLED_SENTENCES:
        assert sentence in text, f"the shipped PDF paraphrases or omits: {sentence!r}"

    for stale in (
        "perpetual for the version you buy",
        "Updates after the first 12 months are paid",
        # The two paraphrases the review found: same meaning, different words.
        "A perpetual licence for the version you receive; it does not expire",
        "All updates released within 12 months of purchase are included",
    ):
        assert stale not in text, f"the shipped PDF still carries the old wording: {stale!r}"

    lowered = text.lower()
    for claim in FORBIDDEN_CLAIMS:
        assert claim not in lowered, f"the shipped PDF carries a claim the owner rejected: {claim!r}"


def test_the_order_pdf_price_matches_the_one_source() -> None:
    """If the order PDF states a price, it states the settled one in pounds."""
    text = _pdf_text()
    if not MONEY.search(text):
        return  # this document carries no price at all, so it cannot carry a wrong one

    found = _amounts(text)
    assert set(found) == {CURRENCY_SYMBOL}, f"the shipped PDF prices in another currency: {sorted(found)}"
    assert found[CURRENCY_SYMBOL] <= {PRICE_PER_DEPLOYMENT}, (
        f"the PDF states a price that is not the settled one: {sorted(found[CURRENCY_SYMBOL])}"
    )
