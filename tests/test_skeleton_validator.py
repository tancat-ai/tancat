"""Tests for the SkeletonValidator class."""

from __future__ import annotations

from src.skeleton_parser import SkeletonValidator


class TestSkeletonValidator:
    """Test that the validator catches hallucinated CSS selectors."""

    def setup_method(self) -> None:
        self.validator = SkeletonValidator()

    def test_valid_skeleton_with_placeholders(self) -> None:
        """Skeleton using only placeholders should pass validation."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_add_to_cart(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("{{GOTO:home_url}}")
    evidence_tracker.click("{{CLICK:product}}", label="product")
    evidence_tracker.click("{{CLICK:add to cart button}}", label="add_to_cart")
    evidence_tracker.assert_visible("{{ASSERT:success message}}", label="success")
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is True
        assert result.violations == []

    def test_catches_css_class_selector_in_click(self) -> None:
        """LLM writing .btn.btn-success instead of placeholder should be caught."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_add_to_cart(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("https://example.com/")
    evidence_tracker.click('.btn.btn-success.close-checkout-modal.btn-block', label="success_message")
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is False
        assert any("CSS class selector" in v for v in result.violations)
        assert "Replace ALL real locators with placeholders" in result.suggestion

    def test_catches_css_class_selector_in_assert(self) -> None:
        """LLM writing .btn.btn-success in assert_visible should be caught."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_assert(page: Page, evidence_tracker) -> None:
    evidence_tracker.assert_visible('.btn.btn-success.close-modal.btn-block', label="success")
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is False
        assert any("CSS class selector" in v for v in result.violations)

    def test_catches_attribute_selector(self) -> None:
        """LLM writing [href="/path"] should be caught."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_click(page: Page, evidence_tracker) -> None:
    evidence_tracker.click('a[href="/view_cart"]', label="view cart")
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is False
        assert any("CSS attribute selector" in v for v in result.violations)

    def test_allows_urls_in_navigate(self) -> None:
        """Real URLs in navigate() should NOT be caught as violations."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_navigate(page: Page, evidence_tracker) -> None:
    evidence_tracker.navigate("https://automationexercise.com/")
    evidence_tracker.click("{{CLICK:products link}}", label="products")
    evidence_tracker.navigate("https://automationexercise.com/view_cart")
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is True
        assert result.violations == []

    def test_allows_placeholders_with_similar_patterns(self) -> None:
        """Placeholders containing descriptions that look like selectors should pass."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_example(page: Page, evidence_tracker) -> None:
    evidence_tracker.click("{{CLICK:button with class name}}", label="button")
    evidence_tracker.assert_visible("{{ASSERT:element with #id visible}}", label="result")
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is True

    def test_catches_page_locator_call(self) -> None:
        """LLM writing page.locator('.class') should be caught."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_click(page: Page, evidence_tracker) -> None:
    page.locator('.btn.btn-default').click()
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is False
        assert any("page.locator" in v for v in result.violations)

    def test_suggestion_provides_helpful_guidance(self) -> None:
        """The suggestion message should guide the LLM to fix the issue."""
        skeleton = """
from playwright.sync_api import Page
import pytest

@pytest.mark.evidence(condition_ref="TC01", story_ref="S01")
def test_01_click(page: Page, evidence_tracker) -> None:
    evidence_tracker.click('.btn.btn-success', label="success")
"""
        result = self.validator.validate(skeleton)
        assert result.is_valid is False
        assert "CLICK:description" in result.suggestion
        assert "ASSERT:description" in result.suggestion
        assert "placeholder resolver" in result.suggestion.lower()
