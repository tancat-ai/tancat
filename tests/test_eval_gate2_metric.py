"""Gate-2 metric integrity (B-093) — CI-visible regression guards.

The harness's false-green metric silently reported ZERO for every run because
per-test outcomes were scraped from console output while pytest.ini enables
xdist (where the outcome prints BEFORE the node id). A clean-looking gate 2
from a broken parser is the worst possible failure mode: it certifies output
that was never checked.

These tests pin the invariants that failure taught us:
  1. per-test outcomes come from JUnit XML, not console text;
  2. an unparseable/missing map falls back to the CONSERVATIVE rule, never to
     "nothing to report";
  3. verification strength comes from the pipeline's own verdict (golden /
     subject / page / unverified) instead of a harness guess; a missing
     verdict is unverified with a reason, never a best-case assumption;
  4. gate 1 (resolver precision) and gate 2 (verification) are measured
     differently and must not be conflated.

The full suites live next to the code (scripts/eval/*_test.py); this file is
the subset that must fail CI if the metric breaks again.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import eval_runner  # noqa: E402
from eval_runner import _parse_junit_xml, _parse_per_test_results, run_full_validation  # noqa: E402
from golden_validator import (  # noqa: E402
    _classify_verification,
    _verification_reason,
    validate_story,
)


class TestPerTestOutcomes:
    def test_junit_xml_is_the_source(self, tmp_path: Path) -> None:
        xml = tmp_path / "results.xml"
        xml.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<testsuites><testsuite>"
            '<testcase name="test_01_login[chromium]" />'
            '<testcase name="test_02_cart[chromium]"><failure message="x">t</failure></testcase>'
            '<testcase name="test_03_skip[chromium]"><skipped message="unresolved" /></testcase>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        assert _parse_junit_xml(xml) == {
            "test_01_login": "PASSED",
            "test_02_cart": "FAILED",
            "test_03_skip": "SKIPPED",
        }

    def test_unreadable_xml_is_empty_not_a_pass(self, tmp_path: Path) -> None:
        assert _parse_junit_xml(tmp_path / "missing.xml") == {}

    def test_xdist_console_shape_outcome_precedes_node_id(self) -> None:
        out = "[gw0] [ 33%] PASSED test_eval.py::test_01_alpha[chromium] \n"
        assert _parse_per_test_results(out) == {"test_01_alpha": "PASSED"}

    def test_unknown_outcomes_never_certify_a_run_as_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No per-test map -> conservative story-level counting, not zero."""
        golden = {
            "id": "eval-995",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. A"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {"action": "ASSERT", "description": "a", "expected_locator": "#a", "tolerance_selectors": []},
                    ],
                },
            ],
        }
        (tmp_path / "eval-995.json").write_text(json.dumps(golden))
        test_file = tmp_path / "test_eval.py"
        test_file.write_text("")
        code = "def test_01_a(page):\n    evidence_tracker.assert_visible('#wrong', label='a')\n"

        def fake_run(
            test_file: Path, pytest_timeout: float = 120.0, **kwargs: object
        ) -> tuple[int, int, int, int, float, str, dict[str, str]]:
            return (1, 1, 0, 0, 1.0, "=== 1 passed in 1.0s ===\n", {})

        monkeypatch.setattr(eval_runner, "run_generated_tests", fake_run)
        results = run_full_validation(tmp_path, {"eval-995": code}, test_files={"eval-995": test_file})
        assert results[0].tests_false_positive == 1


class TestVerificationClassification:
    """B-100 part 3: the harness reads the pipeline verdict, it does not guess."""

    @staticmethod
    def _verdict(status: str, reason: str = "") -> dict[str, Any]:
        return {"status": status, "reason": reason}

    def test_verified_by_element_maps_to_subject(self) -> None:
        assert _classify_verification(False, self._verdict("verified_by_element")) == "subject"

    def test_verified_by_page_arrival_maps_to_page(self) -> None:
        assert _classify_verification(False, self._verdict("verified_by_page_arrival")) == "page"

    def test_unverified_verdict_stays_unverified(self) -> None:
        assert _classify_verification(False, self._verdict("unverified", "1 of 2 unresolved")) == "unverified"

    def test_missing_verdict_is_unverified_not_optimistic(self) -> None:
        """A missing verdict must never read as verified."""
        assert _classify_verification(False, None) == "unverified"
        assert _verification_reason(False, None)

    def test_golden_match_wins(self) -> None:
        assert _classify_verification(True, None) == "golden"

    def test_reason_is_carried_through_for_unverified(self) -> None:
        assert _verification_reason(False, self._verdict("unverified", "why")) == "why"


