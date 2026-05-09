"""Unit tests for src/prerequisite_injector.py"""

from __future__ import annotations

from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.prerequisite_injector import (
    InjectionPlan,
    PrerequisiteInjector,
    PrerequisiteStep,
)

# -- Helpers to build test fixtures --


def _placeholder(action: str, description: str, line_number: int = 1) -> PlaceholderUse:
    token = f"{{{{{action}:{description}}}}}"
    return PlaceholderUse(
        action=action,
        description=description,
        token=token,
        line_number=line_number,
        raw_line=token,
    )


def _step(raw_line: str, placeholders: list[PlaceholderUse] | None = None, line_number: int = 1) -> TestStep:
    return TestStep(
        line_number=line_number,
        raw_line=raw_line,
        placeholders=placeholders or [],
    )


def _journey(
    test_name: str,
    steps: list[TestStep],
    start_line: int = 1,
    end_line: int = 10,
) -> TestJourney:
    return TestJourney(
        test_name=test_name,
        start_line=start_line,
        end_line=end_line,
        steps=steps,
    )


# -- Tests: analyze_dependencies --


class TestAnalyzeDependencies:
    """Tests for PrerequisiteInjector.analyze_dependencies()"""

    def test_returns_empty_when_no_journeys(self) -> None:
        injector = PrerequisiteInjector()
        plans = injector.analyze_dependencies(
            journeys=[],
            starting_url="https://www.saucedemo.com",
        )
        assert plans == {}

    def test_returns_empty_when_no_starting_url(self) -> None:
        injector = PrerequisiteInjector()
        auth_journey = _journey(
            test_name="test_01_login",
            steps=[
                _step(
                    "    {{FILL:username:standard_user}}",
                    [_placeholder("FILL", "username", 2)],
                    line_number=2,
                ),
                _step(
                    "    {{FILL:password:secret_sauce}}",
                    [_placeholder("FILL", "password", 3)],
                    line_number=3,
                ),
                _step(
                    "    {{CLICK:login button}}",
                    [_placeholder("CLICK", "login button", 4)],
                    line_number=4,
                ),
            ],
        )
        plans = injector.analyze_dependencies(
            journeys=[auth_journey],
            starting_url="",
        )
        assert plans == {}

    def test_detects_auth_test_and_injects_for_cart_test(self) -> None:
        """The core scenario: test_01 logs in, test_02 adds to cart."""
        auth_journey = _journey(
            test_name="test_01_login",
            steps=[
                _step(
                    "    evidence_tracker.navigate('https://www.saucedemo.com')",
                    [_placeholder("GOTO", "home", 1)],
                    line_number=1,
                ),
                _step(
                    "    evidence_tracker.fill('#user-name', 'standard_user', label='username input')",
                    [_placeholder("FILL", "username", 2)],
                    line_number=2,
                ),
                _step(
                    "    evidence_tracker.fill('#password', 'secret_sauce', label='password input')",
                    [_placeholder("FILL", "password", 3)],
                    line_number=3,
                ),
                _step(
                    "    evidence_tracker.click('#login-button', label='login button')",
                    [_placeholder("CLICK", "login button", 4)],
                    line_number=4,
                ),
            ],
        )

        cart_journey = _journey(
            test_name="test_02_add_item",
            steps=[
                _step(
                    "    evidence_tracker.navigate('https://www.saucedemo.com')",
                    [_placeholder("GOTO", "home", 5)],
                    line_number=5,
                ),
                _step(
                    "    evidence_tracker.click('#backpack-add-to-cart', label='Sauce Labs Backpack add to cart button')",
                    [_placeholder("CLICK", "Sauce Labs Backpack add to cart button", 6)],
                    line_number=6,
                ),
            ],
        )

        injector = PrerequisiteInjector()
        plans = injector.analyze_dependencies(
            journeys=[auth_journey, cart_journey],
            starting_url="https://www.saucedemo.com",
        )

        # test_02 should need injection
        assert "test_02_add_item" in plans
        plan = plans["test_02_add_item"]
        assert plan.target_test == "test_02_add_item"
        # Plan includes all evidence_tracker steps (navigate, fill, click) —
        # navigation is filtered at injection time, not at analysis time.
        assert len(plan.prerequisites) == 4
        raw_lines = [s.raw_line for s in plan.prerequisites]
        # Navigate step IS in the plan (filtered during inject_into_code)
        assert any("navigate" in line for line in raw_lines)
        assert any("fill" in line for line in raw_lines)
        assert any("click" in line for line in raw_lines)

    def test_does_not_inject_for_auth_test_itself(self) -> None:
        """The auth test should never have prerequisites injected into itself."""
        auth_journey = _journey(
            test_name="test_01_login",
            steps=[
                _step(
                    "    evidence_tracker.fill('#user-name', 'standard_user', label='username')",
                    [_placeholder("FILL", "username", 2)],
                    line_number=2,
                ),
                _step(
                    "    evidence_tracker.click('#login-button', label='login button')",
                    [_placeholder("CLICK", "login button", 4)],
                    line_number=4,
                ),
            ],
        )

        injector = PrerequisiteInjector()
        plans = injector.analyze_dependencies(
            journeys=[auth_journey],
            starting_url="https://www.saucedemo.com",
        )

        # Only one test, no injection needed
        assert "test_01_login" not in plans

    def test_single_test_no_injection(self) -> None:
        """A single test with no dependencies should not trigger injection."""
        journey = _journey(
            test_name="test_01_view_home",
            steps=[
                _step(
                    "    evidence_tracker.navigate('https://example.com')",
                    [_placeholder("GOTO", "home", 1)],
                    line_number=1,
                ),
                _step(
                    "    evidence_tracker.assert_visible('h1', label='homepage heading')",
                    [_placeholder("ASSERT", "homepage heading", 2)],
                    line_number=2,
                ),
            ],
        )

        injector = PrerequisiteInjector()
        plans = injector.analyze_dependencies(
            journeys=[journey],
            starting_url="https://example.com",
        )

        assert plans == {}

    def test_no_post_auth_keywords_no_injection(self) -> None:
        """A test with no post-auth keywords should not get injection."""
        auth_journey = _journey(
            test_name="test_01_login",
            steps=[
                _step(
                    "    evidence_tracker.fill('#user-name', 'standard_user', label='username')",
                    [_placeholder("FILL", "username", 2)],
                    line_number=2,
                ),
            ],
        )

        # This test is about viewing the homepage - no post-auth action
        view_journey = _journey(
            test_name="test_02_view_homepage",
            steps=[
                _step(
                    "    evidence_tracker.navigate('https://www.saucedemo.com')",
                    [_placeholder("GOTO", "home", 5)],
                    line_number=5,
                ),
                _step(
                    "    evidence_tracker.assert_visible('h1', label='homepage title')",
                    [_placeholder("ASSERT", "homepage title", 6)],
                    line_number=6,
                ),
            ],
        )

        injector = PrerequisiteInjector()
        plans = injector.analyze_dependencies(
            journeys=[auth_journey, view_journey],
            starting_url="https://www.saucedemo.com",
        )

        # test_02 should NOT need injection (no post-auth keywords)
        assert "test_02_view_homepage" not in plans


