"""Tests for golden_validator.py — code parsing and golden key validation."""

import json
import tempfile
from pathlib import Path

import pytest
from golden_validator import (
    _action_from_method,
    _build_golden_lookup,
    extract_locators_from_code,
    extract_skipped_descriptions,
    extract_test_function_count,
    load_golden_key,
    validate_dataset,
    validate_story,
)

# ---------------------------------------------------------------------------
# _action_from_method
# ---------------------------------------------------------------------------


class TestActionFromMethod:
    def test_navigate(self) -> None:
        assert _action_from_method("navigate") == "GOTO"

    def test_fill(self) -> None:
        assert _action_from_method("fill") == "FILL"

    def test_click(self) -> None:
        assert _action_from_method("click") == "CLICK"

    def test_assert_visible(self) -> None:
        assert _action_from_method("assert_visible") == "ASSERT"

    def test_assert_text(self) -> None:
        assert _action_from_method("assert_text") == "ASSERT"

    def test_assert_checked(self) -> None:
        assert _action_from_method("assert_checked") == "ASSERT"

    def test_assert_count(self) -> None:
        assert _action_from_method("assert_count") == "ASSERT"


# ---------------------------------------------------------------------------
# extract_locators_from_code
# ---------------------------------------------------------------------------


class TestExtractLocators:
    def test_basic_fill(self) -> None:
        code = "evidence_tracker.fill('#user-name', 'value')"
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        assert locs[0]["action"] == "FILL"
        assert locs[0]["locator"] == "#user-name"

    def test_click(self) -> None:
        code = "evidence_tracker.click('#login-button', label='Login')"
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        assert locs[0]["action"] == "CLICK"
        assert locs[0]["locator"] == "#login-button"

    def test_assert_visible(self) -> None:
        code = "evidence_tracker.assert_visible('.modal-body', label='confirm')"
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        assert locs[0]["action"] == "ASSERT"
        assert locs[0]["locator"] == ".modal-body"

    def test_double_quoted(self) -> None:
        code = """evidence_tracker.click('a[href="/products"]', label="Products")"""
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        assert locs[0]["locator"] == 'a[href="/products"]'

    def test_navigate_skipped(self) -> None:
        code = "evidence_tracker.navigate('https://example.com')"
        locs = extract_locators_from_code(code)
        assert len(locs) == 0

    def test_multiple_calls(self) -> None:
        code = (
            "evidence_tracker.fill('#user-name', 'std')\n"
            "evidence_tracker.fill('#password', 'secret')\n"
            "evidence_tracker.click('#login-button')\n"
        )
        locs = extract_locators_from_code(code)
        assert len(locs) == 3
        assert [item["locator"] for item in locs] == ["#user-name", "#password", "#login-button"]

    def test_assert_text(self) -> None:
        code = "evidence_tracker.assert_text('#heading', 'Welcome')"
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        assert locs[0]["action"] == "ASSERT"
        assert locs[0]["locator"] == "#heading"

    def test_assert_checked(self) -> None:
        code = "evidence_tracker.assert_checked('#gender-radio-1')"
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        assert locs[0]["action"] == "ASSERT"
        assert locs[0]["locator"] == "#gender-radio-1"

    def test_data_test_selector(self) -> None:
        code = 'evidence_tracker.click("#add-to-cart-sauce-labs-backpack", label="Add")'
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        assert locs[0]["locator"] == "#add-to-cart-sauce-labs-backpack"

    def test_has_text_selector(self) -> None:
        code = 'evidence_tracker.assert_visible("h3:has-text("JavaScript Alerts")")'
        locs = extract_locators_from_code(code)
        assert len(locs) == 1
        # The non-greedy .*? with back-ref stops at first matching quote
        assert locs[0]["locator"] == "h3:has-text("

    def test_empty_code(self) -> None:
        assert extract_locators_from_code("") == []


# ---------------------------------------------------------------------------
# extract_skipped_descriptions
# ---------------------------------------------------------------------------


class TestExtractSkipped:
    def test_single_skip(self) -> None:
        code = "pytest.skip(\"Skipping: unresolved placeholders for: 'Thank You page'\")"
        desc = extract_skipped_descriptions(code)
        assert len(desc) == 1
        assert desc[0] == "Thank You page"

    def test_no_skips(self) -> None:
        assert extract_skipped_descriptions("print('hello')") == []


# ---------------------------------------------------------------------------
# extract_test_function_count
# ---------------------------------------------------------------------------


