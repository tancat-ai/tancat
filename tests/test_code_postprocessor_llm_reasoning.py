"""Tests for src/code_postprocessor.py: LLM reasoning stripping, code normalisation,
token replacement, and placeholder resolution safety net."""

from __future__ import annotations

import ast
import asyncio
from unittest.mock import AsyncMock

import pytest

from src.code_normalizer import replace_remaining_placeholders
from src.code_normalizer import strip_pages_needed_block as _strip_pages_needed_block
from src.code_postprocessor import normalise_generated_code, replace_token_in_line
from src.llm_reasoning_filter import _is_llm_reasoning_line
from src.llm_reasoning_filter import strip_llm_reasoning as _strip_llm_reasoning_text
from src.orchestrator import TestOrchestrator
from src.test_generator import TestGenerator


class TestIsLlmReasoningLine:
    """Tests for the _is_llm_reasoning_line structural detector."""

    @pytest.mark.parametrize(
        "line",
        [
            # Numbered bullets
            "# - 1. Open the products page",
            "# - 2. Click the button",
            "  # - 3. Verify the result",
            # Range references
            "# - 1-2 Select an option",
            # Parenthetical notes
            "# - (My test has three steps)",
            # Requirement-style bullets
            "# - Username field must be visible",
            "# - Password field should be hidden",
            "# - Button needs to be clickable",
            "# - Title MAX 50 chars",
            # Constraint-style bullets
            "# - Button inside the modal",
            "# - Input within the form",
            "# - Checkbox inside, the sidebar",
            # Sentence fragments (non-assignment)
            "Wait, I need to check something",
            "Actually, this is wrong",
        ],
    )
    def test_detects_structural_reasoning_lines(self, line: str) -> None:
        """Lines that match structural reasoning patterns should be detected."""
        assert _is_llm_reasoning_line(line) is True

    @pytest.mark.parametrize(
        "line",
        [
            "def test_example() -> None:",
            '    page.goto("https://example.com")',
            "import pytest",
            "from playwright.sync_api import Page",
            "# This is a comment",
            "# TODO: fix this later",
            "# FIXME: broken selector",
            "# type: ignore",
            "assert True",
            "",
            "# PAGES_NEEDED:",
            "# - https://example.com",
            "    evidence_tracker.click('#btn', label='button')",
        ],
    )
    def test_ignores_code_lines(self, line: str) -> None:
        """Actual code lines and valid comments should not be detected as reasoning."""
        assert _is_llm_reasoning_line(line) is False

    def test_long_conversational_comment(self) -> None:
        """Long comments with multiple conversational indicators should be detected."""
        line = (
            "# We can see that the page should display the order summary, and I would assume "
            "that we could verify it by checking the visible elements on the page."
        )
        assert _is_llm_reasoning_line(line) is True

    def test_short_conversational_comment_not_detected(self) -> None:
        """Short comments with a single conversational word should pass through."""
        line = "# We click the button"
        assert _is_llm_reasoning_line(line) is False

    def test_sentence_fragment_assignment_not_detected(self) -> None:
        """Variable assignments starting with CapitalWord, should not be stripped."""
        line = "Status, = some_value"
        assert _is_llm_reasoning_line(line) is False