class TestGateSeparation:
    def test_page_criterion_is_not_a_gate1_match(self) -> None:
        """Gate 2 accepts the page form; gate 1 stays strict against the golden."""
        code = 'def test_01_login(page):\n    expect(page).to_have_url("https://x.com/inventory.html")\n'
        golden = {
            "id": "s1",
            "site": "test",
            "conditions": ["1. Log in"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "criterion_kind": "page",
                    "placeholders": [
                        {
                            "action": "ASSERT",
                            "description": "product list",
                            "expected_locator": '[data-test="inventory-item"]',
                            "tolerance_selectors": [],
                            "expected_page": "https://x.com/inventory.html",
                        },
                    ],
                },
            ],
        }
        result = validate_story(code, golden, verdicts=[{"status": "verified_by_page_arrival"}])
        assert result.resolutions[0].matched is False  # gate 1 strict
        assert result.resolutions[0].verification == "page"  # gate 2 reads the verdict


# ---------------------------------------------------------------------------
# t-1179 / d-0090: gate 2 must not take the whole-file match as proof
# ---------------------------------------------------------------------------

#: Two criteria. Criterion 1's golden is ``#golden``; the code below asserts it in
#: test_01 and asserts something else (#other) in test_02, which owns the criterion.
_HOLLOW_GOLDEN = {
    "id": "eval-997",
    "site": "test",
    "base_url": "https://example.com",
    "conditions": ["1. first thing", "2. second thing"],
    "golden_resolutions": [
        {
            "criterion_index": 0,
            "placeholders": [
                {
                    "action": "ASSERT",
                    "description": "first thing",
                    "expected_locator": "#first",
                    "tolerance_selectors": [],
                }
            ],
        },
        {
            "criterion_index": 1,
            "placeholders": [
                {
                    "action": "ASSERT",
                    "description": "second thing",
                    "expected_locator": "#golden",
                    "tolerance_selectors": [],
                }
            ],
        },
    ],
}

#: #golden appears in test_01, NOT in test_02 - the criterion's own test.
_HOLLOW_CODE = (
    "def test_01_a(page):\n"
    "    evidence_tracker.assert_visible('#first', label='first thing')\n"
    "    evidence_tracker.assert_visible('#golden', label='probe')\n"
    "\n\n"
    "def test_02_b(page):\n"
    "    evidence_tracker.assert_visible('#other', label='second thing')\n"
)

#: Same shape, but the criterion's own test does assert the golden.
_OWN_TEST_CODE = (
    "def test_01_a(page):\n"
    "    evidence_tracker.assert_visible('#first', label='first thing')\n"
    "\n\n"
    "def test_02_b(page):\n"
    "    evidence_tracker.assert_visible('#golden', label='second thing')\n"
)

#: A genuine miss: criterion 1's golden (#golden) is nowhere in the file, and its
#: own test asserted a different element - the shape that used to print #other as
#: if it were the resolved locator.
_MISS_CODE = (
    "def test_01_a(page):\n"
    "    evidence_tracker.assert_visible('#first', label='first thing')\n"
    "\n\n"
    "def test_02_b(page):\n"
    "    evidence_tracker.assert_visible('#other', label='second thing')\n"
)


class TestHollowPassIgnoresTheWholeFileMatch:
    """d-0090: ``r.matched`` is a whole-FILE fact and must not stand in for proof."""

    def test_a_hollow_assert_whose_golden_lives_in_another_test_is_counted(self) -> None:
        from eval_metrics import count_false_greens

        story = validate_story(_HOLLOW_CODE, _HOLLOW_GOLDEN)
        hollow = next(r for r in story.resolutions if r.criterion_index == 1)
        # The setup must really be the defect: the golden is in the file (so the
        # old shortcut skipped the row) but not in the criterion's own test.
        assert hollow.matched is True
        assert hollow.verification == "unverified"

        per_test = {"test_01_a": "PASSED", "test_02_b": "PASSED"}
        assert count_false_greens(story, _HOLLOW_CODE, per_test, passed=2) >= 1, (
            "a passed test that never asserted its own criterion's golden is a hollow pass"
        )

    def test_a_genuinely_verified_assertion_is_not_counted(self) -> None:
        from eval_metrics import count_false_greens

        story = validate_story(_OWN_TEST_CODE, _HOLLOW_GOLDEN)
        verified = next(r for r in story.resolutions if r.criterion_index == 1)
        assert verified.matched is True
        assert verified.verification == "golden"

        per_test = {"test_01_a": "PASSED", "test_02_b": "PASSED"}
        assert count_false_greens(story, _OWN_TEST_CODE, per_test, passed=2) == 0

    def test_a_failed_own_test_is_never_a_false_green(self) -> None:
        from eval_metrics import count_false_greens

        story = validate_story(_HOLLOW_CODE, _HOLLOW_GOLDEN)
        per_test = {"test_01_a": "PASSED", "test_02_b": "FAILED"}
        assert count_false_greens(story, _HOLLOW_CODE, per_test, passed=1) == 0


