"""No personal data in the RAG corpus, and none of the class that slipped in (t-1436).

Three documents in ``docs/rag_corpus/lv_docs`` were named ``*_redacted.md`` and were
not: a real person's car-insurance schedule, amendment letter and certificate, each
carrying an email address, telephone numbers and postcodes, in a public repository.
They are synthetic now, and named ``*_synthetic.md`` - a file called "redacted" in a
public repository tells a reader the opposite of what is true. This test refuses the
whole class rather than those three strings:

- an **email address** must be at a reserved domain (``example.com``, ``.org``,
  ``.net`` - RFC 2606);
- a **UK telephone number** must be in Ofcom's drama range, ``01632 960xxx``;
- a **UK postcode** must be one of the reserved examples (``SW1A 1AA``,
  ``EC1A 1BB``).

The only other allowance is the corporate contact details printed inside the three
insurer PDFs, which are the insurer's own published documents (a switchboard, a data
protection mailbox, a registered-office postcode) and are public, not personal.

A failure names the **file** and the **kind** only - the value is never printed, so a
red build cannot republish what it caught.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "docs" / "rag_corpus"

#: Text formats the corpus is allowed to carry. PDFs are handled separately.
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".yml", ".yaml", ".html", ".htm"}

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
#: UK-shaped phone numbers, with bounded digit groups so a page number that follows
#: a switchboard on the next line is not swallowed ("0330 1239970 3" -> 0330 1239970).
PHONE = re.compile(
    r"(?:\+44\s?\d{2,4}\s?\d{3,4}\s?\d{3,4}"  # +44 1202 880354
    r"|\(\d{4,5}\)\s?\d{5,6}"  # (01632) 960123
    r"|\d{3,5}[\s-]?\d{3,4}[\s-]?\d{3,4})"  # 01632 960123 / 0330 678 5555
)
#: UK postcode shape (both parts, so a bare outward code is not a match).
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.IGNORECASE)

#: Reserved example domains (RFC 2606).
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")

#: Ofcom's drama range, which no real subscriber can hold: 01632 960000-960999.
DRAMA_NUMBER = re.compile(r"^01632960\d{3}$")

#: Reserved example postcodes.
ALLOWED_POSTCODES = {"SW1A1AA", "EC1A1BB"}

#: The insurer's published corporate details, read from the three PDFs already in
#: the corpus. Public company contact details, not personal data.
PUBLISHED_CORPORATE = {
    "gifeedback@lv.co.uk",
    "gidataprotection@lv.co.uk",
    "03306785111",
    "03301239970",
    "03301239973",
    "03301239974",
    "03306785550",
    "03306785590",
    "03306785555",
    "08000234567",
    "+441202880354",
    "BH12AT",
    "GU11DB",
}


def _normalise(value: str) -> str:
    return re.sub(r"[\s-]+", "", value).lower()


def corpus_files() -> list[Path]:
    """The tracked files under docs/rag_corpus - what a checkout and CI see."""
    result = subprocess.run(["git", "ls-files", "docs/rag_corpus"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, "git ls-files failed, so the scan cannot know the corpus"
    return sorted(ROOT / name for name in result.stdout.split() if name.strip())


def personal_data_problems(text: str, *, allow_published_corporate: bool = False) -> list[str]:
    """The kinds of personal data in *text* that are not reserved examples.

    *allow_published_corporate* is for the insurer's own PDFs only: those carry a
    switchboard, a data-protection mailbox and a registered-office postcode, all
    printed in a published document. An authored page gets no such allowance - a
    real postcode in a Markdown file is exactly what this test exists to catch.
    """
    allowed = PUBLISHED_CORPORATE if allow_published_corporate else set()
    problems: list[str] = []

    for value in EMAIL.findall(text):
        domain = value.rsplit("@", 1)[-1].lower()
        if domain not in ALLOWED_EMAIL_DOMAINS and _normalise(value) not in allowed:
            problems.append("email address")

    for value in PHONE.findall(text):
        digits = _normalise(value)
        if not DRAMA_NUMBER.match(digits) and digits not in allowed:
            problems.append("phone number")

    for value in POSTCODE.findall(text):
        compact = _normalise(value).upper()
        if compact not in ALLOWED_POSTCODES and compact not in allowed:
            problems.append("postcode")

    return problems


def _report(problems: list[str]) -> str:
    return "personal data in the RAG corpus (file: kind, value withheld):" + "\n  " + "\n  ".join(problems)


def test_no_personal_data_in_the_corpus_text() -> None:
    files = [path for path in corpus_files() if path.suffix.lower() in TEXT_SUFFIXES]
    assert len(files) >= 4, f"the scan found only {len(files)} text files - it is not seeing the corpus"

    problems: list[str] = []
    for path in files:
        for kind in personal_data_problems(path.read_text(encoding="utf-8", errors="replace")):
            problems.append(f"{path.relative_to(ROOT).as_posix()}: {kind}")

    assert problems == [], _report(problems)


def test_no_personal_data_in_the_corpus_pdfs() -> None:
    """The three insurer PDFs: corporate contact details only, and they are public."""
    pdfplumber = pytest.importorskip("pdfplumber", reason="pdfplumber is in the [pdf] extra")
    files = [path for path in corpus_files() if path.suffix.lower() == ".pdf"]
    assert len(files) >= 3, f"the scan found only {len(files)} PDFs - it is not seeing the corpus"

    problems: list[str] = []
    for path in files:
        with pdfplumber.open(path) as document:
            text = " ".join((page.extract_text() or "") for page in document.pages)
        for kind in personal_data_problems(text, allow_published_corporate=True):
            problems.append(f"{path.relative_to(ROOT).as_posix()}: {kind}")

    assert problems == [], _report(problems)


def test_the_synthetic_documents_say_they_are_synthetic() -> None:
    """A reader (and the next agent) must not mistake the sample for a real policy."""
    for name in ("schedule_synthetic.md", "letter_synthetic.md", "certificate_synthetic.md"):
        text = (CORPUS / "lv_docs" / name).read_text(encoding="utf-8")
        assert "Synthetic example document" in text, f"{name} does not declare itself synthetic"


def test_the_synthetic_documents_keep_the_sections_ingestion_exercises() -> None:
    """Same shape as before: the corpus still tests 'personal documents'."""
    schedule = (CORPUS / "lv_docs" / "schedule_synthetic.md").read_text(encoding="utf-8")
    for marker in ("Policy No.", "Insured from:", "Registration number:", "Cover:", "Excesses"):
        assert marker in schedule, f"the schedule lost its {marker!r} section"

    letter = (CORPUS / "lv_docs" / "letter_synthetic.md").read_text(encoding="utf-8")
    for marker in ("Policy number", "Effective start date", "Additional premium", "Registration"):
        assert marker in letter, f"the letter lost its {marker!r} section"

    certificate = (CORPUS / "lv_docs" / "certificate_synthetic.md").read_text(encoding="utf-8")
    for marker in ("Certificate Number", "Registration mark", "Date of expiry", "Limitations as to use"):
        assert marker in certificate, f"the certificate lost its {marker!r} section"


def test_no_corpus_file_is_named_redacted() -> None:
    """The name is a claim about the content, so it must not survive the rewrite.

    A reader who sees ``*_redacted.md`` learns that something was taken out of a
    document - which was true of the old files and is false of these. The class
    rule above covers the data; this covers the name.
    """
    offenders = sorted(path.relative_to(ROOT).as_posix() for path in corpus_files() if "redacted" in path.name.lower())
    assert offenders == [], f"a corpus file still claims to be a redaction: {offenders}"
