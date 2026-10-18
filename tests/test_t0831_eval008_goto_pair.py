"""t-0831: the eval-008 GOTO pair resolves.

The two eval-008 GOTO placeholders ("go to the transfer page", "navigate to
bill payments") reported ``target_never_captured`` in every held-out run
(2026-10-12 through 2026-10-16, committed fixtures) even though the product
resolved both to the right URLs: the generated tests reach the pages via
journey clicks and assert arrival with ``expect(page).to_have_url(...)``.

The defect was in the harness, not the product. The golden validator's
locator extractor skipped every ``evidence_tracker.navigate(...)`` call and
tagged every ``to_have_url(...)`` assertion as ASSERT, while matching
requires an exact action equality - so a GOTO golden (a bare URL) had an
empty candidate pool and was structurally unmatchable in every run, worth a
permanent -2/113 on gate 1 and a misattributed ``target_never_captured``
class.

Fix (scripts/eval/golden_validator.py): ``navigate(url)`` is extracted as a
GOTO locator; each ``to_have_url(url)`` assertion is extracted as both an
ASSERT (page-arrival goldens, unchanged) and a GOTO locator (the emitted
form of a resolved GOTO); and the URL comparison branch reduces bare-URL
goldens and assertion expressions to their URL before comparing
(trailing-slash-insensitive, as before).

Tests 4-5 re-score committed held-out evidence (no model, no browser): the
2026-10-16 run's GOTO pair now resolves (87/113 -> 89/113, both were
resolvable in that run), and the 2026-10-13 run's transfer GOTO - which had
no arrival evidence in that draw - stays an honest miss (94/113 -> 95/113).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import rescore  # noqa: E402
from golden_validator import (  # noqa: E402
    _locators_match,
    extract_locators_from_code,
)

_DATASET = _EVAL_DIR / "dataset"
_RUNS = _REPO_ROOT / "fixtures" / "heldout_runs"

_GOTO_GOLDEN: dict[str, Any] = {
    "action": "GOTO",
    "description": "go to the transfer page",
    "expected_locator": "http://localhost:8781/transfer.html",
    "tolerance_selectors": ["http://localhost:8781/transfer.html"],
}


class TestGotoExtraction:
    def test_navigate_is_extracted_as_goto(self) -> None:
        code = "evidence_tracker.navigate('http://localhost:8781/transfer.html')"
        locs = extract_locators_from_code(code)

        assert len(locs) == 1
        assert locs[0]["action"] == "GOTO"
        assert locs[0]["locator"] == "http://localhost:8781/transfer.html"

    def test_to_have_url_is_extracted_as_assert_and_goto(self) -> None:
        code = 'expect(page).to_have_url("http://localhost:8781/payments.html")'
        locs = extract_locators_from_code(code)

        assert [(item["action"], item["locator"]) for item in locs] == [
            ("ASSERT", 'expect(page).to_have_url("http://localhost:8781/payments.html")'),
            ("GOTO", 'expect(page).to_have_url("http://localhost:8781/payments.html")'),
        ]

    def test_other_actions_are_unchanged(self) -> None:
        code = (
            "evidence_tracker.navigate('http://localhost:8781/index.html')\n"
            "evidence_tracker.fill('#amount', '100')\n"
            "evidence_tracker.click('#transfer-submit')\n"
        )
        locs = extract_locators_from_code(code)

        assert [(item["action"], item["locator"]) for item in locs] == [
            ("GOTO", "http://localhost:8781/index.html"),
            ("FILL", "#amount"),
            ("CLICK", "#transfer-submit"),
        ]


class TestGotoLocatorMatching:
    def test_bare_url_golden_matches_to_have_url_expression(self) -> None:
        generated = 'expect(page).to_have_url("http://localhost:8781/transfer.html")'
        assert _locators_match(generated, _GOTO_GOLDEN["expected_locator"], _GOTO_GOLDEN["tolerance_selectors"])

    def test_bare_url_golden_matches_navigate_url(self) -> None:
        generated = "http://localhost:8781/transfer.html"
        assert _locators_match(generated, _GOTO_GOLDEN["expected_locator"], _GOTO_GOLDEN["tolerance_selectors"])

    def test_trailing_slash_insensitive_for_urls(self) -> None:
        assert _locators_match(
            'expect(page).to_have_url("http://localhost:8781/transfer.html/")',
            _GOTO_GOLDEN["expected_locator"],
            _GOTO_GOLDEN["tolerance_selectors"],
        )

    def test_wrong_url_does_not_match(self) -> None:
        generated = 'expect(page).to_have_url("http://localhost:8781/index.html")'
        assert not _locators_match(generated, _GOTO_GOLDEN["expected_locator"], _GOTO_GOLDEN["tolerance_selectors"])

    def test_element_golden_does_not_match_url_assertion(self) -> None:
        generated = 'expect(page).to_have_url("http://localhost:8781/transfer.html")'
        assert not _locators_match(generated, "#transfer-success-title", [])


def _eval008_gotos(run: Path) -> dict[str, tuple[bool, str | None]]:
    report = rescore.rescore(run, _DATASET)
    story = next(s for s in report.stories if s.story_id == "eval-008")
    return {r.description: (r.matched, r.generated_locator) for r in story.resolutions if r.action == "GOTO"}


class TestGotoPairOnCommittedEvidence:
    """The 'test that says it passed': both GOTO steps resolve on the committed
    2026-10-16 held-out evidence, with no model and no browser."""

    def test_both_goto_steps_resolve_on_2026_10_16(self) -> None:
        gotos = _eval008_gotos(_RUNS / "2026-10-16")

        assert gotos["go to the transfer page"][0] is True
        assert gotos["go to the transfer page"][1] == 'expect(page).to_have_url("http://localhost:8781/transfer.html")'
        assert gotos["navigate to bill payments"][0] is True
        assert (
            gotos["navigate to bill payments"][1] == 'expect(page).to_have_url("http://localhost:8781/payments.html")'
        )

    def test_2026_10_16_rescores_to_89(self) -> None:
        report = rescore.rescore(_RUNS / "2026-10-16", _DATASET)

        # 87 under the pre-fix validator; the +2 is the GOTO pair (both were
        # resolvable in that run). Gate 2 is unaffected (ASSERT-only rule).
        assert (report.correct_resolutions, report.total_placeholders) == (89, 113)
        assert report.total_false_positives == 0

    def test_goto_without_arrival_evidence_stays_a_miss(self) -> None:
        """The 2026-10-13 draw emitted no arrival assertion for the transfer
        page (the criterion's test was absent) - the fixed validator must
        credit only the payments GOTO, not both."""
        gotos = _eval008_gotos(_RUNS / "2026-10-13")
        report = rescore.rescore(_RUNS / "2026-10-13", _DATASET)

        assert gotos["go to the transfer page"][0] is False
        assert gotos["navigate to bill payments"][0] is True
        assert (report.correct_resolutions, report.total_placeholders) == (95, 113)
        assert report.total_false_positives == 0

    def test_dataset_has_no_goto_targeting_a_base_url(self) -> None:
        """Guard for the navigate-extraction semantics: no held-out GOTO golden
        may target the site's base URL (which the per-test setup navigate
        visits unconditionally), or the setup navigate would be creditable."""
        for golden_file in sorted(_DATASET.glob("*.json")):
            golden = json.loads(golden_file.read_text(encoding="utf-8"))
            base = str(golden.get("base_url", "")).rstrip("/")
            for c in golden.get("golden_resolutions", []):
                for p in c.get("placeholders", []):
                    if p["action"] not in ("GOTO", "URL"):
                        continue
                    assert str(p["expected_locator"]).rstrip("/") != base, golden_file.name
