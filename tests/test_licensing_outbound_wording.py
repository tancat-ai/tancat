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
)

#: The check phrase, in every form a denial uses: noun, plural and verb.
CHECK_WORD = re.compile(r"check(ed|s|ing)?(?![a-z])", re.IGNORECASE)
CHECK_TOPIC = re.compile(r"(update|version)s?(?![a-z])", re.IGNORECASE)

#: Negations and DISABLING verbs. "are never performed", "is disabled", "avoids",
#: "free of" and "switched off" are all denials a positional-before rule missed.
DENIAL_CUES = re.compile(
    r"(?<![a-z])(no|never|not|none|without|free of|zero|disabled|disable|avoids?|avoided|"
    r"omits?|omitted|skips?|suppressed|removed)(?![a-z])",
    re.IGNORECASE,
)
SWITCHED_OFF = re.compile(r"(switched|turned) off(?![a-z])", re.IGNORECASE)

#: Benign shapes that contain a cue word but say the OPPOSITE. Each is here for a
#: reason, and the test below asserts every one still passes:
#:  - "two kinds of call and no others ... a version check": "no others" counts the
#:    KINDS of call; it does not deny the check;
#:  - "the version check sends nothing about you": that is what the check sends,
#:    not whether it happens;
#:  - "can be turned off in settings": the CUSTOMER may switch it off; the product
#:    still checks unless told not to.
BENIGN = (
    "no others",
    "two kinds of call",
    "sends nothing about you",
    "nothing about you is sent",
    "carries nothing about you",
    "can be turned off",
    "turned off in settings",
    "settings turns it off",
    "turn the update check off",
    "if you leave the update check on",
)

#: How far either side of the check phrase a cue counts. A short window, not the
#: whole clause: "no others: ... a version check" is far enough away to be a list,
#: while "checks are never performed" is inside it.
WINDOW_CHARS = 60

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def denies_a_check(sentence: str) -> bool:
    """True when *sentence* mentions an update/version check and denies one.

    A RULE, not a phrase list. A denial counts when a negation or a disabling verb
    sits within ``WINDOW_CHARS`` on EITHER side of the check phrase - the earlier
    version looked only backwards, so "Update checks are never performed" and "The
    version check is disabled" slipped through. The vocabulary carries the passive
    and disabling forms ("are never performed", "is disabled", "avoids", "free of",
    "switched off") and "checked" as a verb.

    Residual risk: any rule over English has gaps. These are the shapes we know
    about; a reviewer who finds a new one adds it as a test here, and the rule grows
    rather than being re-listed.
    """
    if not CHECK_TOPIC.search(sentence):
        return False
    low = sentence.lower()
    if any(marker in low for marker in BENIGN):
        return False
    match = CHECK_WORD.search(low)
    if match is None:
        return False
    window = low[max(0, match.start() - WINDOW_CHARS) : match.end() + WINDOW_CHARS]
    return bool(DENIAL_CUES.search(window) or SWITCHED_OFF.search(window))


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


def test_the_activation_path_is_gone() -> None:
    """j-0309: licensing is offline, so no page may claim an activation call."""
    assert not (REPO_ROOT / "src" / "licensing" / "activation.py").exists()
    source = " ".join(p.read_text(encoding="utf-8", errors="replace") for p in (REPO_ROOT / "src").rglob("*.py"))
    assert "api.lemonsqueezy.com" not in source.lower()
    assert "licenses/activate" not in source.lower()


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


def test_no_document_denies_an_update_check() -> None:
    """Every sentence on every buyer document, through the rule."""
    offenders: dict[str, list[str]] = {}
    for name, text in _scanned_documents():
        bad = [sentence for sentence in SENTENCE_END.split(text) if denies_a_check(sentence)]
        if bad:
            offenders[name] = bad[:3]
    assert offenders == {}, f"document(s) that deny an update check while one exists: {offenders}"


def test_the_denial_rule_catches_the_four_that_slipped_and_three_more() -> None:
    """Proof the rule, not a list. The first four are the review's slipped shapes."""
    denied = [
        "Update checks are never performed.",
        "The version check is disabled.",
        "TanCat avoids any update check.",
        "Updates are never checked.",
        # Three more of the same family, none of them on any list.
        "The product performs no update checks.",
        "TanCat never performs an update check.",
        "Update checking is switched off by the application.",
    ]
    for sentence in denied:
        assert denies_a_check(sentence), sentence


