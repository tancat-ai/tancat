"""t-1014: four answer keys accept page arrival for a "go to the page" step.

The owner's decision (2026-10-28): a story that says "the shopper goes to the
transfer page" is satisfied when the browser arrives at that page. It is not
required to also assert an element on it.

Four keys said otherwise. Every other criterion in the dataset whose wording is
"Navigate to the ... page" already holds an arrival assertion
(``expect(page).to_have_url(...)``, ``expected_type: url_assertion``) - eval-002
c0/c1/c4, eval-006 c0/c3, eval-007 c0, eval-008 c0, eval-010 c0. These four were
the exceptions, and each demanded an element instead:

    eval-001 c2  "3. Navigate to the shopping cart page"
    eval-001 c4  "5. Navigate to the checkout page"
    eval-003 c0  "1. Navigate to the demoqa.com practice form page"
    eval-004 c0  "1. Navigate to the the-internet.herokuapp.com main page"

The correction moves the arrival URL into ``expected_locator`` and keeps the old
element in ``tolerance_selectors``, so an element assertion still passes (it is
the stronger proof) and a capture that only asserts the element keeps scoring.

What must NOT change: an arrival at the wrong page still fails. The matcher
compares page identity (``src/page_identity.same_page``), not "some arrival
happened", so the 2026-10-24 draw - where the journey never left the inventory
page - still misses these criteria. A bare ``assert_visible('body')`` fails too.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

from golden_validator import (  # noqa: E402
    accepts_page_arrival,
    load_golden_key,
    validate_story,
)

# ``eval_harness`` is imported inside the test that needs it: it imports its
# sibling scripts by their bare names, and the repo's mypy hook (which checks
# tests/) then sees scripts/eval/eval_resolver.py under two module names and
# refuses to run. The dynamic import keeps the hook green and still exercises
# the real CLI entry point.

_DATASET = _EVAL_DIR / "dataset"

_KEYS = {
    "eval-001": _DATASET / "eval-001_saucedemo_login_checkout.json",
    "eval-003": _DATASET / "eval-003_demoqa_forms.json",
    "eval-004": _DATASET / "eval-004_theinternet_alerts.json",
}

# (story, criterion_index, description, arrival that passes, arrival that fails,
#  the element the key used to demand)
_CORRECTED: list[tuple[str, int, str, str, str, str]] = [
    (
        "eval-001",
        2,
        "Cart Summary",
        "https://www.saucedemo.com/cart.html",
        "https://www.saucedemo.com/inventory.html",
        "#cart_contents_container",
    ),
    (
        "eval-001",
        4,
        "Checkout Info form",
        "https://www.saucedemo.com/checkout-step-one.html",
        "https://www.saucedemo.com/cart.html",
        "#checkout_info_container",
    ),
    (
        "eval-003",
        0,
        "practice form page title",
        "https://demoqa.com/automation-practice-form",
        "https://demoqa.com/",
        'h5:has-text("Student Registration Form")',
    ),
    (
        "eval-004",
        0,
        "all elements listing",
        "https://the-internet.herokuapp.com",
        "https://the-internet.herokuapp.com/javascript_alerts",
        ".heading",
    ),
]


def _golden(story: str) -> dict[str, Any]:
    return load_golden_key(_KEYS[story])


def _assert_result(story: str, criterion_index: int, description: str, code: str) -> Any:
    """Match one emitted code sample against the story's real golden key."""
    result = validate_story(code=code, golden=_golden(story))
    matches = [
        r
        for r in result.resolutions
        if r.action == "ASSERT" and r.criterion_index == criterion_index and r.description == description
    ]
    assert len(matches) == 1, f"expected one {description!r} placeholder, got {len(matches)}"
    return matches[0]


def _arrival(url: str) -> str:
    return f'expect(page).to_have_url("{url}")'


def _placeholder(story: str, criterion_index: int, description: str) -> dict[str, Any]:
    for crit in _golden(story).get("golden_resolutions", []):
        if crit.get("criterion_index") != criterion_index:
            continue
        for ph in crit.get("placeholders", []):
            if ph.get("description") == description and ph.get("action") == "ASSERT":
                return ph
    raise AssertionError(f"{story} c{criterion_index} has no ASSERT placeholder {description!r}")


