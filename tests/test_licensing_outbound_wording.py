"""j-0304 / j-0306: the site must state the two calls it makes, and no other.

TanCat makes two kinds of outbound call: one activation request, and a version
check at most once a day that can be switched off. These tests hold every buyer
document - pages, the PDF source, the order PDF itself and the user docs - to that
truth, and fail on any document that claims there is no outbound call at all or
leaves the version check out.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LANDING = REPO_ROOT / "landing"
DOCS = REPO_ROOT / "docs" / "user"

#: Claims that are false once ``src/licensing/activation.py`` exists.
FALSE_CLAIMS = (
    "no vendor call",
    "zero outbound traffic",
    "and to nowhere else",
    "makes no call to a vendor server",
    "no call to a vendor server",
    "no vendor server call",
    # j-0306: the version check exists, so a document that rules out update checks
    # is false too.
    "no automatic update check",
    "no update check",
)

#: The order PDF ships with every purchase, and its source is docs/implementation.
ORDER_PDF = LANDING / "tancat-pro-install-and-licence.pdf"
IMPLEMENTATION = REPO_ROOT / "docs" / "implementation"

#: Documents that must now say the activation call happens.
MUST_SAY = {
    LANDING / "privacy.html": "version check",
    LANDING / "install.html": "version check a day",
    LANDING / "terms.html": "version check at most once a day",
    DOCS / "reference" / "licensing.md": "version check at most once a day",
    DOCS / "getting-started" / "install.md": "version check at most once a day",
    IMPLEMENTATION / "tancat-pro-install-and-licence.html": "one version check a day",
}


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _user_docs() -> list[Path]:
    return sorted(DOCS.rglob("*.md"))


def test_the_activation_module_exists() -> None:
    """The pages are only held to this rule because the call is real."""
    module = REPO_ROOT / "src" / "licensing" / "activation.py"
    assert module.is_file()
    text = module.read_text(encoding="utf-8")
    assert "api.lemonsqueezy.com/v1/licenses/activate" in text


def _pdf_text(path: Path) -> str:
    """The PDF as one line, so a shipped document is scanned like a page."""
    pdfplumber = pytest.importorskip("pdfplumber", reason="pdfplumber is used elsewhere in the suite")
    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return " ".join(text.split())


def _scanned_documents() -> list[tuple[str, str]]:
    """Every document a buyer can read: pages, the implementation source, the PDFs."""
    docs: list[tuple[str, str]] = []
    for path in sorted(LANDING.glob("*.html")):
        docs.append((path.name, _flat(path)))
    for path in sorted(IMPLEMENTATION.glob("*.html")):
        docs.append((f"docs/implementation/{path.name}", _flat(path)))
    for path in sorted(LANDING.glob("*.pdf")):
        docs.append((path.name, _pdf_text(path)))
    for path in _user_docs():
        docs.append((str(path.relative_to(REPO_ROOT)), _flat(path)))
    return docs


def test_no_page_claims_no_outbound_traffic() -> None:
    """Pages, the PDF source and the PDFs themselves - a shipped document counts."""
    offenders: dict[str, list[str]] = {}
    for name, text in _scanned_documents():
        found = [claim for claim in FALSE_CLAIMS if claim in text.lower()]
        if found:
            offenders[name] = found
    assert offenders == {}, f"document(s) still claim no vendor traffic while activation calls out: {offenders}"


def test_the_order_pdf_carries_the_activation_truth() -> None:
    """The PDF is regenerated from its source; the shipped text must say so too."""
    text = _pdf_text(ORDER_PDF)
    assert "once to our licensing service" in text, "the shipped PDF does not say one activation call"
    assert "one version check a day" in text, "the shipped PDF does not state the daily version check"
    assert "sends nothing about you" in text, "the shipped PDF does not draw the line"
    assert "installable Python packages" in text, "the shipped PDF describes update delivery the old way"


def test_each_document_names_the_one_activation_call() -> None:
    missing = [str(path.relative_to(REPO_ROOT)) for path, phrase in MUST_SAY.items() if phrase not in _flat(path)]
    assert missing == [], f"document(s) that do not mention the activation call: {missing}"


def test_the_privacy_notice_names_both_runtime_recipients() -> None:
    """Lemon Squeezy gets the key; PyPI gets the version question and nothing else."""
    page = _flat(LANDING / "privacy.html")
    assert "Lemon Squeezy" in page
    assert re.search(r"single activation call to Lemon Squeezy", page), page[:200]
    assert "pypi.org" in page, "the notice does not name what the version check contacts"
    assert "sends nothing about you" in page, "the notice does not draw the line"


def test_the_install_footer_says_paid_once() -> None:
    page = _flat(LANDING / "install.html")
    assert "paid once" in page
    assert "£399 per deployment, one price" not in page.replace("&pound;", "£")


def test_the_terms_say_both_calls_and_that_the_product_works_offline() -> None:
    page = _flat(LANDING / "terms.html")
    assert "two kinds of outbound call and no others" in page
    assert "version check at most once a day" in page
    assert "works with no internet connection" in page
