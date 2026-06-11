"""Tests for POM mode in PlaceholderOrchestrator (AI-010 Phase 2).

Validates that the orchestrator correctly:
- Accepts and stores the pom_mode flag
- Builds evidence-aware page objects when pom_mode=True
- Generates POM imports and instantiation lines
- Resolves POM instance names by URL
- Generates POM method calls for CLICK/FILL (not ASSERT/GOTO)
"""

from __future__ import annotations

from src.pipeline_models import GeneratedPageObject, ScrapedPage
from src.placeholder_orchestrator import PlaceholderOrchestrator


def test_pom_mode_flag_default_false() -> None:
    """pom_mode should default to False for backward compatibility."""
    orch = PlaceholderOrchestrator()
    assert orch._pom_mode is False


def test_pom_mode_flag_can_be_true() -> None:
    """pom_mode=True should be stored."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    assert orch._pom_mode is True


def test_build_page_object_artifacts_uses_evidence_tracker_when_pom_mode() -> None:
    """Page objects should be built with use_evidence_tracker=True in POM mode."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    scraped = [
        ScrapedPage(
            url="https://example.com/home",
            element_count=1,
            elements=[{"tag": "button", "text": "Submit", "selector": "#submit"}],
        )
    ]
    objects = orch._build_page_object_artifacts(scraped)
    assert len(objects) == 1
    po = objects[0]
    # In POM mode, methods should use self.tracker
    src = po.module_source
    assert "self.tracker" in src


def test_build_page_object_artifacts_plain_when_not_pom_mode() -> None:
    """Page objects should be plain (page.locator) when pom_mode=False."""
    orch = PlaceholderOrchestrator(pom_mode=False)
    scraped = [
        ScrapedPage(
            url="https://example.com/home",
            element_count=1,
            elements=[{"tag": "button", "text": "Submit", "selector": "#submit"}],
        )
    ]
    objects = orch._build_page_object_artifacts(scraped)
    assert len(objects) == 1
    src = objects[0].module_source
    assert "self.tracker" not in src


def test_build_pom_url_map() -> None:
    """_build_pom_url_map should map URLs to page objects."""
    orch = PlaceholderOrchestrator()
    po_home = GeneratedPageObject(
        url="https://example.com/home",
        class_name="HomePage",
        module_name="home_page",
        file_path="pages/home_page.py",
    )
    po_cart = GeneratedPageObject(
        url="https://example.com/cart",
        class_name="CartPage",
        module_name="cart_page",
        file_path="pages/cart_page.py",
    )
    url_map = orch._build_pom_url_map([po_home, po_cart])
    assert url_map["https://example.com/home"] is po_home
    assert url_map["https://example.com/cart"] is po_cart


def test_build_pom_imports() -> None:
    """_build_pom_imports should generate correct import statements."""
    orch = PlaceholderOrchestrator()
    po_home = GeneratedPageObject(
        url="https://example.com/home",
        class_name="HomePage",
        module_name="home_page",
        file_path="pages/home_page.py",
    )
    po_cart = GeneratedPageObject(
        url="https://example.com/cart",
        class_name="CartPage",
        module_name="cart_page",
        file_path="pages/cart_page.py",
    )
    imports = orch._build_pom_imports([po_home, po_cart])
    assert "from pages.home_page import HomePage" in imports
    assert "from pages.cart_page import CartPage" in imports


def test_build_pom_instantiation() -> None:
    """_build_pom_instantiation should generate correct instance lines with EvidenceTracker."""
    orch = PlaceholderOrchestrator()
    po_home = GeneratedPageObject(
        url="https://example.com/home",
        class_name="HomePage",
        module_name="home_page",
        file_path="pages/home_page.py",
    )
    po_view_cart = GeneratedPageObject(
        url="https://example.com/view_cart",
        class_name="ViewCartPage",
        module_name="view_cart_page",
        file_path="pages/view_cart_page.py",
    )
    # Default use_evidence_tracker=True generates instances with tracker parameter
    lines = orch._build_pom_instantiation([po_home, po_view_cart])
    assert "    home_page = HomePage(page, evidence_tracker)" in lines
    assert "    view_cart_page = ViewCartPage(page, evidence_tracker)" in lines

    # use_evidence_tracker=False generates plain instances (backward compatible)
    plain_lines = orch._build_pom_instantiation([po_home, po_view_cart], use_evidence_tracker=False)
    assert "    home_page = HomePage(page)" in plain_lines
    assert "    view_cart_page = ViewCartPage(page)" in plain_lines