@pytest.mark.parametrize(("story", "crit", "desc", "good_url", "bad_url", "element"), _CORRECTED)
class TestArrivalSatisfiesTheKey:
    def test_arrival_at_the_page_passes(
        self, story: str, crit: int, desc: str, good_url: str, bad_url: str, element: str
    ) -> None:
        result = _assert_result(story, crit, desc, _arrival(good_url))

        assert result.matched is True
        assert result.generated_locator == _arrival(good_url)

    def test_arrival_at_the_wrong_page_still_fails(
        self, story: str, crit: int, desc: str, good_url: str, bad_url: str, element: str
    ) -> None:
        result = _assert_result(story, crit, desc, _arrival(bad_url))

        assert result.matched is False

    def test_the_old_element_still_passes(
        self, story: str, crit: int, desc: str, good_url: str, bad_url: str, element: str
    ) -> None:
        """An element assertion is the stronger proof and stays accepted."""
        result = _assert_result(story, crit, desc, f"evidence_tracker.assert_visible('{element}')")

        assert result.matched is True

    def test_a_bare_page_global_assertion_does_not_pass(
        self, story: str, crit: int, desc: str, good_url: str, bad_url: str, element: str
    ) -> None:
        """'It ran' is not evidence of the page."""
        result = _assert_result(story, crit, desc, "evidence_tracker.assert_visible('body')")

        assert result.matched is False


@pytest.mark.parametrize(("story", "crit", "desc", "good_url", "bad_url", "element"), _CORRECTED)
def test_the_key_is_an_arrival_key_with_the_element_as_a_tolerance(
    story: str, crit: int, desc: str, good_url: str, bad_url: str, element: str
) -> None:
    ph = _placeholder(story, crit, desc)

    assert ph.get("expected_type") == "url_assertion"
    assert ph["expected_locator"] == _arrival(good_url)
    assert ph.get("expected_page") == good_url
    assert element in ph.get("tolerance_selectors", [])


def test_every_navigate_to_page_criterion_now_accepts_arrival() -> None:
    """The four were the only 'Navigate to the ... page' keys without an arrival."""
    missing: list[str] = []
    for golden_file in sorted(_DATASET.glob("*.json")):
        golden = load_golden_key(golden_file)
        conditions = golden.get("conditions", [])
        for crit in golden.get("golden_resolutions", []):
            index = crit.get("criterion_index")
            wording = conditions[index] if isinstance(index, int) and index < len(conditions) else ""
            if crit.get("criterion_kind") != "page" or "navigate to" not in wording.lower():
                continue
            for ph in crit.get("placeholders", []):
                if ph.get("action") == "ASSERT" and not accepts_page_arrival(ph):
                    missing.append(f"{golden['id']} c{index}: {wording}")

    assert missing == []


def test_the_two_remaining_element_only_page_keys_are_named() -> None:
    """Not corrected here, and not hidden: the dataset check says so out loud.

    eval-001 c0 (the login step) and eval-004 c1 (the alert-link click) are page
    criteria keyed only to an element. They are outside this job's four, so the
    check names them in every ``dataset --validate`` run instead of leaving the
    reader to find them.
    """
    assert accepts_page_arrival(_placeholder("eval-001", 0, "product list")) is False
    assert accepts_page_arrival(_placeholder("eval-004", 1, "alert demonstration header")) is False


def test_the_dataset_check_warns_about_element_only_page_keys(capsys: pytest.CaptureFixture[str]) -> None:
    eval_harness = importlib.import_module("eval_harness")
    args = argparse.Namespace(validate=True)

    assert eval_harness._cmd_dataset(args) == 0  # noqa: SLF001 - the CLI entry point under test
    out = capsys.readouterr().out

    assert "eval-001_saucedemo_login_checkout.json: criterion 0 'product list'" in out
    assert "eval-004_theinternet_alerts.json: criterion 1 'alert demonstration header'" in out
    # The corrected four must not be named.
    assert "criterion 2 'Cart Summary'" not in out
    assert "criterion 4 'Checkout Info form'" not in out
    assert "eval-003_demoqa_forms.json: criterion 0" not in out
    assert "eval-004_theinternet_alerts.json: criterion 0" not in out


def test_accepts_page_arrival_reads_the_key_shape() -> None:
    assert accepts_page_arrival({"expected_locator": 'expect(page).to_have_url("https://x/y")'}) is True
    assert accepts_page_arrival({"expected_locator": "https://x/y"}) is True
    assert (
        accepts_page_arrival(
            {"expected_locator": "#cart", "tolerance_selectors": ['expect(page).to_have_url("https://x/y")']}
        )
        is True
    )
    assert accepts_page_arrival({"expected_locator": "#cart", "tolerance_selectors": [".cart"]}) is False


def test_the_dataset_files_still_parse() -> None:
    for path in _KEYS.values():
        json.loads(path.read_text(encoding="utf-8"))