# -- Tests: inject_into_code --


class TestInjectIntoCode:
    """Tests for PrerequisiteInjector.inject_into_code()"""

    def test_returns_code_unchanged_when_no_plans(self) -> None:
        injector = PrerequisiteInjector()
        code = "def test_01(page):\n    pass\n"
        result = injector.inject_into_code(code, {})
        assert result == code

    def test_injects_prerequisite_steps_with_markers(self) -> None:
        code = """\
import pytest
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.click('#backpack-add-to-cart', label='Sauce Labs Backpack add to cart button')
"""
        plan = InjectionPlan(
            target_test="test_02_add_item",
            prerequisites=[
                PrerequisiteStep(
                    raw_line="    evidence_tracker.fill('#user-name', 'standard_user', label='username input')",
                    source_test="test_01_login",
                    source_condition="TC-01",
                ),
                PrerequisiteStep(
                    raw_line="    evidence_tracker.fill('#password', 'secret_sauce', label='password input')",
                    source_test="test_01_login",
                    source_condition="TC-01",
                ),
                PrerequisiteStep(
                    raw_line="    evidence_tracker.click('#login-button', label='login button')",
                    source_test="test_01_login",
                    source_condition="TC-01",
                ),
            ],
            reason="test_02_add_item requires authentication (TC-01)",
        )

        injector = PrerequisiteInjector()
        result = injector.inject_into_code(code, {"test_02_add_item": plan})

        # Check that prerequisite markers are present
        assert "# --- Prerequisite: TC-01 (injected) ---" in result
        assert "# --- Original test steps ---" in result
        # Check that login steps are injected
        assert "evidence_tracker.fill('#user-name'" in result
        assert "evidence_tracker.fill('#password'" in result
        assert "evidence_tracker.click('#login-button'" in result
        # Original steps should still be present
        assert "evidence_tracker.click('#backpack-add-to-cart'" in result

    def test_preserves_decorators(self) -> None:
        code = """\
@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.click('#add-to-cart', label='add to cart')
"""
        plan = InjectionPlan(
            target_test="test_02_add_item",
            prerequisites=[
                PrerequisiteStep(
                    raw_line="    evidence_tracker.fill('#user-name', 'standard_user', label='username')",
                    source_test="test_01_login",
                ),
            ],
            reason="test_02_add_item requires authentication (TC-01)",
        )

        injector = PrerequisiteInjector()
        result = injector.inject_into_code(code, {"test_02_add_item": plan})

        # Decorator should still be present before the function
        assert "@pytest.mark.evidence" in result
        # Decorator should come before the function def
        decorator_pos = result.index("@pytest.mark.evidence")
        func_pos = result.index("def test_02_add_item")
        assert decorator_pos < func_pos

    def test_skips_navigation_and_consent_steps(self) -> None:
        """Navigation and consent dismiss steps should not be injected."""
        code = """\
def test_02_add_item(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.click('#add-to-cart', label='add to cart')
"""
        plan = InjectionPlan(
            target_test="test_02_add_item",
            prerequisites=[
                PrerequisiteStep(
                    raw_line="    evidence_tracker.navigate('https://www.saucedemo.com')",
                    source_test="test_01_login",
                ),
                PrerequisiteStep(
                    raw_line="    dismiss_consent_overlays(page)",
                    source_test="test_01_login",
                ),
                PrerequisiteStep(
                    raw_line="    evidence_tracker.fill('#user-name', 'standard_user', label='username')",
                    source_test="test_01_login",
                ),
                PrerequisiteStep(
                    raw_line="    evidence_tracker.click('#login-button', label='login button')",
                    source_test="test_01_login",
                ),
            ],
            reason="test_02_add_item requires authentication (TC-01)",
        )

        injector = PrerequisiteInjector()
        result = injector.inject_into_code(code, {"test_02_add_item": plan})

        # Navigation and consent dismiss should NOT be in injected section
        lines = result.splitlines()
        in_injected_section = False
        injected_lines = []
        for line in lines:
            if "# --- Prerequisite:" in line:
                in_injected_section = True
                continue
            if "# --- Original test steps ---" in line:
                in_injected_section = False
                continue
            if in_injected_section:
                injected_lines.append(line)

        injected_text = "\n".join(injected_lines)
        assert "navigate" not in injected_text
        assert "dismiss_consent_overlays" not in injected_text
        assert "fill" in injected_text
        assert "click" in injected_text

    def test_does_not_modify_unrelated_tests(self) -> None:
        """Tests not in injection plans should remain unchanged."""
        code = """\
def test_01_login(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.fill('#user-name', 'standard_user', label='username')

def test_03_view_profile(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    evidence_tracker.assert_visible('#profile', label='profile section')
"""
        plan = InjectionPlan(
            target_test="test_01_login",
            prerequisites=[],
            reason="test_01_login requires authentication (TC-01)",
        )

        injector = PrerequisiteInjector()
        result = injector.inject_into_code(code, {"test_01_login": plan})

        # test_03 should be unchanged
        assert "def test_03_view_profile" in result
        assert "evidence_tracker.assert_visible('#profile'" in result