def test_the_denial_rule_still_passes_the_three_known_good_shapes() -> None:
    """Why each passes: the cue word is about something else, or the customer acts."""
    allowed = [
        # "no others" counts the kinds of call, not the check.
        "TanCat makes exactly one automatic call and no others: a version check at most once a day.",
        # This is what the check sends, not whether it happens.
        "The version check sends nothing about you.",
        # The customer may switch it off; the product still checks unless told not to.
        "It can be turned off in settings.",
        "It makes at most one version check a day.",
    ]
    for sentence in allowed:
        assert not denies_a_check(sentence), sentence


def test_no_page_claims_no_outbound_traffic() -> None:
    """Pages, the PDF source and the PDFs themselves - a shipped document counts."""
    offenders: dict[str, list[str]] = {}
    for name, text in _scanned_documents():
        found = [claim for claim in FALSE_CLAIMS if claim in text.lower()]
        if found:
            offenders[name] = found
    assert offenders == {}, f"document(s) still claim no vendor traffic while activation calls out: {offenders}"


def test_the_order_pdf_carries_the_one_call_truth() -> None:
    """The PDF is regenerated from its source; the shipped text must say so too."""
    text = _pdf_text(ORDER_PDF)
    assert "licensing service" not in text, "the shipped PDF still says there is a licensing call"
    assert "one version check a day" in text, "the shipped PDF does not state the daily version check"
    assert "verified offline" in text, "the shipped PDF does not say licensing is offline"
    assert "installable Python packages" in text, "the shipped PDF describes update delivery the old way"


def test_each_document_names_the_one_automatic_call() -> None:
    missing = [str(path.relative_to(REPO_ROOT)) for path, phrase in MUST_SAY.items() if phrase not in _flat(path)]
    assert missing == [], f"document(s) that do not mention the one automatic call: {missing}"


def test_no_document_mentions_an_activation_call() -> None:
    """The removed path must not survive in copy a buyer can read."""
    offenders: dict[str, str] = {}
    for name, text in _scanned_documents():
        low = text.lower()
        for stale in ("activation", "licensing service", "two kinds of call", "lemon squeezy"):
            if stale in low:
                offenders[name] = stale
                break
    assert offenders == {}, f"document(s) still describe the removed activation path: {offenders}"


def test_the_privacy_notice_names_the_one_automatic_call() -> None:
    """The version check is the only thing the product asks US for."""
    page = _flat(LANDING / "privacy.html")
    assert "version" in page.lower() and "check" in page.lower(), "the notice does not mention the check"
    assert "sends nothing about you" in page or "carries nothing about you" in page, "the notice does not draw the line"
    assert "Lemon Squeezy" not in page, "the notice still names a merchant as a runtime recipient"


def test_the_install_footer_says_paid_once() -> None:
    page = _flat(LANDING / "install.html")
    assert "paid once" in page
    assert "£399 per deployment, one price" not in page.replace("&pound;", "£")


def test_the_terms_say_one_automatic_call_and_that_licensing_is_offline() -> None:
    page = _flat(LANDING / "terms.html")
    assert "exactly one automatic call" in page
    assert "version check at most once a day" in page
    assert "licensing never touches the network" in page.lower()
    assert "two kinds of outbound call" not in page


# ---------------------------------------------------------------------------
# t-1466: the dead key flow, as a CLASS of words, and every provider name
# ---------------------------------------------------------------------------

#: Words and variables that belong to the removed store-key path. A buyer document
#: may contain none of them - not even in a negation, because the reader sees the
#: noun and assumes it is a step.
DEAD_KEY_WORDS = (
    "activate",
    "activation",
    "licence key",
    "license key",
    "AITEST_LICENSE_KEY",
    "AITEST_LICENSE_FILE",
)

#: The truth every buyer document must state instead.
SIGNED_FILE_PHRASE = "signed licence"


def _buyer_documents() -> list[tuple[str, str]]:
    """Pages, the implementation source, the shipped PDFs and the user docs."""
    return _scanned_documents()


def test_no_buyer_document_teaches_the_dead_key_flow() -> None:
    offenders: dict[str, list[str]] = {}
    for name, text in _buyer_documents():
        low = text.lower()
        found = [word for word in DEAD_KEY_WORDS if word.lower() in low]
        if found:
            offenders[name] = found
    assert offenders == {}, f"document(s) still teach the removed key flow: {offenders}"


