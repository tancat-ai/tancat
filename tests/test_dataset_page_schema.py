"""The two-page schema (t-1303 step 1, d-0149).

One field, `expected_page`, carried two facts and each consumer read it the other
way: the resolver treated it as the page holding the element, and the arrival
check treated it as the page the step must reach (t-1303 section 0). The split is
`target_page` (what the step selects on) and `outcome_page` (what it must reach).

These tests pin the static half of the split:

* every committed golden passes the schema;
* each way of breaking it is refused, and the message names the story, the
  criterion and the placeholder - never just "invalid file".

The live half (the locator really is on the target page, the outcome page really
is reachable) needs a browser and belongs to the revalidator, not here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from golden_validator import check_page_schema  # noqa: E402

DATASET = _EVAL_DIR / "dataset"
_BASE = "http://localhost:8781"


def _golden(*placeholders: dict, kind: str = "element") -> dict:
    return {
        "id": "eval-900",
        "site": "test",
        "base_url": f"{_BASE}/index.html",
        "conditions": ["1. Do X"],
        "golden_resolutions": [{"criterion_index": 0, "criterion_kind": kind, "placeholders": list(placeholders)}],
    }


def _problems(*placeholders: dict, kind: str = "element") -> list[str]:
    return check_page_schema(_golden(*placeholders, kind=kind))


class TestTheCommittedDataset:
    def test_every_golden_file_passes_the_schema(self) -> None:
        files = sorted(DATASET.glob("*.json"))
        assert len(files) == 9
        problems: list[str] = []
        placeholders = 0
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            placeholders += sum(len(c.get("placeholders", [])) for c in data.get("golden_resolutions", []))
            problems.extend(f"{path.name}: {problem}" for problem in check_page_schema(data))
        # 114 placeholders - the count the 2026-11-04 legs scored.
        assert placeholders == 114
        assert problems == []

    def test_no_golden_still_carries_the_retired_field(self) -> None:
        for path in sorted(DATASET.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            assert '"expected_page"' not in text, f"{path.name} still carries expected_page"


class TestEachRuleFailsByName:
    def test_the_retired_field_is_named(self) -> None:
        problems = _problems(
            {"action": "CLICK", "description": "Sign in", "expected_locator": "#go", "expected_page": _BASE}
        )
        assert "eval-900 c0 Sign in" in problems[0]
        assert "retired field 'expected_page'" in problems[0]

    def test_a_missing_outcome_page_is_named(self) -> None:
        problems = _problems(
            {"action": "CLICK", "description": "Sign in", "expected_locator": "#go", "target_page": _BASE}
        )
        assert problems and "missing outcome_page" in problems[0]
        assert "eval-900 c0 Sign in" in problems[0]

    def test_a_goto_may_not_carry_a_target(self) -> None:
        problems = _problems(
            {
                "action": "GOTO",
                "description": "go to the transfer page",
                "expected_locator": f"{_BASE}/transfer.html",
                "target_page": f"{_BASE}/dashboard.html",
                "outcome_page": f"{_BASE}/transfer.html",
            }
        )
        assert problems and "target_page must be empty" in problems[0]
        assert "go to the transfer page" in problems[0]

    def test_a_goto_outcome_must_be_the_url_its_locator_names(self) -> None:
        problems = _problems(
            {
                "action": "GOTO",
                "description": "go to the transfer page",
                "expected_locator": f"{_BASE}/transfer.html",
                "target_page": "",
                "outcome_page": f"{_BASE}/dashboard.html",
            }
        )
        assert problems and "not the URL its locator names" in problems[0]

    def test_a_click_needs_a_target_page(self) -> None:
        problems = _problems(
            {
                "action": "CLICK",
                "description": "Add to cart",
                "expected_locator": "#add",
                "target_page": "",
                "outcome_page": "",
            }
        )
        assert problems and "target_page is required" in problems[0]

    def test_a_page_kind_assert_needs_an_outcome_page(self) -> None:
        problems = _problems(
            {
                "action": "ASSERT",
                "description": "order confirmation shown",
                "expected_locator": ".confirmation",
                "target_page": f"{_BASE}/success.html",
                "outcome_page": "",
            },
            kind="page",
        )
        assert problems and "a page-kind ASSERT is proved by arriving" in problems[0]

    def test_a_url_assertion_may_not_carry_a_target(self) -> None:
        problems = _problems(
            {
                "action": "ASSERT",
                "description": "cart page loaded",
                "expected_locator": f'expect(page).to_have_url("{_BASE}/cart.html")',
                "target_page": f"{_BASE}/cart.html",
                "outcome_page": f"{_BASE}/cart.html",
                "expected_type": "url_assertion",
            },
            kind="page",
        )
        assert problems and "target_page must be empty" in problems[0]


class TestTheValidShapesPass:
    def test_a_click_with_a_target_and_no_outcome_is_valid(self) -> None:
        assert (
            _problems(
                {
                    "action": "CLICK",
                    "description": "Add to cart",
                    "expected_locator": "#add",
                    "target_page": f"{_BASE}/inventory.html",
                    "outcome_page": "",
                }
            )
            == []
        )

    def test_a_goto_with_only_its_outcome_is_valid(self) -> None:
        assert (
            _problems(
                {
                    "action": "GOTO",
                    "description": "go to the transfer page",
                    "expected_locator": f"{_BASE}/transfer.html",
                    "target_page": "",
                    "outcome_page": f"{_BASE}/transfer.html",
                }
            )
            == []
        )

    def test_an_element_assert_may_repeat_its_page_as_the_outcome(self) -> None:
        assert (
            _problems(
                {
                    "action": "ASSERT",
                    "description": "balances visible",
                    "expected_locator": ".balance",
                    "target_page": f"{_BASE}/dashboard.html",
                    "outcome_page": f"{_BASE}/dashboard.html",
                }
            )
            == []
        )
