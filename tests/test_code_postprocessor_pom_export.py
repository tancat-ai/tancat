"""Unit tests for strip_evidence_from_pom() in code_postprocessor."""

from src.code_postprocessor import strip_evidence_from_pom, strip_evidence_from_test_code


class TestStripEvidenceFromPomInit:
    """Tests for __init__ signature transformation."""

    def test_replaces_evidence_init_signature(self) -> None:
        code = (
            "    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:\n"
            "        self.page = page\n"
            "        self.tracker = tracker\n"
        )
        result = strip_evidence_from_pom(code)
        assert "def __init__(self, page: Page) -> None:" in result
        assert "tracker: EvidenceTracker" not in result

    def test_removes_tracker_assignment(self) -> None:
        code = (
            "    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:\n"
            "        self.page = page\n"
            "        self.tracker = tracker\n"
        )
        result = strip_evidence_from_pom(code)
        assert "self.tracker = tracker" not in result
        assert "self.page = page" in result


class TestStripEvidenceFromPomImport:
    """Tests for EvidenceTracker import removal."""

    def test_removes_evidence_tracker_import(self) -> None:
        code = (
            '"""Auto-generated page object module."""\n\n'
            "from playwright.sync_api import Page\n"
            "from src.evidence_tracker import EvidenceTracker\n\n\n"
            "class LoginPage:\n"
        )
        result = strip_evidence_from_pom(code)
        assert "from src.evidence_tracker import EvidenceTracker" not in result
        assert "from playwright.sync_api import Page" in result

    def test_preserves_playwright_import(self) -> None:
        code = "from playwright.sync_api import Page\nfrom src.evidence_tracker import EvidenceTracker\n"
        result = strip_evidence_from_pom(code)
        assert "from playwright.sync_api import Page" in result


class TestStripEvidenceFromPomClick:
    """Tests for click method transformation."""

    def test_converts_tracker_click_to_locator_click(self) -> None:
        code = '        self.tracker.click("#login-button", label="login button")'
        result = strip_evidence_from_pom(code)
        assert 'self.page.locator("#login-button").click()' in result
        assert "self.tracker.click" not in result

    def test_converts_click_with_single_quotes(self) -> None:
        code = "        self.tracker.click('#user-name', label='username input')"
        result = strip_evidence_from_pom(code)
        assert "self.page.locator('#user-name').click()" in result


class TestStripEvidenceFromPomFill:
    """Tests for fill method transformation."""

    def test_converts_tracker_fill_to_locator_fill(self) -> None:
        code = '        self.tracker.fill("#user-name", value, label="username input")'
        result = strip_evidence_from_pom(code)
        assert 'self.page.locator("#user-name").fill(value)' in result
        assert "self.tracker.fill" not in result

    def test_preserves_value_parameter(self) -> None:
        code = '        self.tracker.fill("#password", value, label="password input")'
        result = strip_evidence_from_pom(code)
        assert 'self.page.locator("#password").fill(value)' in result


class TestStripEvidenceFromPomNavigate:
    """Tests for navigate method transformation."""

    def test_converts_tracker_navigate_to_page_goto(self) -> None:
        code = "        self.tracker.navigate(self.URL)"
        result = strip_evidence_from_pom(code)
        assert "self.page.goto(self.URL)" in result
        assert "self.tracker.navigate" not in result

    def test_converts_navigate_with_label(self) -> None:
        code = '        self.tracker.navigate("https://example.com", label="home page")'
        result = strip_evidence_from_pom(code)
        assert 'self.page.goto("https://example.com")' in result


class TestStripEvidenceFromPomAssert:
    """Tests for assert_visible method transformation."""

    def test_converts_tracker_assert_to_expect(self) -> None:
        code = '        self.tracker.assert_visible(".cart-badge", label="cart badge")'
        result = strip_evidence_from_pom(code)
        assert 'expect(self.page.locator(".cart-badge")).to_be_visible()' in result

    def test_adds_expect_import_when_needed(self) -> None:
        code = (
            "from playwright.sync_api import Page\n\n\n"
            "class LoginPage:\n"
            "    def check_visible(self) -> None:\n"
            '        self.tracker.assert_visible(".alert", label="alert")\n'
        )
        result = strip_evidence_from_pom(code)
        assert "from playwright.sync_api import Page, expect" in result


class TestStripEvidenceFromPomGetText:
    """Tests for get_text method transformation."""

    def test_converts_tracker_get_text(self) -> None:
        code = '        self.tracker.get_text(".total", label="total price")'
        result = strip_evidence_from_pom(code)
        assert 'self.page.locator(".total").text_content()' in result


class TestStripEvidenceFromPomSelect:
    """Tests for select method transformation."""

    def test_converts_tracker_select(self) -> None:
        code = '        self.tracker.select("#shipping", value, label="shipping method")'
        result = strip_evidence_from_pom(code)
        assert 'self.page.locator("#shipping").select_option(value)' in result