#: The documents that discuss licensing, and so must describe the real flow.
LICENSING_DOCUMENTS = (
    LANDING / "terms.html",
    LANDING / "privacy.html",
    LANDING / "install.html",
    LANDING / "index.html",
    DOCS / "reference" / "licensing.md",
    DOCS / "getting-started" / "install.md",
    IMPLEMENTATION / "tancat-pro-install-and-licence.html",
)


def test_every_licensing_document_states_the_signed_file() -> None:
    """A page that talks about the licence must say what a licence is."""
    missing = [str(path.relative_to(REPO_ROOT)) for path in LICENSING_DOCUMENTS if "signed" not in _flat(path).lower()]
    assert missing == [], f"document(s) that do not mention the signed licence file: {missing}"
    assert "signed" in _pdf_text(ORDER_PDF).lower(), "the shipped PDF does not say the licence is signed"


def test_a_planted_key_instruction_is_caught() -> None:
    """Prove the rule on the real document: plant the old sentence, watch it fail.

    The PDF source is the one a buyer follows step by step, so it is where a stale
    instruction does the most damage.
    """
    target = IMPLEMENTATION / "tancat-pro-install-and-licence.html"
    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(
            original.replace(
                "&mdash; nothing is switched on, and no call is made to us or",
                "by pasting it as AITEST_LICENSE_KEY &mdash; nothing is switched on, and no call is made to us or",
                1,
            ),
            encoding="utf-8",
        )
        found = [word for word in DEAD_KEY_WORDS if word.lower() in _flat(target).lower()]
        assert found, "the plant did not land - the test would pass vacuously"
        assert "AITEST_LICENSE_KEY" in found
    finally:
        target.write_text(original, encoding="utf-8")


#: Providers that a buyer document must never name: the store is not chosen yet,
#: and naming one promises a route that does not exist.
PROVIDER_NAMES = ("lemon squeezy", "lemonsqueezy", "paddle", "polar", "creem", "fastspring", "gumroad", "stripe")


#: Copy in the product that a buyer can read: string literals, not docstrings.
def _product_copy_strings() -> list[tuple[str, str]]:
    import ast

    found: list[tuple[str, str]] = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                found.append((path.relative_to(REPO_ROOT).as_posix(), node.value))
    return found


def test_no_buyer_document_names_a_provider() -> None:
    """No store is signed, so no page may promise one - terms.html included."""
    offenders: dict[str, list[str]] = {}
    for name, text in _buyer_documents():
        low = text.lower()
        found = [provider for provider in PROVIDER_NAMES if provider in low]
        if found:
            offenders[name] = found
    assert offenders == {}, f"document(s) naming a provider that is not signed: {offenders}"


def test_no_product_copy_names_a_provider() -> None:
    """The same rule over what the CLI and the UI print (docstrings excluded)."""
    offenders: dict[str, list[str]] = {}
    for path, value in _product_copy_strings():
        low = value.lower()
        found = [provider for provider in PROVIDER_NAMES if provider in low]
        if found:
            offenders[path] = found
    assert offenders == {}, f"product copy names a provider that is not signed: {offenders}"


def test_a_planted_provider_name_is_caught() -> None:
    """Two plants: 'Polar' in privacy.html, 'Creem' in an install-page string."""
    privacy = LANDING / "privacy.html"
    install = LANDING / "install.html"
    original_privacy = privacy.read_text(encoding="utf-8")
    original_install = install.read_text(encoding="utf-8")
    try:
        privacy.write_text(
            original_privacy.replace("our host (GitHub Pages)", "Polar (our store)", 1), encoding="utf-8"
        )
        install.write_text(
            original_install.replace("Install and add your licence", "Creem checkout", 1), encoding="utf-8"
        )

        page_offenders = [
            provider
            for provider in PROVIDER_NAMES
            if provider in _flat(privacy).lower() or provider in _flat(install).lower()
        ]
        assert "polar" in page_offenders, "the privacy plant did not land"
        assert "creem" in page_offenders, "the install plant did not land"
    finally:
        privacy.write_text(original_privacy, encoding="utf-8")
        install.write_text(original_install, encoding="utf-8")
