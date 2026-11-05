"""d-0154: a non-permissive licence must not enter without a recorded election.

``docs/licenses/DEPENDENCIES.md`` is regenerated from ``uv.lock`` by
``scripts/maintenance/licence_record.py``, so a new copyleft dependency re-appears
in its "Flagged" table on the next refresh. What the generator does NOT do is
decide which licence option TanCat relies on. The "Elections" section is that
decision, and this test fails when a flagged package has no row there - so the
next copyleft arrival cannot pass as an oversight, and the election cannot be
deleted while the flag stays.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = REPO_ROOT / "docs" / "licenses" / "DEPENDENCIES.md"
NOTICE = REPO_ROOT / "NOTICE"

#: A flagged licence that needs a decision, not only a note.
COPYLEFT_MARKERS = ("GPL", "MPL", "AGPL", "LGPL", "EUPL", "CDDL", "OSL")

#: The licence options this project may elect. Every entry is compatible with
#: shipping Apache-2.0 code, and each names the actual option relied on.
ALLOWED_ELECTIONS = {
    "Artistic-1.0",
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "MPL-2.0",
}

#: How the licences in the record's prose map to an SPDX-style name.
_LICENCE_ALIASES = {
    "artistic license": "Artistic-1.0",
    "artistic-1.0": "Artistic-1.0",
    "gnu general public license (gpl)": "GPL-2.0",
    "gnu general public license v2 or later (gplv2+)": "GPL-2.0-or-later",
    "gpl-2.0-or-later": "GPL-2.0-or-later",
    "gplv2+": "GPL-2.0-or-later",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "mpl-2.0": "MPL-2.0",
    "apache-2.0": "Apache-2.0",
    "mit": "MIT",
    "mit-cmu": "MIT-CMU",
}


def _normalise_licence(text: str) -> str:
    key = re.sub(r"\s+", " ", text.strip().lower())
    return _LICENCE_ALIASES.get(key, text.strip())


def _conjuncts(expression: str) -> list[list[str]]:
    """Licence obligations in *expression*: a list of options-sets, ANDed together.

    ``MPL-2.0 AND (Apache-2.0 OR MIT)`` is two obligations - MPL-2.0, and one of
    Apache/MIT - so an election that answers only one of them is not an election.
    A dual licence written with semicolons or a slash is ONE obligation with
    alternatives. Plain text is one obligation with one option.
    """
    text = expression.strip()
    if " AND " in text.upper():
        parts = re.split(r"\s+AND\s+", text, flags=re.IGNORECASE)
        return [
            [
                _normalise_licence(option)
                for option in re.split(r"\s+OR\s+", part.strip().strip("()"), flags=re.IGNORECASE)
            ]
            for part in parts
        ]
    alternatives = re.split(r"\s*;\s*|\s+/\s*", text)
    return [[_normalise_licence(option) for option in alternatives]]


def _elected_options(election: str) -> list[str]:
    """The licences an election row actually names, ' AND '-separated."""
    return [_normalise_licence(part) for part in re.split(r"\s+AND\s+", election.split(" (")[0].strip())]


def _record() -> str:
    return RECORD.read_text(encoding="utf-8")


def _flagged_rows() -> dict[str, str]:
    """package -> licence text, for every Flagged row that says FLAG.

    The table also carries "Note -" rows (permissive, recorded only because the
    metadata reads oddly); those need no election. A FLAG row is what the
    generator writes for a licence that is not permissive.
    """
    text = _record()
    start = text.index("## Flagged: non-permissive or unclear")
    end = text.index("\n## ", start + 10)
    rows: dict[str, str] = {}
    for line in text[start:end].splitlines():
        if not line.startswith("| ") or "---" in line or "Package |" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        package, licence, verdict = cells[0], cells[1], cells[2]
        if verdict.upper().startswith("FLAG"):
            rows[package] = licence
    return rows


def _elections() -> dict[str, dict[str, str]]:
    """package -> {elected, scope, why}, from the Elections table."""
    text = _record()
    assert "## Elections" in text, "the Elections section is gone - a flagged licence would have no record"
    start = text.index("## Elections")
    tail = text[start:]
    end = tail.find("\n## ", 10)
    section = tail if end == -1 else tail[:end]
    out: dict[str, dict[str, str]] = {}
    for line in section.splitlines():
        if not line.startswith("| ") or "---" in line or "Package |" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        out[cells[0]] = {"elected": cells[1], "scope": cells[2], "why": cells[3]}
    return out


def test_every_flagged_package_has_a_recorded_election() -> None:
    flagged = _flagged_rows()
    assert flagged, "the Flagged table is empty - this test would pass on nothing"
    elections = _elections()

    missing = sorted(package for package in flagged if package not in elections)
    assert missing == [], (
        f"flagged licence(s) with no recorded election: {missing}. Add a row to the Elections "
        "section of docs/licenses/DEPENDENCIES.md naming the option relied on and its scope."
    )


def test_the_flagged_licences_are_still_the_copyleft_ones() -> None:
    """The list this test guards must not quietly lose its copyleft members."""
    flagged = _flagged_rows()
    copyleft = {
        package for package, licence in flagged.items() if any(marker in licence.upper() for marker in COPYLEFT_MARKERS)
    }
    assert "text-unidecode" in copyleft, "text-unidecode left the flagged table without a decision recorded"
    assert copyleft, "no copyleft licence found - the table or its markers changed"


def test_every_election_names_an_allowed_licence_and_a_scope() -> None:
    for package, election in _elections().items():
        assert election["elected"], f"{package}: no licence elected"
        # An AND expression elects every term; each named term must be an
        # allowed option. OR stays one choice between allowed options.
        elected = election["elected"].split(" (")[0].strip()
        options = [
            option.strip()
            for part in re.split(r"\s+AND\s+", elected, flags=re.IGNORECASE)
            for option in re.split(r"\s+OR\s+", part)
        ]
        unknown = [option for option in options if option not in ALLOWED_ELECTIONS]
        assert options and not unknown, (
            f"{package}: {unknown or elected!r} is not one of the recorded permissive options "
            f"{sorted(ALLOWED_ELECTIONS)}"
        )
        assert re.search(r"runtime|dev only", election["scope"], re.IGNORECASE), (
            f"{package}: scope '{election['scope']}' does not say whether it ships or is dev-only"
        )
        assert len(election["why"]) > 20, f"{package}: the election gives no reason"


def test_every_election_answers_the_licence_the_package_declares() -> None:
    """The election must satisfy the package's OWN expression, not an allow-list.

    ``MPL-2.0 AND (Apache-2.0 OR MIT)`` cannot be answered with "Apache-2.0 OR
    MIT": the MPL term is operative too. This is the check that would have caught
    the two wrong rows (orjson, tqdm) the first draft shipped.
    """
    flagged = _flagged_rows()
    elections = _elections()

    wrong: list[str] = []
    for package, expression in flagged.items():
        election = elections.get(package)
        if not election:
            continue  # the first test reports the missing row
        obligations = _conjuncts(expression)
        chosen = _elected_options(election["elected"])
        for options in obligations:
            satisfied = [option for option in chosen if option in options]
            if not satisfied:
                wrong.append(f"{package}: '{expression}' needs one of {options}, the row elects {chosen}")
                break
        extra = [option for option in chosen if not any(option in options for options in obligations)]
        if extra:
            wrong.append(f"{package}: the row elects {extra}, which the package's expression does not declare")

    assert wrong == [], "election(s) that do not answer the package's own licence: " + "; ".join(wrong)


def test_the_notice_carries_the_text_unidecode_election() -> None:
    """The election must travel with the distribution, not only the record."""
    notice = NOTICE.read_text(encoding="utf-8")
    assert "text-unidecode" in notice
    assert "Artistic-1.0" in notice
    assert "elects" in notice.lower()
    assert "default install" in notice.lower()
