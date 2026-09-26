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
  3. verification strength is classified on its merits (golden / subject /
     page / unverified) instead of "did it use the golden's selector";
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
    _is_global_container,
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
            test_file: Path, pytest_timeout: float = 120.0
        ) -> tuple[int, int, int, int, float, str, dict[str, str]]:
            return (1, 1, 0, 0, 1.0, "=== 1 passed in 1.0s ===\n", {})

        monkeypatch.setattr(eval_runner, "run_generated_tests", fake_run)
        results = run_full_validation(tmp_path, {"eval-995": code}, test_files={"eval-995": test_file})
        assert results[0].tests_false_positive == 1


class TestVerificationClassification:
    @staticmethod
    def _ph(desc: str, kind: str, expected_page: str = "") -> dict[str, Any]:
        return {
            "action": "ASSERT",
            "description": desc,
            "expected_locator": "#golden",
            "tolerance_selectors": [],
            "expected_page": expected_page,
            "criterion_kind": kind,
        }

    def test_global_container_can_never_verify(self) -> None:
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": 'main:has-text("na")'}]
        assert _classify_verification(pool, self._ph("account balances", "element"), "element", False) == "unverified"

    def test_wrong_element_on_right_page_is_unverified(self) -> None:
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#place-order"}]
        assert (
            _classify_verification(pool, self._ph("order success message", "element"), "element", False) == "unverified"
        )

    def test_distinctive_element_verifies_content(self) -> None:
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#remove-sauce-labs-backpack"}]
        assert _classify_verification(pool, self._ph("backpack item in cart", "element"), "element", False) == "subject"

    def test_url_assertion_verifies_only_a_page_criterion(self) -> None:
        pool = [
            {
                "method": "to_have_url",
                "action": "ASSERT",
                "locator": 'expect(page).to_have_url("https://x.com/inventory.html")',
            }
        ]
        ph = self._ph("product list", "page", expected_page="https://x.com/inventory.html")
        assert _classify_verification(pool, ph, "page", False) == "page"
        # ...but not a content criterion.
        assert _classify_verification(pool, self._ph("product list", "element"), "element", False) == "unverified"

    def test_global_container_detection(self) -> None:
        assert _is_global_container("main")
        assert _is_global_container("#content")
        assert not _is_global_container("#cart_contents_container")

    def test_error_element_never_verifies_a_success_criterion(self) -> None:
        """Found live on banking_mock: ``#transfer-error`` shares "transfer"
        with "transfer success message" but is the opposite outcome."""
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#transfer-error"}]
        ph = {
            "action": "ASSERT",
            "description": "transfer success message",
            "expected_locator": "#transfer-success-title",
            "tolerance_selectors": [],
            "expected_page": "",
            "criterion_kind": "element",
        }
        assert _classify_verification(pool, ph, "element", False) == "unverified"


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
        result = validate_story(code, golden)
        assert result.resolutions[0].matched is False  # gate 1 strict
        assert result.resolutions[0].verification == "page"  # gate 2 fair