# -- Tests: helper methods --


class TestHelperMethods:
    """Tests for internal helper methods"""

    def test_is_navigation_step(self) -> None:
        assert PrerequisiteInjector._is_navigation_step("    evidence_tracker.navigate('https://example.com')") is True
        assert PrerequisiteInjector._is_navigation_step("    evidence_tracker.click('#btn')") is False

    def test_is_consent_dismiss(self) -> None:
        assert PrerequisiteInjector._is_consent_dismiss("    dismiss_consent_overlays(page)") is True
        assert PrerequisiteInjector._is_consent_dismiss("    evidence_tracker.click('#btn')") is False

    def test_extract_tc_ref(self) -> None:
        assert PrerequisiteInjector._extract_tc_ref("test needs auth (TC-01)") == "TC-01"
        assert PrerequisiteInjector._extract_tc_ref("test needs auth (TC-05)") == "TC-05"
        assert PrerequisiteInjector._extract_tc_ref("no ref here") == "prerequisite"

    def test_find_auth_test_detects_login_pattern(self) -> None:
        auth_journey = _journey(
            test_name="test_01_login",
            steps=[
                _step(
                    "    {{FILL:username}}",
                    [_placeholder("FILL", "username", 2)],
                    line_number=2,
                ),
                _step(
                    "    {{CLICK:login button}}",
                    [_placeholder("CLICK", "login button", 4)],
                    line_number=4,
                ),
            ],
        )

        injector = PrerequisiteInjector()
        result = injector._find_auth_test([auth_journey], "https://example.com")
        assert result == "test_01_login"

    def test_find_auth_test_fallback_to_first(self) -> None:
        """When no login pattern is found, fallback to first journey."""
        journey = _journey(
            test_name="test_01_view_home",
            steps=[
                _step(
                    "    {{CLICK:heading}}",
                    [_placeholder("CLICK", "homepage heading", 1)],
                    line_number=1,
                ),
            ],
        )

        injector = PrerequisiteInjector()
        result = injector._find_auth_test([journey], "https://example.com")
        # Fallback to first test
        assert result == "test_01_view_home"


