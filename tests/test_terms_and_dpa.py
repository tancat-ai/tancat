"""The terms say what the market says and what is true; the DPA exists (j-0301).

Each assertion here is a sentence the owner settled on 2026-11-12, or the
guardrail around it:

- the free-tier limits are **not** described as switchable (no comparator writes
  that, and it advertises that the paid tier is optional);
- updates are **installable packages** with no runtime call - "delivered as files
  on Lemon Squeezy" was true of an older build and is now false;
- Lemon Squeezy is named **once**, in the payment clause, as merchant of record;
- support is the company's, answered by the developer;
- the perpetual licence is stated as a feature: nothing switches off;
- the business/consumer sentence is present;
- ``landing/dpa.html`` exists, says we are not a processor of test data, and names
  the providers.

The refund window, the price, the liability cap and the governing law are pinned
only to stop an edit to this page from moving them by accident.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from src.licensing.pricing import CURRENCY_SYMBOL, PRICE_PER_DEPLOYMENT

ROOT = Path(__file__).resolve().parent.parent
LANDING = ROOT / "landing"
TERMS = LANDING / "terms.html"
PRIVACY = LANDING / "privacy.html"
DPA = LANDING / "dpa.html"


def _text(path: Path) -> str:
    """The page as one line, entities decoded - what a buyer reads."""
    return " ".join(unescape(path.read_text(encoding="utf-8")).split())


def test_the_terms_do_not_advertise_that_the_limits_can_be_switched_off() -> None:
    page = _text(TERMS).lower()
    assert "nudge, not a lock" not in page, "the sentence that advertises a turned-off limit is back"
    assert "can turn them off" not in page, "the terms say the paid tier is optional again"
    assert "enforced locally" not in page, "the terms describe the local enforcement again"
    # The rule that follows it stays.
    assert "do not reset a limit to avoid paying" in page, "the rule against resetting a limit was lost"


def test_the_updates_clause_describes_installable_packages_and_no_runtime_call() -> None:
    page = _text(TERMS)
    assert "installable Python packages" in page, "the updates clause does not say how updates arrive"
    assert "upgrade the way you upgrade any Python tool" in page, "the clause does not say how a customer upgrades"
    assert "delivered as files" not in page, "the clause still describes the old file delivery"
    assert "no call to a vendor server" in page, "the clause does not rule out a runtime call"
    assert "no automatic update check" in page, "the clause does not rule out an update check"
    assert "choose when to install" in page, "the clause does not say the buyer chooses when to install"


def test_lemon_squeezy_is_named_once_as_the_merchant_of_record() -> None:
    raw = TERMS.read_text(encoding="utf-8")
    assert raw.count("Lemon Squeezy") == 1, (
        f"Lemon Squeezy is named {raw.count('Lemon Squeezy')} times - once, in the payment clause"
    )
    payment = _text(TERMS).split("Payment and refunds", 1)[1].split("Ending the licence", 1)[0]
    assert "Lemon Squeezy" in payment, "the one mention is not in the payment clause"
    assert "merchant of record" in payment, "the payment clause does not say what Lemon Squeezy is"


def test_the_company_provides_support_and_the_developer_answers_it() -> None:
    page = _text(TERMS)
    assert "Support is provided by Cat Tan Operations Ltd" in page, "support is not the company's"
    assert "the developer who builds TanCat answers it" in page, "the developer's part is gone"
    assert "within two working days" in page, "the two-working-day aim was lost"


def test_the_perpetual_licence_is_stated_as_a_feature() -> None:
    page = _text(TERMS)
    assert "nothing switches off if we stop trading" in page, "the perpetual licence is not stated as a feature"
    assert "the version you hold keeps running" in page, "the sentence does not say what keeps running"


def test_the_terms_state_who_buys_and_keep_consumer_rights() -> None:
    page = _text(TERMS)
    assert "sold to businesses" in page, "the terms do not say who the sale is for"
    assert "if you buy as a consumer" in page.lower(), "there is no consumer sentence"
    assert "do not remove" in page.lower() and "consumer" in page.lower(), "statutory rights are not preserved"


def test_the_dpa_is_linked_from_both_legal_pages() -> None:
    for page, name in ((TERMS, "terms"), (PRIVACY, "privacy")):
        html = page.read_text(encoding="utf-8")
        assert 'href="dpa.html"' in html, f"{name}.html does not link the data processing statement"


def test_the_page_title_matches_what_it_says() -> None:
    """It says we are not a processor, so it must not be titled an "agreement"."""
    html = DPA.read_text(encoding="utf-8")
    assert "<h1>Data processing statement</h1>" in html, "the page title no longer matches its content"
    assert "data processing agreement" not in html.lower(), "the page calls itself an agreement again"


def test_the_dpa_states_our_role_and_the_only_personal_data_we_handle() -> None:
    page = _text(DPA)
    assert "you are the controller and we are not a processor" in page, "the roles are not stated"
    assert "runs on your own machine and sends us nothing" in page, "the reason for the role is missing"
    assert "name, email address and licence details" in page, "the purchase record is not listed"
    assert "content of an email you send us" in page, "the support email is not listed"
    assert "no telemetry" in page, "the page does not rule out telemetry"


def test_the_dpa_names_the_providers_and_where_they_sit() -> None:
    page = _text(DPA)
    assert "Lemon Squeezy" in page and "merchant of record" in page, "the merchant of record is not named"
    assert "Zoho" in page, "the email provider is not named"
    assert "EU data centre" in page, "the email provider's data centre is not stated"
    assert "GitHub Pages" in page, "the site host is not named"


def test_the_dpa_keeps_the_retention_and_the_contact_the_privacy_notice_gives() -> None:
    page = _text(DPA)
    assert "six years" in page, "the tax retention period differs from the privacy notice"
    assert "24 months" in page, "the support retention period differs from the privacy notice"
    assert "hello@tancat.dev" in page, "the DPA gives no contact"
    assert "ico.org.uk" in page, "the DPA does not mention the regulator"


# The four guardrails the brief said not to move, one test each. Four tests, not
# one: a single function stops at its first failure, so a stale price assert hid
# the law and the licence behind it (t-1414).


def test_the_price_is_the_settled_one() -> None:
    # Symbol and number come from src/licensing/pricing.py. A literal "$399" was
    # the bug: the store moved to pounds and this pin went stale.
    assert f"{CURRENCY_SYMBOL}{PRICE_PER_DEPLOYMENT} per deployment" in _text(TERMS), "the price moved"


def test_the_refund_window_is_thirty_days() -> None:
    assert "within 30 days of purchase" in _text(TERMS), "the refund window moved"


def test_the_governing_law_is_england_and_wales() -> None:
    assert "law of England and Wales" in _text(TERMS), "the governing law moved"


def test_the_liability_cap_is_twelve_months_of_fees() -> None:
    assert "12 months before the claim" in _text(TERMS), "the liability cap moved"


def test_the_licence_is_the_business_source_licence() -> None:
    assert "Business Source License 1.1" in _text(TERMS), "the licence changed"


# --- the update truth, as a rule over every page (t-1416) --------------------

#: Every page a buyer can read. A glob, not a list: the reviewer defeated a fixed
#: list by putting the old sentence on a fifth page.
PAGE_GLOBS = (
    (LANDING, "*.html"),
    (ROOT / "docs" / "user", "**/*.md"),
)

#: A sentence speaks of updates if it carries one of these forms. "Last updated" is
#: a date stamp, not a delivery claim, so it is excluded.
UPDATE_WORD = re.compile(r"\bupdates?\b|\bupdating\b|(?<!last )\bupdated\b", re.IGNORECASE)

#: The one delivery the owner settled. A sentence carrying it is the settled claim.
SETTLED_DELIVERY = "released as installable Python packages"

#: How an update could be described as reaching a buyer. This is a RULE, not the old
#: phrasing: the reviewer defeated a phrase list twice, so the test asks what an
#: update sentence says rather than whether it contains one known string.
DELIVERY_WORDS = (
    "download",
    "downloads",
    "downloaded",
    "downloading",
    "deliver",
    "delivers",
    "delivered",
    "delivery",
    "arrive",
    "arrives",
    "arrived",
    "arriving",
    "file",
    "files",
    "store",
    "stores",
    "shop",
    "shops",
    "send",
    "sends",
    "sent",
    # "we email you the update" is the same claim as "we send it to you": an early
    # version of this list had only "emailed"/"emails" and my own attack walked past
    # it (t-1416).
    "email",
    "emails",
    "emailed",
    "post",
    "posted",
    "courier",
)

#: Where a buyer could be told to go and fetch one.
STORE_NAMES = ("lemon squeezy", "lemonsqueezy", "app store", "play store")

#: An HTML tag that ends a block. Without this, whole tables flatten into one
#: "sentence" and every block-level word lands in it.
BLOCK_END = re.compile(
    r"</(?:p|li|tr|td|th|h[1-6]|div|section|footer|title)>|<br\s*/?>",
    re.IGNORECASE,
)


def buyer_pages() -> list[Path]:
    """Every page a buyer can read, from the two globs."""
    found: set[Path] = set()
    for base, pattern in PAGE_GLOBS:
        found.update(path for path in base.glob(pattern) if path.is_file())
    return sorted(found)


def _blocks(path: Path) -> list[str]:
    """The page as block-level text: tags removed, entities decoded, blocks split."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".html":
        raw = BLOCK_END.sub("\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    text = unescape(raw)
    blocks = [" ".join(chunk.split()) for chunk in text.split("\n")]
    return [block for block in blocks if block]


def _sentences(path: Path) -> list[str]:
    sentences: list[str] = []
    for block in _blocks(path):
        sentences.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", block) if part.strip())
    return sentences


def _delivery_hits(sentence: str) -> list[str]:
    low = sentence.lower()
    hits = [word.strip() for word in DELIVERY_WORDS if re.search(rf"\b{re.escape(word.strip())}\b", low)]
    hits.extend(name for name in STORE_NAMES if name in low)
    return sorted(set(hits))


def test_no_update_sentence_delivers_an_update_any_other_way() -> None:
    """Ask what each update sentence says, on every page, not a phrase list."""
    pages = buyer_pages()
    assert len(pages) >= 15, f"the page globs found only {len(pages)} pages - the scan is not seeing the site"

    problems: list[str] = []
    seen = 0
    for path in pages:
        for sentence in _sentences(path):
            if not UPDATE_WORD.search(sentence):
                continue
            seen += 1
            if SETTLED_DELIVERY.lower() in sentence.lower():
                continue  # this IS the settled claim
            hits = _delivery_hits(sentence)
            if hits:
                problems.append(
                    f"{path.relative_to(ROOT)}: update sentence claims delivery by {hits}: {sentence[:180]!r}"
                )

    assert seen >= 20, f"only {seen} update sentences scanned - the sentence splitter is not working"
    assert problems == [], (
        "a page describes update delivery in words the terms do not use:" + "\n" + "  " + ("\n" + "  ").join(problems)
    )


def test_every_page_that_speaks_of_updates_states_the_settled_delivery() -> None:
    """Derived from the text: a new page that mentions updates inherits the rule."""
    problems = [
        f"{path.relative_to(ROOT)}: speaks of updates but does not carry {SETTLED_DELIVERY!r}"
        for path in buyer_pages()
        if any(UPDATE_WORD.search(sentence) for sentence in _sentences(path)) and SETTLED_DELIVERY not in _text(path)
    ]
    assert problems == [], (
        "a page speaks of updates without stating how they arrive:" + "\n" + "  " + ("\n" + "  ".join(problems))
    )


def test_every_page_that_states_the_delivery_also_rules_out_both_shortcuts() -> None:
    """The settled sentence is followed by its guarantees; they cannot be dropped."""
    problems: list[str] = []
    for path in buyer_pages():
        page = _text(path)
        if SETTLED_DELIVERY not in page:
            continue
        if "no call to a vendor server" not in page:
            problems.append(f"{path.relative_to(ROOT)}: states the delivery but not the vendor-call guarantee")
        if "no automatic update check" not in page:
            problems.append(f"{path.relative_to(ROOT)}: states the delivery but not the update-check guarantee")
    assert problems == [], (
        "a page leaves the product's update behaviour open:" + "\n" + "  " + ("\n" + "  ".join(problems))
    )