class TestStripLlmReasoningText:
    """Tests for the strip_llm_reasoning function."""

    def test_strips_numbered_bullets_from_code(self) -> None:
        """Numbered reasoning bullets should be removed."""
        code = """import pytest
# - 1. Navigate to the page
from playwright.sync_api import Page
# - 2. Click the button

def test_example() -> None:
    page.goto("https://example.com")
"""
        result = _strip_llm_reasoning_text(code)
        assert "# - 1." not in result
        assert "# - 2." not in result
        assert 'page.goto("https://example.com")' in result

    def test_steps_output_not_affected(self) -> None:
        """Steps output printed to stdout should not be affected."""
        code = """Here is the test code:

```python
import pytest
from playwright.sync_api import Page

print("Wait, this is steps output")
def test_example() -> None:
    page.goto("https://example.com")
```
"""
        result = _strip_llm_reasoning_text(code)
        assert 'print("Wait, this is steps output")' in result

    def test_handles_no_reasoning(self) -> None:
        """Code without reasoning lines should pass through unchanged."""
        code = """import pytest
from playwright.sync_api import Page

def test_example() -> None:
    page.goto("https://example.com")
"""
        result = _strip_llm_reasoning_text(code)
        assert result.strip() == code.strip()

    def test_handles_empty_code(self) -> None:
        """Empty code should return empty string."""
        assert _strip_llm_reasoning_text("") == ""

    def test_preserves_valid_comments(self) -> None:
        """TODO, FIXME, type: comments should not be stripped."""
        code = """import pytest
# TODO: improve this test
# FIXME: flaky selector
# type: ignore

def test_example() -> None:
    pass
"""
        result = _strip_llm_reasoning_text(code)
        assert "# TODO:" in result
        assert "# FIXME:" in result
        assert "# type: ignore" in result

    def test_preserves_pages_needed(self) -> None:
        """PAGES_NEEDED metadata should not be stripped."""
        code = """def test_example() -> None:
    pass

# PAGES_NEEDED:
# - https://example.com
"""
        result = _strip_llm_reasoning_text(code)
        assert "# PAGES_NEEDED:" in result
        assert "# - https://example.com" in result


def test_normalise_generated_code_strips_invalid_pytest_mark_assignment() -> None:
    broken = """
import pytest
from playwright.sync_api import Page

@pytest.markelse = None # Placeholder to keep structure clean
@pytest.mark.evidence(condition_ref="TC01.01", story_ref="S1")
def test_01_ok(page: Page, evidence_tracker) -> None:
    pass
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "@pytest.markelse" not in fixed
    assert "@pytest.mark.evidence" in fixed


def test_normalise_generated_code_repairs_hallucinated_page_object_constructor_and_callsite() -> None:
    broken = """
from playwright.sync_api import Page, expect

def dismiss_consent_overlays(page: Page) -> None:
    pass

class CartPage:
    def __larry(self, page: Page):
        self.page = page

    def go(self) -> None:
        dismiss_consent_overlays(page)
        page.goto("https://example.com/")

def test_01_checkout(page: Page):
    cart = CartPage(project=page) # Note: using placeholder logic
    cart.go()
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "def __init__(self, page: Page) -> None:" in fixed
    assert "CartPage(page)" in fixed
    assert "dismiss_consent_overlays(self.page)" in fixed
    assert 'evidence_tracker.navigate("https://example.com/")' in fixed


def test_normalise_generated_code_rewrites_hallucinated_evidence_launcher_fixture() -> None:
    broken = """
import pytest
from playwright.sync_api import Page

@pytest.mark/evidence(condition_ref="TC01.01", story_ref="S1")
def test_01_ok(page: Page, evidence_launcher) -> None:
    evidence_launcher.step("hello")
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "evidence_launcher" not in fixed
    assert "evidence_tracker" in fixed


def test_normalise_generated_code_adds_evidence_tracker_fixture_when_body_uses_it() -> None:
    broken = """
import pytest

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_login(page):
    evidence_tracker.navigate("https://example.com/")
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    # Now adds page: Page type hint since evidence_tracker depends on page fixture
    assert "def test_01_login(page: Page, evidence_tracker):" in fixed


def test_normalise_generated_code_repairs_pytest_mark_slash_typo() -> None:
    broken = """
import pytest

@pytest.mark/evidence(condition_ref="TC01.01", story_ref="S1")
def test_01_ok() -> None:
    assert True
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "@pytest.mark/evidence" not in fixed
    assert "@pytest.mark.evidence" in fixed


def test_normalise_generated_code_rewrites_consent_helper_page_reference_in_page_objects() -> None:
    broken = """
from playwright.sync_api import Page

def dismiss_consent_overlays(page: Page) -> None:
    pass

class ProductPage:
    def __init__(self, page: Page):
        self.page = page

    def navigate(self, evidence_tracker) -> None:
        evidence_tracker.navigate("https://example.com/")
        dismiss_consent_overlays(page)
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "dismiss_consent_overlays(self.page)" in fixed


