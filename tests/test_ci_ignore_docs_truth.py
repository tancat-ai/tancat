"""t-1358 / t-1362: the ignore-list docs and the report say what happens.

`docs/ci.md` claimed the list shipped with Phase 7 and that CI "reports N
known-benign ignored". It does not: `src/ci_ignore.py` parses and validates the
file, `src/cli/headless.py` loads and counts the entries and prints
`ignores loaded: N`, and the matcher exists and is unit-tested but **nothing
calls it on a run's results** - so a failure in an ignored test still fails the
run.

Two kinds of assertion, both needed (the reviewer's note on t-1358):

* **absence** - the claim cannot come back;
* **presence** - the corrected wording, the validation fact and the pointer to
  the follow-up must still be there. Absence alone passes on a deleted row.

The generated report's own sentence is guarded too: it must invite the reader to
record an ignore, never to expect it to silence a failure.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI_DOC = ROOT / "docs" / "ci.md"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
SPEC = ROOT / "docs" / "specs" / "FEATURE_SPEC_phase7_ci_cd_integration.md"
MODULE = ROOT / "src" / "ci_ignore.py"
REPORT = ROOT / "action" / "report.py"

#: Claims that would tell a reader a failure is reported as ignored.
REPORTING_CLAIMS = (
    "known-benign ignored",
    "instead of real failures",
    "surfaces every ignore",
    "CI reports",
)

#: The corrected facts that must be present, not merely un-contradicted.
CI_FACTS = (
    "with one piece of the spec not built",  # the banner is qualified
    "matching an ignore against a failure is not implemented",
    "does not yet change a run's outcome",
    "ignores loaded",
    "anti-rug",
)
ARCHITECTURE_FACTS = (
    "nothing calls it on a run's results",
    "ignores loaded: N",
    "q-0397",
)
SPEC_FACTS = (
    "NOT IMPLEMENTED",
    "parsed, validated and counted",
    "q-0397",
)
MODULE_FACTS = (
    "parse + validate + count",
    "no run calls it on its results",
    "q-0397",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_ci_page_does_not_claim_a_failure_is_reported_as_ignored() -> None:
    lowered = _text(CI_DOC).lower()
    found = [phrase for phrase in REPORTING_CLAIMS if phrase.lower() in lowered]
    assert found == [], f"docs/ci.md still promises ignore reporting: {found}"


def test_the_ci_page_states_what_happens() -> None:
    """Presence, not just absence: the banner is qualified and the facts are stated."""
    text = _text(CI_DOC)
    missing = [fact for fact in CI_FACTS if fact not in text]
    assert missing == [], f"docs/ci.md no longer states: {missing}"


def test_the_ci_page_keeps_the_design_reason() -> None:
    text = _text(CI_DOC)
    assert "anti-rug" in text
    assert "reason" in text and "required" in text


def test_the_architecture_row_is_present_and_correct() -> None:
    """Absence-only passed on a deleted row; the corrected row must exist."""
    text = _text(ARCHITECTURE)
    for phrase in ("instead of real failures", "lands in Phase 7b"):
        assert phrase not in text, f"docs/ARCHITECTURE.md still says {phrase!r}"
    missing = [fact for fact in ARCHITECTURE_FACTS if fact not in text]
    assert missing == [], f"docs/ARCHITECTURE.md lost the corrected ci_ignore row: {missing}"


def test_the_spec_row_is_marked_not_implemented() -> None:
    text = _text(SPEC)
    missing = [fact for fact in SPEC_FACTS if fact not in text]
    assert missing == [], f"the Phase 7 spec row lost its status note: {missing}"


def test_the_module_docstring_says_what_runs() -> None:
    text = _text(MODULE)
    missing = [fact for fact in MODULE_FACTS if fact not in text]
    assert missing == [], f"src/ci_ignore.py docstring lost: {missing}"
    assert "reports them as" not in text.lower(), "the module still promises reporting"


def test_the_report_invites_recording_and_never_a_mute() -> None:
    """t-1362: the generated report must not promise that an ignore silences a failure."""
    text = _text(REPORT)
    assert "as known-benign)" not in text, "action/report.py still invites an ignore as a mute"
    assert "not a mute" in text, "action/report.py must say an ignore is a record, not a mute"
    assert "matching against failures is not implemented" in text