class TestStripEvidenceFromPomFullModule:
    """Integration tests for full POM module transformation."""

    def test_full_evidence_aware_module(self) -> None:
        """Transform a complete evidence-aware POM module to clean POM."""
        code = (
            '"""Auto-generated page object module."""\n\n'
            "from playwright.sync_api import Page\n"
            "from src.evidence_tracker import EvidenceTracker\n\n\n"
            "class LoginPage:\n"
            '    """Page Object for https://www.saucedemo.com. Scraped elements: 3."""\n\n'
            '    URL = "https://www.saucedemo.com"\n\n'
            "    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:\n"
            "        self.page = page\n"
            "        self.tracker = tracker\n\n"
            "    def navigate(self) -> None:\n"
            "        self.tracker.navigate(self.URL)\n\n"
            "    def __getattr__(self, name):\n"
            "        def fallback(*args, **kwargs):\n"
            "            import pytest\n"
            "            pytest.skip(f\"Method '{name}' not found on {self.__class__.__name__}. The scraper may have missed this element or its label changed.\")\n"
            "        return fallback\n"
            "    def fill_username(self, value: str) -> None:\n"
            '        self.tracker.fill("#user-name", value, label="username")\n'
            "    def fill_password(self, value: str) -> None:\n"
            '        self.tracker.fill("#password", value, label="password")\n'
            "    def click_login_button(self) -> None:\n"
            '        self.tracker.click("#login-button", label="login button")\n'
        )
        result = strip_evidence_from_pom(code)

        # EvidenceTracker completely removed
        assert "EvidenceTracker" not in result
        assert "self.tracker" not in result
        assert "tracker" not in result

        # Clean signatures
        assert "def __init__(self, page: Page) -> None:" in result
        assert 'self.page.locator("#user-name").fill(value)' in result
        assert 'self.page.locator("#password").fill(value)' in result
        assert 'self.page.locator("#login-button").click()' in result
        assert "self.page.goto(self.URL)" in result

        # Preserved structure
        assert "class LoginPage:" in result
        assert 'URL = "https://www.saucedemo.com"' in result
        assert "from playwright.sync_api import Page" in result

    def test_no_double_blank_lines(self) -> None:
        """Ensure removed lines don't leave excessive blank lines."""
        code = (
            '"""Auto-generated page object module."""\n\n'
            "from playwright.sync_api import Page\n"
            "from src.evidence_tracker import EvidenceTracker\n\n\n"
            "class LoginPage:\n"
            "    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:\n"
            "        self.page = page\n"
            "        self.tracker = tracker\n\n"
        )
        result = strip_evidence_from_pom(code)
        # Should not have 3+ consecutive newlines
        assert "\n\n\n" not in result


class TestStripEvidenceFromPomEdgeCases:
    """Edge cases and idempotency."""

    def test_idempotent_on_clean_code(self) -> None:
        """Running on already-clean code should not change it (after first normalization)."""
        # Input already has normalized blank-line spacing (max 2 consecutive newlines)
        clean_code = (
            "from playwright.sync_api import Page\n\n"
            "class LoginPage:\n"
            "    def __init__(self, page: Page) -> None:\n"
            "        self.page = page\n"
        )
        result = strip_evidence_from_pom(clean_code)
        assert result == clean_code

    def test_no_false_positives_on_plain_text(self) -> None:
        """Should not crash on code without evidence patterns."""
        code = "# Just a comment\nprint('hello')\n"
        result = strip_evidence_from_pom(code)
        assert result == code


class TestStripEvidenceFromTestCodePomConversion:
    """strip_evidence_from_test_code must convert POM-mode tests for flat export."""

    def test_removes_pom_imports_and_instantiations(self) -> None:
        code = (
            "from playwright.sync_api import Page, expect\n"
            "import pytest\n"
            "from pages.home_page import HomePage\n"
            "from pages.products_page import ProductsPage\n"
            "\n"
            '@pytest.mark.evidence(condition_ref="T01", story_ref="S01")\n'
            "def test_01(page, evidence_tracker):\n"
            "    home_page = HomePage(page, evidence_tracker)\n"
            "    products_page = ProductsPage(page, evidence_tracker)\n"
            "    evidence_tracker.navigate('https://example.com/')\n"
            "    home_page.click('Products', selector='a[href=\"/products\"]')\n"
        )
        result = strip_evidence_from_test_code(code)
        assert "from pages." not in result
        assert "= HomePage(" not in result
        assert "= ProductsPage(" not in result

    def test_converts_pom_click_with_selector(self) -> None:
        code = (
            "def test_01(page, evidence_tracker):\n"
            "    home_page = HomePage(page, evidence_tracker)\n"
            "    home_page.click('Products', selector='a[href=\"/products\"]')\n"
        )
        result = strip_evidence_from_test_code(code)
        assert "page.locator('a[href=\"/products\"]').click()" in result
        assert "_page." not in result

    def test_converts_pom_click_without_selector_best_effort(self) -> None:
        code = (
            "def test_01(page, evidence_tracker):\n"
            "    home_page = HomePage(page, evidence_tracker)\n"
            "    home_page.click('Add to cart')\n"
        )
        result = strip_evidence_from_test_code(code)
        assert "page.get_by_text('Add to cart').first.click()" in result

    def test_converts_pom_fill_with_selector(self) -> None:
        code = (
            "def test_01(page, evidence_tracker):\n"
            "    login_page = LoginPage(page, evidence_tracker)\n"
            "    login_page.fill('username', 'standard_user', selector='#user-name')\n"
        )
        result = strip_evidence_from_test_code(code)
        assert "page.locator('#user-name').fill('standard_user')" in result

    def test_converts_pom_fill_without_selector_best_effort(self) -> None:
        code = (
            "def test_01(page, evidence_tracker):\n"
            "    login_page = LoginPage(page, evidence_tracker)\n"
            "    login_page.fill('username', 'admin')\n"
        )
        result = strip_evidence_from_test_code(code)
        assert "page.get_by_label('username').fill('admin')" in result

    def test_evidence_calls_still_converted(self) -> None:
        code = (
            "def test_01(page, evidence_tracker):\n"
            "    evidence_tracker.assert_visible('.modal-body', label='confirmation popup')\n"
            "    expect(page).to_have_url('https://example.com/')\n"
        )
        result = strip_evidence_from_test_code(code)
        assert "expect(page.locator('.modal-body')).to_be_visible()" in result
        assert "to_have_url" in result
