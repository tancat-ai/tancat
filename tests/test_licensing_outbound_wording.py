"""j-0304: no page may claim "no outbound traffic" while activation exists.

The activation call made five sentences false. This test holds the pages and the
licensing docs to what the code does: one activation call to Lemon Squeezy, then
nothing. It fails if any page claims otherwise, and it checks the replacement
sentences are present, so a future revert is caught too.
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
)

#: The order PDF ships with every purchase, and its source is docs/implementation.
ORDER_PDF = LANDING / "tancat-pro-install-and-licence.pdf"
IMPLEMENTATION = REPO_ROOT / "docs" / "implementation"

#: Documents that must now say the activation call happens.
MUST_SAY = {
    LANDING / "privacy.html": "Lemon Squeezy",
    LANDING / "install.html": "licensing service",
    LANDING / "terms.html": "merchant of record named above",
    DOCS / "reference" / "licensing.md": "one call to a vendor",
    DOCS / "getting-started" / "install.md": "one call to a vendor",
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
    assert "no further call" in text, "the shipped PDF does not say the call is once"
    assert "installable Python packages" in text, "the shipped PDF describes update delivery the old way"


def test_each_document_names_the_one_activation_call() -> None:
    missing = [str(path.relative_to(REPO_ROOT)) for path, phrase in MUST_SAY.items() if phrase not in _flat(path)]
    assert missing == [], f"document(s) that do not mention the activation call: {missing}"


def test_the_privacy_notice_names_the_runtime_recipient() -> None:
    """Lemon Squeezy receives the key and the instance name at activation."""
    page = _flat(LANDING / "privacy.html")
    assert "Lemon Squeezy" in page
    assert re.search(r"activation call to Lemon Squeezy|single activation call", page), page[:200]


def test_the_install_footer_says_paid_once() -> None:
    page = _flat(LANDING / "install.html")
    assert "paid once" in page
    assert "£399 per deployment, one price" not in page.replace("&pound;", "£")


def test_the_terms_say_the_call_happens_once() -> None:
    page = _flat(LANDING / "terms.html")
    assert "one call to a vendor server" in page
    assert "After activation it makes no further call." in page
