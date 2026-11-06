"""t-1358: the ignore-list docs say what the product does, not what it was meant to.

`docs/ci.md` claimed the list shipped with Phase 7 and that CI "reports N
known-benign ignored". It does not: `src/ci_ignore.py` parses and validates the
file, `src/cli/headless.py` loads and counts the entries and prints
`ignores loaded: N`, and the matcher exists and is unit-tested but **nothing
calls it on a run's results** - so a failure in an ignored test still fails the
run.

These tests are the guard on the text: the page must not claim an ignore changes
an outcome, and it must say that matching is not implemented. They are a grep,
deliberately - the fault was a sentence, and the fix is that the sentence cannot
come back unnoticed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI_DOC = ROOT / "docs" / "ci.md"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"

#: Claims that would tell a reader a failure is reported as ignored.
REPORTING_CLAIMS = (
    "known-benign ignored",
    "instead of real failures",
    "surfaces every ignore",
    "CI reports",
)


def _ci_text() -> str:
    return CI_DOC.read_text(encoding="utf-8")


def test_the_ci_page_does_not_claim_a_failure_is_reported_as_ignored() -> None:
    lowered = _ci_text().lower()
    found = [phrase for phrase in REPORTING_CLAIMS if phrase.lower() in lowered]
    assert found == [], f"docs/ci.md still promises ignore reporting: {found}"


def test_the_ci_page_says_matching_is_not_implemented() -> None:
    text = _ci_text()
    assert "not implemented" in text.lower(), "docs/ci.md must say matching is not implemented"
    assert "does not yet change a run's outcome" in text, (
        "docs/ci.md must say an ignore does not change a run's outcome yet"
    )
    assert "ignores loaded" in text, "docs/ci.md must name what the run actually prints"


def test_the_ci_page_keeps_the_design_reason() -> None:
    """The honest version still explains why the list is human-recorded."""
    text = _ci_text()
    assert "anti-rug" in text
    assert "reason" in text and "required" in text


def test_the_architecture_row_does_not_promise_gating() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    asserts_that = [
        "instead of real failures",
        "lands in Phase 7b",
    ]
    for phrase in asserts_that:
        assert phrase not in text, f"docs/ARCHITECTURE.md still says {phrase!r}"
