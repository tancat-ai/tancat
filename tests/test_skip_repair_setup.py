"""Tests for skip-repair setup script translation and URL normalization."""

from src.locator_repair import translate_setup_step_to_python
from src.url_utils import normalize_url_path


def test_normalize_url_path_fixes_categoryproduct_typo() -> None:
    url = "https://automationexercise.com/categoryproduct/1"
    assert normalize_url_path(url) == "https://automationexercise.com/category_products/1"


def test_normalize_url_path_fixes_hyphen_and_underscore_variants() -> None:
    assert normalize_url_path("https://example.com/category-product/2") == "https://example.com/category_products/2"
    assert normalize_url_path("https://example.com/category_product/2") == "https://example.com/category_products/2"


def test_translate_pom_click_uses_text_matching_not_css_selector() -> None:
    lines = translate_setup_step_to_python("home_page.click('Dress')")
    joined = "\n".join(lines)
    assert "get_by_role('link', name='Dress')" in joined
    assert "locator('Dress')" not in joined
    # Fallback uses get_by_text() (modern API) instead of deprecated text=Dress CSS selector
    assert "get_by_text('Dress'" in joined


def test_translate_pom_fill_uses_label_or_placeholder() -> None:
    lines = translate_setup_step_to_python("home_page.fill('Email', 'test@example.com')")
    joined = "\n".join(lines)
    assert "get_by_label('Email')" in joined
    assert "test@example.com" in joined


def test_translate_evidence_tracker_locator_click() -> None:
    lines = translate_setup_step_to_python(
        "evidence_tracker.click('.add-to-cart.btn[data-product-id=\"11\"]', label='Add to cart')"
    )
    joined = "\n".join(lines)
    assert "get_by_text('Add to cart')" in joined