# -- Integration test --


class TestEndToEnd:
    """Integration tests combining analyze_dependencies + inject_into_code"""

    def test_full_pipeline_saucedemo_scenario(self) -> None:
        """Simulate the SauceDemo UAT scenario where tests 2-6 need login injection."""
        # Build auth journey (test_01)
        auth_journey = _journey(
            test_name="test_01_login",
            steps=[
                _step(
                    "    evidence_tracker.navigate('https://www.saucedemo.com')",
                    [_placeholder("GOTO", "saucedemo home", 1)],
                    line_number=1,
                ),
                _step(
                    "    evidence_tracker.fill('#user-name', 'standard_user', label='username input')",
                    [_placeholder("FILL", "username input", 2)],
                    line_number=2,
                ),
                _step(
                    "    evidence_tracker.fill('#password', 'secret_sauce', label='password input')",
                    [_placeholder("FILL", "password input", 3)],
                    line_number=3,
                ),
                _step(
                    "    evidence_tracker.click('#login-button', label='login button')",
                    [_placeholder("CLICK", "login button", 4)],
                    line_number=4,
                ),
            ],
        )

        # Build cart journey (test_02)
        cart_journey = _journey(
            test_name="test_02_add_item",
            steps=[
                _step(
                    "    evidence_tracker.navigate('https://www.saucedemo.com')",
                    [_placeholder("GOTO", "saucedemo home", 5)],
                    line_number=5,
                ),
                _step(
                    "    evidence_tracker.click('#backpack-add-to-cart', label='Sauce Labs Backpack add to cart button')",
                    [_placeholder("CLICK", "Sauce Labs Backpack add to cart button", 6)],
                    line_number=6,
                ),
            ],
        )

        code = """\
import pytest
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_add_item(page, evidence_tracker):
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.click('#backpack-add-to-cart', label='Sauce Labs Backpack add to cart button')
"""

        injector = PrerequisiteInjector()
        plans = injector.analyze_dependencies(
            journeys=[auth_journey, cart_journey],
            starting_url="https://www.saucedemo.com",
        )

        result = injector.inject_into_code(code, plans)

        # Verify injection happened
        assert "# --- Prerequisite:" in result
        assert "# --- Original test steps ---" in result

        # Verify login steps are in test_02
        # Extract test_02 body by finding the function def and collecting until
        # the next top-level definition or end of file.
        lines = result.splitlines()
        test_02_start = None
        for i, line in enumerate(lines):
            if "def test_02_add_item" in line:
                test_02_start = i
                break

        assert test_02_start is not None, "test_02_add_item function not found in result"

        # Collect lines from test_02 def until next non-indented, non-empty line
        # that is not a comment (i.e., another function def or import)
        test_02_lines: list[str] = []
        for i in range(test_02_start, len(lines)):
            line = lines[i]
            test_02_lines.append(line)
            # Stop if we hit another top-level def
            if (
                i > test_02_start
                and line
                and not line[0].isspace()
                and line.strip()
                and not line.strip().startswith("#")
            ):
                if "def " in line or "@" in line:
                    break

        test_02_code = "\n".join(test_02_lines)
        assert "evidence_tracker.fill('#user-name'" in test_02_code
        assert "evidence_tracker.fill('#password'" in test_02_code
        assert "evidence_tracker.click('#login-button'" in test_02_code
        # Original step should still be there
        assert "evidence_tracker.click('#backpack-add-to-cart'" in test_02_code

        # Verify test_01 is unchanged (no injection into auth test)
        test_01_start = result.index("def test_01_login")
        test_02_start = result.index("def test_02_add_item")
        test_01_code = result[test_01_start:test_02_start]
        # test_01 should not have prerequisite markers
        assert "# --- Prerequisite:" not in test_01_code