def test_normalise_generated_code_dedents_top_level_test_block_after_helper() -> None:
    broken = """
import pytest
from playwright.sync_api import Page

def dismiss_consent_overlays(page: Page) -> None:
    pass

     @pytest.mark.evidence(condition_ref="TC01.01", story_ref="S1")
     def test_01_ok(page: Page, evidence_tracker) -> None:
         evidence_tracker.navigate("https://example.com/")
         assert True

     # PAGES_NEEDED:
     # - https://example.com/
"""
    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")
    assert "\n@pytest.mark.evidence" in fixed
    assert "\n     @pytest.mark.evidence" not in fixed
    assert "\ndef test_01_ok" in fixed


def test_normalise_generated_code_injects_playwright_import_when_page_annotations_exist() -> None:
    broken = """
def test_01_ok(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("https://example.com/")
"""
    fixed = normalise_generated_code(broken, consent_mode="auto-dismiss")
    assert "from playwright.sync_api import Page, expect" in fixed
    assert "from src.browser_utils import dismiss_consent_overlays" in fixed
    assert "dismiss_consent_overlays(page)" in fixed


def test_run_pipeline_normalises_payable_type_to_page() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

class CheckoutPage:
    def __init__(self, page: Payable):
        self.page = page

def test_checkout(page: Page):
    checkout_page = CheckoutPage(page)
    checkout_page
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(return_value={})  # type: ignore[method-assign]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to check out",
            conditions="1. Check out",
            target_urls=[],
        )
    )

    assert "page: Payable" not in final_code
    assert "page: Page" in final_code


def test_run_pipeline_normalises_unknown_page_parameter_type_to_page() -> None:
    generator = TestGenerator(output_dir="generated_tests")
    generator.generate_skeleton = AsyncMock(  # type: ignore[method-assign]
        return_value="""
from playwright.sync_api import Page

class CheckoutPage:
    def __init__(self, page: Note):
        self.page = page

def test_01_checkout(page: Note):
    checkout_page = CheckoutPage(page)
    checkout_page
"""
    )

    orchestrator = TestOrchestrator(generator)
    orchestrator.scraper.scrape_all = AsyncMock(return_value={})  # type: ignore[method-assign]

    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story="As a shopper I want to check out",
            conditions="1. Check out",
            target_urls=[],
        )
    )

    assert "page: Note" not in final_code
    assert "def __init__(self, page: Page)" in final_code
    # POM instantiation (CheckoutPage(page)) triggers both page and evidence_tracker fixtures
    assert (
        "def test_01_checkout(page: Page, evidence_tracker)" in final_code
        or "def test_01_checkout(page: Page)" in final_code
    )


def test_replace_token_in_line_uses_description_for_label_not_token() -> None:
    """Ensure evidence labels use the plain description, not the bracketed token."""
    line = "evidence_tracker.click('{{CLICK:basket}}')"

    fixed = replace_token_in_line(
        line=line,
        action="CLICK",
        token="{{CLICK:basket}}",
        resolved_value="'#cart-btn'",
        duplicate_selectors=set(),
        description="shopping basket",
    )

    assert "label='shopping basket'" in fixed
    assert "{{CLICK:basket}}" not in fixed


def test_replace_token_in_line_with_skip_replaces_whole_line() -> None:
    """Unresolved steps should become standalone skips, not invalid parameter injections."""
    line = "    evidence_tracker.click('{{CLICK:missing}}')"

    fixed = replace_token_in_line(
        line=line,
        action="CLICK",
        token="{{CLICK:missing}}",
        resolved_value='pytest.skip("not found")',
        duplicate_selectors=set(),
        description="missing button",
    )

    assert fixed.strip() == 'pytest.skip("not found")'
    assert "evidence_tracker.click" not in fixed


def test_replace_token_in_line_goto_replaces_quoted_placeholder_without_double_quotes() -> None:
    line = '    evidence_tracker.navigate("{{GOTO:products page}}")'

    fixed = replace_token_in_line(
        line=line,
        action="GOTO",
        token="{{GOTO:products page}}",
        resolved_value="'https://example.com/products'",
        duplicate_selectors=set(),
        description="products page",
    )

    assert fixed.strip() == "evidence_tracker.navigate('https://example.com/products')"


