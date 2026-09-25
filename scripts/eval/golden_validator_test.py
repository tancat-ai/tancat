"""Tests for golden_validator.py — code parsing and golden key validation."""

import json
import tempfile
from pathlib import Path

import pytest
from golden_validator import (
    _action_from_method,
    _build_golden_lookup,
    _classify_verification,
    _is_global_container,
    _match_generated_to_golden,
    _subject_tokens,
    extract_locators_from_code,
    extract_locators_per_test,
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

    def test_has_text_substring_tolerance(self) -> None:
        """AI-037 Phase 3: :has-text() needles match by substring (Playwright semantics).

        Resolver emits the full visible text (e.g. h2 with emoji prefix) while
        the golden tolerance carries a shorter needle. Both target the same
        element, so the validator must treat them as equivalent.
        """
        code = 'evidence_tracker.assert_visible(\'h2:has-text("✅ Quote Generated Successfully!")\', label="msg")'
        golden = {
            "id": "s1",
            "site": "test",
            "conditions": ["1. Confirm"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "ASSERT",
                            "description": "msg",
                            "expected_locator": "#quoteSuccess",
                            "tolerance_selectors": ["h2:has-text('Quote Generated')"],
                        },
                    ],
                },
            ],
        }
        result = validate_story(code, golden)
        assert result.resolutions[0].matched is True

    def test_has_text_substring_not_match_unrelated(self) -> None:
        """Substring equivalence must not fire for unrelated needles."""
        code = 'evidence_tracker.assert_visible(\'h2:has-text("Submit")\', label="msg")'
        golden = {
            "id": "s1",
            "site": "test",
            "conditions": ["1. Confirm"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "ASSERT",
                            "description": "msg",
                            "expected_locator": "#quoteSuccess",
                            "tolerance_selectors": ["h2:has-text('Quote Generated')"],
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


class TestValidateStoryVerification:
    def test_page_criterion_verified_by_url_but_gate1_stays_strict(self) -> None:
        """Gate 2 accepts the page form; gate 1 accuracy does not (it compares
        against the golden's own locator, unchanged)."""
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
        assert result.resolutions[0].matched is False  # gate 1 stays strict
        assert result.resolutions[0].verification == "page"  # gate 2 is fair

    def test_element_criterion_defaults_when_kind_absent(self) -> None:
        code = 'def test_01_a(page):\n    expect(page).to_have_url("https://x.com/cart.html")\n'
        golden = {
            "id": "s2",
            "site": "test",
            "conditions": ["1. A"],
            "golden_resolutions": [
                {
                    "criterion_index": 0,
                    "placeholders": [
                        {
                            "action": "ASSERT",
                            "description": "backpack item in cart",
                            "expected_locator": "#cart",
                            "tolerance_selectors": [],
                            "expected_page": "https://x.com/cart.html",
                        },
                    ],
                },
            ],
        }
        result = validate_story(code, golden)
        # No criterion_kind -> strict "element" reading, so a URL cannot verify it.
        assert result.resolutions[0].verification == "unverified"


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


# ---------------------------------------------------------------------------
# extract_locators_per_test  (gate 2 / B-093)
# ---------------------------------------------------------------------------


class TestExtractLocatorsPerTest:
    def test_returns_one_entry_per_function_in_order(self) -> None:
        code = (
            "def test_01_login(page):\n"
            "    evidence_tracker.fill('#user-name', 'std')\n"
            "def test_02_cart(page):\n"
            "    evidence_tracker.click('#cart-link')\n"
        )
        per_test = extract_locators_per_test(code)
        assert [name for name, _ in per_test] == ["test_01_login", "test_02_cart"]
        assert per_test[0][1][0]["locator"] == "#user-name"
        assert per_test[1][1][0]["locator"] == "#cart-link"

    def test_url_assert_is_an_assert_in_its_own_function(self) -> None:
        code = 'def test_01_load(page):\n    expect(page).to_have_url("http://x/home.html")\n'
        per_test = extract_locators_per_test(code)
        assert len(per_test) == 1
        assert per_test[0][1][0]["action"] == "ASSERT"
        assert "to_have_url" in per_test[0][1][0]["locator"]

    def test_empty_when_no_functions(self) -> None:
        assert extract_locators_per_test("no tests here") == []


# ---------------------------------------------------------------------------
# _match_generated_to_golden criterion scoping  (gate 2 / B-093)
# ---------------------------------------------------------------------------


def _ph(action: str, desc: str, expected: str, criterion_index: int = 0, tol: list[str] | None = None):
    return {
        "criterion_index": criterion_index,
        "action": action,
        "description": desc,
        "expected_locator": expected,
        "tolerance_selectors": tol or [],
    }


class TestGlobalContainerDetection:
    def test_global_containers_are_rejected(self) -> None:
        for loc in ("body", "html", "main", "#content", "#root", "#app"):
            assert _is_global_container(loc), loc

    def test_has_text_on_a_global_container_is_rejected(self) -> None:
        assert _is_global_container('main:has-text("Your Accounts Welcome back")')

    def test_page_specific_elements_are_allowed(self) -> None:
        for loc in ("#cart_contents_container", ".account_balance", "#success-title", "h3"):
            assert not _is_global_container(loc), loc


class TestSubjectTokens:
    def test_distinctive_word_survives(self) -> None:
        assert _subject_tokens("backpack item in cart") == {"backpack"}

    def test_generic_criterion_words_are_dropped(self) -> None:
        # "order" is < 6 chars and "success"/"message" are noise — this is why
        # ``#place-order`` must NOT be accepted for "order success message".
        assert _subject_tokens("order success message") == set()

    def test_long_stopwords_are_dropped(self) -> None:
        assert _subject_tokens("confirmation message displayed") == set()


class TestClassifyVerification:
    def _ph(self, desc: str, kind: str, expected_page: str = "") -> dict[str, object]:
        return {
            "action": "ASSERT",
            "description": desc,
            "expected_locator": "#golden",
            "tolerance_selectors": [],
            "expected_page": expected_page,
            "criterion_kind": kind,
        }

    def test_golden_match_wins(self) -> None:
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#golden"}]
        assert _classify_verification(pool, self._ph("x", "element"), "element", True) == "golden"

    def test_page_criterion_accepts_url_assertion_on_expected_page(self) -> None:
        pool = [
            {
                "method": "to_have_url",
                "action": "ASSERT",
                "locator": 'expect(page).to_have_url("https://x.com/inventory.html")',
            }
        ]
        ph = self._ph("product list", "page", expected_page="https://x.com/inventory.html")
        assert _classify_verification(pool, ph, "page", False) == "page"

    def test_page_criterion_rejects_url_assertion_on_another_page(self) -> None:
        pool = [
            {
                "method": "to_have_url",
                "action": "ASSERT",
                "locator": 'expect(page).to_have_url("https://x.com/payments.html")',
            }
        ]
        ph = self._ph("accounts dashboard loaded", "page", expected_page="https://x.com/dashboard.html")
        assert _classify_verification(pool, ph, "page", False) == "unverified"

    def test_element_criterion_is_not_verified_by_a_url_assertion(self) -> None:
        pool = [
            {
                "method": "to_have_url",
                "action": "ASSERT",
                "locator": 'expect(page).to_have_url("https://x.com/cart.html")',
            }
        ]
        ph = self._ph("backpack item in cart", "element", expected_page="https://x.com/cart.html")
        assert _classify_verification(pool, ph, "element", False) == "unverified"

    def test_distinctive_element_verifies_a_content_criterion(self) -> None:
        pool = [
            {
                "method": "assert_visible",
                "action": "ASSERT",
                "locator": "#remove-sauce-labs-backpack",
            }
        ]
        ph = self._ph("backpack item in cart", "element")
        assert _classify_verification(pool, ph, "element", False) == "subject"

    def test_wrong_element_on_the_right_page_stays_unverified(self) -> None:
        """The real false green: ``#place-order`` for "order success message"."""
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#place-order"}]
        ph = self._ph("order success message", "element")
        assert _classify_verification(pool, ph, "element", False) == "unverified"

    def test_global_container_never_verifies_even_with_matching_words(self) -> None:
        pool = [
            {
                "method": "assert_visible",
                "action": "ASSERT",
                "locator": 'main:has-text("Your Accounts ... current balances")',
            }
        ]
        ph = self._ph("account balances visible", "element")
        assert _classify_verification(pool, ph, "element", False) == "unverified"


class TestPolarityGuard:
    def _ph(self, desc: str, expected: str = "#golden") -> dict[str, object]:
        return {
            "action": "ASSERT",
            "description": desc,
            "expected_locator": expected,
            "tolerance_selectors": [],
            "expected_page": "",
            "criterion_kind": "element",
        }

    def test_error_element_does_not_verify_a_success_criterion(self) -> None:
        """Found live: ``#transfer-error`` shares "transfer" with "transfer
        success message" but is the OPPOSITE outcome (B-093)."""
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#transfer-error"}]
        ph = self._ph("transfer success message", "#transfer-success-title")
        assert _classify_verification(pool, ph, "element", False) == "unverified"

    def test_success_element_with_the_subject_word_verifies(self) -> None:
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#transfer-success-note"}]
        ph = self._ph("transfer success message", "#transfer-success-title")
        assert _classify_verification(pool, ph, "element", False) == "subject"

    def test_success_element_does_not_verify_an_error_criterion(self) -> None:
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#order-success"}]
        ph = self._ph("order error message", "#order-error")
        assert _classify_verification(pool, ph, "element", False) == "unverified"

    def test_no_polarity_words_means_no_constraint(self) -> None:
        pool = [{"method": "assert_visible", "action": "ASSERT", "locator": "#remove-sauce-labs-backpack"}]
        ph = self._ph("backpack item in cart", '[data-test="cart-list-container"]')
        assert _classify_verification(pool, ph, "element", False) == "subject"


class TestMatchCriterionScoping:
    def test_matching_locator_in_own_test_counts(self) -> None:
        generated = [{"method": "assert_visible", "action": "ASSERT", "locator": "#acct"}]
        per_test = [generated]
        res = _match_generated_to_golden(generated, [_ph("ASSERT", "balances", "#acct")], per_test)
        assert res[0].matched is True
        assert res[0].criterion_index == 0

    def test_matching_locator_in_wrong_test_counts_for_gate1_but_not_gate2(self) -> None:
        """Criterion 0's golden locator only appears in criterion 1's test.

        Gate 1 (resolver precision) is whole-file: the resolver DID pick the
        right element, so it counts. Gate 2 (verification) is per test: a
        check in another test proves nothing about this criterion.
        """
        t0 = [{"method": "assert_visible", "action": "ASSERT", "locator": "#other"}]
        t1 = [{"method": "assert_visible", "action": "ASSERT", "locator": "#acct"}]
        generated = t0 + t1
        per_test = [t0, t1]
        res = _match_generated_to_golden(generated, [_ph("ASSERT", "balances", "#acct")], per_test)
        assert res[0].matched is True  # gate 1: resolver found it
        assert res[0].verification == "unverified"  # gate 2: not in its own test

    def test_no_per_test_falls_back_to_whole_file(self) -> None:
        generated = [{"method": "assert_visible", "action": "ASSERT", "locator": "#acct"}]
        res = _match_generated_to_golden(generated, [_ph("ASSERT", "balances", "#acct")], None)
        assert res[0].matched is True

    def test_missing_criterion_function_falls_back_to_whole_file(self) -> None:
        # Only one test function exists but the placeholder is for criterion 2.
        t0 = [{"method": "assert_visible", "action": "ASSERT", "locator": "#acct"}]
        res = _match_generated_to_golden(t0, [_ph("ASSERT", "x", "#acct", criterion_index=2)], [t0])
        assert res[0].matched is True

    def test_first_non_match_wins_for_readable_reports(self) -> None:
        a = {"method": "assert_visible", "action": "ASSERT", "locator": "#a"}
        b = {"method": "assert_visible", "action": "ASSERT", "locator": "#b"}
        generated = [a, b]
        res = _match_generated_to_golden(generated, [_ph("ASSERT", "x", "#z")], [generated])
        assert res[0].matched is False
        assert res[0].generated_locator == "#a"