def test_get_pom_instance_name_matches_url() -> None:
    """_get_pom_instance_name should return the correct instance name for a URL."""
    orch = PlaceholderOrchestrator()
    po_home = GeneratedPageObject(
        url="https://example.com/home",
        class_name="HomePage",
        module_name="home_page",
        file_path="pages/home_page.py",
    )
    po_cart = GeneratedPageObject(
        url="https://example.com/cart",
        class_name="CartPage",
        module_name="cart_page",
        file_path="pages/cart_page.py",
    )
    assert orch._get_pom_instance_name("https://example.com/home", [po_home, po_cart]) == "home_page"
    assert orch._get_pom_instance_name("https://example.com/cart", [po_home, po_cart]) == "cart_page"
    assert orch._get_pom_instance_name("https://example.com/unknown", [po_home, po_cart]) is None
    assert orch._get_pom_instance_name(None, [po_home, po_cart]) is None


def test_get_pom_method_call_click_returns_pom_call_when_pom_mode() -> None:
    """CLICK should generate POM method call in POM mode."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    result = orch._get_pom_method_call("CLICK", "Submit button", "#submit", "home_page")
    assert result == "home_page.click('Submit button')"


def test_get_pom_method_call_fill_returns_pom_call_when_pom_mode() -> None:
    """FILL should generate POM method call with fill_value in POM mode."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    result = orch._get_pom_method_call("FILL", "Username input", "#username", "login_page", fill_value="testuser")
    assert result == "login_page.fill('Username input', 'testuser')"


def test_get_pom_method_call_assert_returns_none_in_pom_mode() -> None:
    """ASSERT should remain as direct evidence_tracker call (not POM)."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    result = orch._get_pom_method_call("ASSERT", "Success message", "#success", "home_page")
    assert result is None


def test_get_pom_method_call_goto_returns_none_in_pom_mode() -> None:
    """GOTO should remain as direct page.goto (not POM)."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    result = orch._get_pom_method_call("GOTO", "Home page", "https://example.com", "home_page")
    assert result is None


def test_get_pom_method_call_url_returns_none_in_pom_mode() -> None:
    """URL should remain as direct page.goto (not POM)."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    result = orch._get_pom_method_call("URL", "Home page", "https://example.com", "home_page")
    assert result is None


def test_get_pom_method_call_returns_none_when_not_pom_mode() -> None:
    """All actions should return None when pom_mode=False."""
    orch = PlaceholderOrchestrator(pom_mode=False)
    assert orch._get_pom_method_call("CLICK", "Submit", "#submit", "home_page") is None
    assert orch._get_pom_method_call("FILL", "Username", "#user", "login_page", "test") is None


def test_pom_mode_preserves_page_object_builder_evidence_tracker_param() -> None:
    """Verify the PageObjectBuilder receives use_evidence_tracker=True in POM mode."""
    orch = PlaceholderOrchestrator(pom_mode=True)
    # The builder is instantiated with default use_evidence_tracker=False,
    # but _build_page_object_artifacts passes use_evidence_tracker=self._pom_mode
    assert orch._pom_mode is True
    # Verify by building artifacts
    scraped = [
        ScrapedPage(
            url="https://example.com/test",
            element_count=1,
            elements=[{"tag": "input", "name": "q", "selector": "#search", "type": "text"}],
        )
    ]
    objects = orch._build_page_object_artifacts(scraped)
    assert len(objects) == 1
    # Evidence-aware POM should have tracker in __init__
    assert "tracker" in objects[0].module_source