def test_replace_remaining_placeholders_converts_placeholders_in_function_calls() -> None:
    """Placeholders inside function call arguments (even in quotes) must be converted to pytest.skip().

    This is the correct behavior: a raw {{CLICK:basket}} token inside a function call
    is invalid Python at runtime and must be replaced with pytest.skip() to avoid SyntaxError.
    """
    code = "evidence_tracker.click('#id', label='{{CLICK:basket}}')"
    fixed = replace_remaining_placeholders(code)

    # The entire line should be replaced with pytest.skip()
    assert "pytest.skip" in fixed
    assert "{{CLICK:basket}}" not in fixed or "pytest.skip" in fixed  # May appear in skip reason


def test_replace_remaining_placeholders_converts_raw_placeholder_to_skip() -> None:
    """Unresolved {{...}} placeholders (e.g. those with Python variable syntax) must be
    replaced with pytest.skip() so they never produce a SyntaxError."""
    code_with_unresolved = """\
def test_something(page, evidence_tracker):
    {{ASSERT:item {item_name} is present in cart}}
    {{CLICK:add to cart button}}
"""
    fixed = replace_remaining_placeholders(code_with_unresolved)
    assert "pytest.skip(" in fixed
    # Confirm no line starts with a raw placeholder (which would be invalid Python syntax)
    for line in fixed.splitlines():
        assert not line.lstrip().startswith("{{"), f"Raw placeholder still present: {line!r}"
    # Indentation must be preserved
    for line in fixed.splitlines():
        if "pytest.skip" in line:
            assert line.startswith("    "), f"Expected indented skip, got: {line!r}"


def test_replace_remaining_placeholders_replaces_function_call_line_with_valid_skip() -> None:
    """Unresolved placeholders inside function calls must become valid standalone skips."""
    code_with_unresolved = """\
import pytest

def test_checkout(page, evidence_tracker):
    evidence_tracker.fill({{FILL:email}}, '', label="email")
    """
    fixed = replace_remaining_placeholders(code_with_unresolved)
    assert "evidence_tracker.fill(" not in fixed
    assert "Unresolved placeholder in this step." in fixed
    assert "pytest.skip(" in fixed
    ast.parse(fixed)


def test_normalise_generated_code_unwraps_evidence_tracker_wrapped_placeholders() -> None:
    """The normaliser should unwrap evidence_tracker wrapped placeholders to standalone token lines."""
    code = """\
from playwright.sync_api import Page, expect
import pytest

def test_01(page: Page, evidence_tracker) -> None:
    evidence_tracker.click( {{CLICK:add to cart}}, label='add to cart')
"""
    fixed = normalise_generated_code(code, consent_mode="leave-as-is")
    assert "evidence_tracker.click(" not in fixed
    assert "{{CLICK:add to cart}}" in fixed


def test_strip_pages_needed_block_removes_trailing_skeleton_metadata() -> None:
    code = """from playwright.sync_api import Page, expect

def test_checkout(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://example.com/')

# PAGES_NEEDED:
# - https://example.com/
"""

    fixed = _strip_pages_needed_block(code)

    assert "# PAGES_NEEDED:" not in fixed
    assert "# - https://example.com/" not in fixed


def test_normalise_generated_code_fixes_over_indented_lines_after_placeholder_skip() -> None:
    broken = """from playwright.sync_api import Page, expect
import pytest

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_checkout(page: Page, evidence_tracker) -> None:
    pytest.skip("Skipping unresolved placeholders")
           evidence_tracker.navigate('https://example.com/')
           pytest.skip('Unresolved placeholder in this step. {{CLICK:buy}}')

       # PAGES_NEEDED:
       # - https://example.com/
"""

    fixed = normalise_generated_code(broken, consent_mode="leave-as-is")

    assert "# PAGES_NEEDED:" not in fixed
    ast.parse(fixed)


def test_normalise_generated_code_preserves_nested_helper_blocks_in_auto_dismiss_mode() -> None:
    broken = """from playwright.sync_api import Page, expect

def test_checkout(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate('https://example.com/')
           evidence_tracker.click('#buy', label='buy')
"""

    fixed = normalise_generated_code(broken, consent_mode="auto-dismiss")

    assert "from src.browser_utils import dismiss_consent_overlays" in fixed
    assert "dismiss_consent_overlays(page)" in fixed
    ast.parse(fixed)