class TestAMissIsNotDisplayedAsAResolvedLocator:
    """t-1179: #dob and #quoteSubmit read as picks because the nearest candidate
    was printed in a column labelled "resolved". Display only - no scoring change."""

    def test_a_missed_placeholder_has_no_resolved_locator(self) -> None:
        from eval_criteria import MISS_WRONG_ELEMENT, criterion_rows

        story = validate_story(_MISS_CODE, _HOLLOW_GOLDEN)
        rows = criterion_rows(story, _MISS_CODE, {"test_01_a": "PASSED", "test_02_b": "PASSED"})
        miss = next(row for row in rows if row["criterion_index"] == 1)

        assert miss["matched"] == 0
        assert miss["resolved_locator"] is None, "a miss must not display a locator as resolved"
        # The diagnostic survives: what kind of miss it was is still recorded.
        assert miss["miss_class"] == MISS_WRONG_ELEMENT

    def test_a_matched_placeholder_keeps_its_resolved_locator(self) -> None:
        from eval_criteria import criterion_rows

        story = validate_story(_OWN_TEST_CODE, _HOLLOW_GOLDEN)
        rows = criterion_rows(story, _OWN_TEST_CODE, {"test_01_a": "PASSED", "test_02_b": "PASSED"})
        hit = next(row for row in rows if row["criterion_index"] == 1)

        assert hit["matched"] == 1
        assert hit["resolved_locator"] == "#golden"


# ---------------------------------------------------------------------------
# t-1183: gate 2 must not take the tool's word for what it verified
# ---------------------------------------------------------------------------

#: One page-kind criterion whose golden is a URL assertion.
_PAGE_GOLDEN = {
    "id": "eval-996",
    "site": "test",
    "base_url": "https://example.com",
    "conditions": ["1. cart page loaded"],
    "golden_resolutions": [
        {
            "criterion_index": 0,
            "criterion_kind": "page",
            "placeholders": [
                {
                    "action": "ASSERT",
                    "description": "cart page loaded",
                    "expected_locator": 'expect(page).to_have_url("https://example.com/cart")',
                    "tolerance_selectors": ["#cart"],
                }
            ],
        }
    ],
}

#: The criterion's own test asserts an ELEMENT, not the URL the key names, so the
#: row can only be as strong as the pipeline's own verdict.
_PAGE_CODE = "def test_01_a(page):\n    evidence_tracker.assert_visible('h1.title', label='cart page loaded')\n"


class TestGateTwoDoesNotTakeTheToolsWord:
    """t-1183 (owner, 2026-11-02: "2 go for truth"): a ``verified_by_element``
    verdict is not proof for gate 2 unless the element is the one the key names."""

    def test_a_subject_row_checked_against_another_element_is_counted(self) -> None:
        from eval_metrics import count_false_greens

        story = validate_story(
            _HOLLOW_CODE,
            _HOLLOW_GOLDEN,
            verdicts=[
                {"status": "verified_by_element", "checked": "#first"},
                {"status": "verified_by_element", "checked": "#other"},
            ],
        )
        row = next(r for r in story.resolutions if r.criterion_index == 1)

        # The product's own view is untouched: it still reads "subject".
        assert row.verification == "subject"
        # Gate 2 does not take that word: #other is not the golden.
        assert row.gate2_verified is False
        assert row.checked_element == "#other"
        per_test = {"test_01_a": "PASSED", "test_02_b": "PASSED"}
        assert count_false_greens(story, _HOLLOW_CODE, per_test, passed=2) == 1

    def test_a_subject_row_checked_against_the_golden_is_not_counted(self) -> None:
        from eval_metrics import count_false_greens

        story = validate_story(
            _HOLLOW_CODE,
            _HOLLOW_GOLDEN,
            verdicts=[
                {"status": "verified_by_element", "checked": "#first"},
                {"status": "verified_by_element", "checked": "#golden"},
            ],
        )
        row = next(r for r in story.resolutions if r.criterion_index == 1)

        assert row.verification == "subject"
        assert row.gate2_verified is True
        per_test = {"test_01_a": "PASSED", "test_02_b": "PASSED"}
        assert count_false_greens(story, _HOLLOW_CODE, per_test, passed=2) == 0

    def test_a_page_kind_url_assertion_is_not_counted(self) -> None:
        from eval_metrics import count_false_greens

        story = validate_story(
            _PAGE_CODE,
            _PAGE_GOLDEN,
            verdicts=[{"status": "verified_by_page_arrival", "checked": "# Page arrival check: cart"}],
        )
        row = story.resolutions[0]

        assert row.verification == "page"
        assert row.gate2_verified is True
        assert count_false_greens(story, _PAGE_CODE, {"test_01_a": "PASSED"}, passed=1) == 0

    def test_an_element_verdict_on_a_page_kind_criterion_is_counted(self) -> None:
        from eval_metrics import count_false_greens

        story = validate_story(
            _PAGE_CODE,
            _PAGE_GOLDEN,
            verdicts=[{"status": "verified_by_element", "checked": "h1.title"}],
        )
        row = story.resolutions[0]

        assert row.verification == "subject"
        assert row.gate2_verified is False
        assert count_false_greens(story, _PAGE_CODE, {"test_01_a": "PASSED"}, passed=1) == 1
