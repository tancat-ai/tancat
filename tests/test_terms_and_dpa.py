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
        assert 'href="dpa.html"' in html, f"{name}.html does not link the data processing agreement"


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


def test_the_guardrails_named_in_the_brief_are_untouched() -> None:
    page = _text(TERMS)
    assert "within 30 days of purchase" in page, "the refund window moved"
    assert re.search(r"\$\s?399 per deployment", page), "the price moved"
    assert "12 months before the claim" in page, "the liability cap moved"
    assert "law of England and Wales" in page, "the governing law moved"
    assert "Business Source License 1.1" in page, "the licence changed"