class TestExtractTestCount:
    def test_single_test(self) -> None:
        code = "def test_01_login(page: Page):"
        assert extract_test_function_count(code) == 1

    def test_multiple_tests(self) -> None:
        code = "def test_01_login(page: Page):\n    pass\ndef test_02_add_cart(page: Page):\n    pass\n"
        assert extract_test_function_count(code) == 2

    def test_no_tests(self) -> None:
        assert extract_test_function_count("print('hello')") == 0

    def test_ignores_non_test_functions(self) -> None:
        code = "def helper():\n    pass\n\ndef test_01_foo(page: Page):"
        assert extract_test_function_count(code) == 1


# ---------------------------------------------------------------------------
# load_golden_key
# ---------------------------------------------------------------------------


class TestLoadGoldenKey:
    def test_valid_key(self) -> None:
        data = {
            "id": "eval-001",
            "site": "test",
            "base_url": "https://example.com",
            "conditions": ["1. Do something"],
            "golden_resolutions": [],
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)
        try:
            result = load_golden_key(path)
            assert result["id"] == "eval-001"
        finally:
            path.unlink()

    def test_missing_keys(self) -> None:
        data = {"id": "eval-001"}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="missing keys"):
                load_golden_key(path)
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# _build_golden_lookup
# ---------------------------------------------------------------------------


class TestBuildGoldenLookup:
    def test_flat_list(self) -> None:
        golden = {
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {"action": "FILL", "description": "x", "expected_locator": "#a", "tolerance_selectors": []},
                        {
                            "action": "CLICK",
                            "description": "y",
                            "expected_locator": "#b",
                            "tolerance_selectors": ["#b2"],
                        },
                    ],
                },
                {
                    "criterion_index": 1,
                    "placeholders": [
                        {"action": "ASSERT", "description": "z", "expected_locator": "#c", "tolerance_selectors": []},
                    ],
                },
            ],
        }
        flat = _build_golden_lookup(golden)
        assert len(flat) == 3
        assert flat[0]["action"] == "FILL"
        assert flat[1]["tolerance_selectors"] == ["#b2"]
        assert flat[2]["criterion_index"] == 1


# ---------------------------------------------------------------------------
# validate_story
# ---------------------------------------------------------------------------


class TestValidateStory:
    def test_perfect_match(self) -> None:
        code = "evidence_tracker.fill('#user-name', 'std')\nevidence_tracker.click('#login-button')\n"
        golden = {
            "id": "s1",
            "site": "test",
            "conditions": ["1. Login"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "FILL",
                            "description": "u",
                            "expected_locator": "#user-name",
                            "tolerance_selectors": [],
                        },
                        {
                            "action": "CLICK",
                            "description": "b",
                            "expected_locator": "#login-button",
                            "tolerance_selectors": [],
                        },
                    ],
                },
            ],
        }
        result = validate_story(code, golden)
        assert len(result.resolutions) == 2
        assert all(r.matched for r in result.resolutions)

    def test_tolerance_match(self) -> None:
        code = "evidence_tracker.fill('input[name=\"user-name\"]', 'std')"
        golden = {
            "id": "s1",
            "site": "test",
            "conditions": ["1. Login"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "FILL",
                            "description": "u",
                            "expected_locator": "#user-name",
                            "tolerance_selectors": ['input[name="user-name"]'],
                        },
                    ],
                },
            ],
        }
        result = validate_story(code, golden)
        assert result.resolutions[0].matched is True

    def test_wrong_locator(self) -> None:
        code = "evidence_tracker.fill('#wrong', 'std')"
        golden = {
            "id": "s1",
            "site": "test",
            "conditions": ["1. Login"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "FILL",
                            "description": "u",
                            "expected_locator": "#user-name",
                            "tolerance_selectors": [],
                        },
                    ],
                },
            ],
        }
        result = validate_story(code, golden)
        assert result.resolutions[0].matched is False

    def test_unresolved_skip(self) -> None:
        code = "pytest.skip('unresolved')"
        golden = {
            "id": "s1",
            "site": "test",
            "conditions": ["1. Login"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "FILL",
                            "description": "u",
                            "expected_locator": "#user-name",
                            "tolerance_selectors": [],
                        },
                    ],
                },
            ],
        }
        result = validate_story(code, golden)
        assert result.resolutions[0].generated_locator is None
        assert result.resolutions[0].matched is False


# ---------------------------------------------------------------------------
# validate_dataset
# ---------------------------------------------------------------------------


class TestValidateDataset:
    def test_missing_code_in_map(self, tmp_path: Path) -> None:
        golden = {
            "id": "eval-099",
            "site": "test",
            "base_url": "https://x.com",
            "conditions": ["1. Do X"],
            "golden_resolutions": [],
        }
        (tmp_path / "eval-099.json").write_text(json.dumps(golden))
        results = validate_dataset(tmp_path, {})
        assert len(results) == 1
        assert results[0].story_id == "eval-099"
        assert results[0].criteria_with_skeletons == 0
