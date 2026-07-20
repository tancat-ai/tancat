"""Tests for the journey_scraper module."""

from __future__ import annotations

from src.cart_seeding_scraper import CartSeedingScraper
from src.journey_auth_detector import (
    detect_auth_redirect as _detect_auth_redirect,
)
from src.journey_auth_detector import (
    detect_captcha as _detect_captcha,
)
from src.journey_auth_detector import (
    detect_mfa as _detect_mfa,
)
from src.journey_auth_detector import (
    detect_sso as _detect_sso,
)
from src.journey_models import CredentialProfile, JourneyResult, JourneyStep, substitute_templates
from src.journey_scraper import (
    JourneyScraper,
)

# Legacy alias for test compatibility
_substitute_templates = substitute_templates


class TestJourneyStep:
    """Tests for JourneyStep dataclass."""

    def test_journey_step_defaults(self) -> None:
        """Test JourneyStep default values."""
        step = JourneyStep(action="navigate", url="https://example.com")
        assert step.action == "navigate"
        assert step.url == "https://example.com"
        assert step.selector is None
        assert step.text is None
        assert step.description == ""
        assert step.timeout_ms == 30_000

    def test_journey_step_with_all_fields(self) -> None:
        """Test JourneyStep with all fields set."""
        step = JourneyStep(
            action="click",
            selector="#myButton",
            description="click button",
            timeout_ms=5000,
        )
        assert step.action == "click"
        assert step.selector == "#myButton"
        assert step.description == "click button"
        assert step.timeout_ms == 5000


class TestCredentialProfile:
    """Tests for CredentialProfile dataclass."""

    def test_credential_profile_creation(self) -> None:
        """Test CredentialProfile basic creation."""
        profile = CredentialProfile(
            label="demo",
            username="test_user",
            password="secret123",
        )
        assert profile.label == "demo"
        assert profile.username == "test_user"
        assert profile.password == "secret123"


class TestJourneyResult:
    """Tests for JourneyResult dataclass."""

    def test_journey_result_creation(self) -> None:
        """Test JourneyResult basic creation."""
        result = JourneyResult(
            success=True,
            captured_pages={"https://example.com": []},
            failed_steps=[],
        )
        assert result.success is True
        assert result.captured_pages == {"https://example.com": []}
        assert result.failed_steps == []
        assert result.error_message is None
        assert result.redirected_urls == []

    def test_journey_result_with_error(self) -> None:
        """Test JourneyResult with error message."""
        result = JourneyResult(
            success=False,
            captured_pages={},
            failed_steps=["Step 1: CAPTCHA detected"],
            error_message="CAPTCHA detected — automated login not supported",
            redirected_urls=["https://example.com/login"],
        )
        assert result.success is False
        assert result.error_message == "CAPTCHA detected — automated login not supported"
        assert len(result.redirected_urls) == 1

    def test_journey_result_to_dict(self) -> None:
        """Test JourneyResult serialization."""
        result = JourneyResult(
            success=True,
            captured_pages={"https://example.com": [{"tag": "div"}]},
            failed_steps=[],
        )
        data = result.to_dict()
        assert data["success"] is True
        assert "https://example.com" in data["captured_pages"]
        assert data["redirected_urls"] == []

    def test_journey_result_from_dict(self) -> None:
        """Test JourneyResult deserialization."""
        data = {
            "success": True,
            "captured_pages": {"https://example.com": [{"tag": "div"}]},
            "failed_steps": [],
            "error_message": None,
            "redirected_urls": [],
        }
        result = JourneyResult.from_dict(data)
        assert result.success is True
        assert "https://example.com" in result.captured_pages
        assert result.error_message is None

    def test_journey_result_round_trip(self) -> None:
        """Test serialize -> deserialize round trip."""
        original = JourneyResult(
            success=False,
            captured_pages={"https://example.com/page": [{"tag": "input", "selector": "#user"}]},
            failed_steps=["Step 2: timeout"],
            error_message="SSO redirect",
            redirected_urls=["https://sso.provider.com"],
        )
        data = original.to_dict()
        restored = JourneyResult.from_dict(data)
        assert restored.success == original.success
        assert restored.captured_pages == original.captured_pages
        assert restored.failed_steps == original.failed_steps
        assert restored.error_message == original.error_message
        assert restored.redirected_urls == original.redirected_urls


# ───────────────────────────────────────────────────────────────
# Detection logic tests
# ───────────────────────────────────────────────────────────────


class TestAuthRedirectDetection:
    """Tests for _detect_auth_redirect."""

    def test_auth_redirect_url_mismatch(self) -> None:
        """Test auth redirect detected when URL domain changes."""
        assert (
            _detect_auth_redirect(
                page_url="https://sso.provider.com/login",
                intended_url="https://example.com/dashboard",
                page_title="Login",
                h1_text="",
            )
            is True
        )

    def test_auth_redirect_same_url_no_keywords(self) -> None:
        """Test no redirect when URL matches and no auth keywords."""
        assert (
            _detect_auth_redirect(
                page_url="https://example.com/dashboard",
                intended_url="https://example.com/dashboard",
                page_title="Dashboard",
                h1_text="Welcome",
            )
            is False
        )

    def test_auth_redirect_login_keyword_in_title(self) -> None:
        """Test redirect detected when title contains 'Login'."""
        assert (
            _detect_auth_redirect(
                page_url="https://example.com/login",
                intended_url="https://example.com/dashboard",
                page_title="Login Page",
                h1_text="",
            )
            is True
        )

    def test_auth_redirect_sign_in_keyword_in_title(self) -> None:
        """Test redirect detected when title contains 'Sign In'."""
        assert (
            _detect_auth_redirect(
                page_url="https://example.com/signin",
                intended_url="https://example.com/dashboard",
                page_title="Sign In",
                h1_text="",
            )
            is True
        )

    def test_auth_redirect_session_expired_in_h1(self) -> None:
        """Test redirect detected when H1 contains 'Session Expired'."""
        assert (
            _detect_auth_redirect(
                page_url="https://example.com/expired",
                intended_url="https://example.com/dashboard",
                page_title="Expired",
                h1_text="Session Expired",
            )
            is True
        )

    def test_auth_redirect_log_in_keyword(self) -> None:
        """Test redirect detected for 'Log In' variant."""
        assert (
            _detect_auth_redirect(
                page_url="https://example.com/auth",
                intended_url="https://example.com/dashboard",
                page_title="Log In",
                h1_text="",
            )
            is True
        )

    def test_auth_redirect_authenticate_keyword(self) -> None:
        """Test redirect detected for 'Authenticate' keyword."""
        assert (
            _detect_auth_redirect(
                page_url="https://example.com/auth",
                intended_url="https://example.com/dashboard",
                page_title="Authenticate",
                h1_text="",
            )
            is True
        )


class TestSSODetection:
    """Tests for _detect_sso."""

    def test_sso_detection_domain_change(self) -> None:
        """Test SSO detected when domain changes."""
        assert (
            _detect_sso(
                base_domain="example.com",
                current_url="https://accounts.google.com/oauth",
            )
            is True
        )

    def test_no_sso_same_domain(self) -> None:
        """Test no SSO when domain stays the same."""
        assert (
            _detect_sso(
                base_domain="example.com",
                current_url="https://example.com/dashboard",
            )
            is False
        )

    def test_no_sso_subdomain_same_base(self) -> None:
        """Test no false positive for same domain."""
        assert (
            _detect_sso(
                base_domain="example.com",
                current_url="https://example.com/login",
            )
            is False
        )


class TestMFADetection:
    """Tests for _detect_mfa."""

    def test_mfa_detection_tel_input(self) -> None:
        """Test MFA detected when page has tel input."""
        html = '<input type="tel" name="code" />'
        assert _detect_mfa(html) is True

    def test_mfa_detection_verification_label(self) -> None:
        """Test MFA detected when page mentions verification code."""
        html = "<label>Enter verification code</label>"
        assert _detect_mfa(html) is True

    def test_mfa_detection_authenticator_label(self) -> None:
        """Test MFA detected when page mentions authenticator."""
        html = "<p>Open your authenticator app</p>"
        assert _detect_mfa(html) is True

    def test_mfa_detection_one_time_label(self) -> None:
        """Test MFA detected for one-time password."""
        html = "<label>One-time password</label>"
        assert _detect_mfa(html) is True

    def test_no_mfa_normal_page(self) -> None:
        """Test no MFA on normal page."""
        html = "<h1>Welcome</h1><p>Please log in.</p>"
        assert _detect_mfa(html) is False


class TestCaptchaDetection:
    """Tests for _detect_captcha."""

    def test_captcha_detection_recaptcha_iframe(self) -> None:
        """Test CAPTCHA detected for reCAPTCHA iframe."""
        html = '<iframe src="https://google.recaptcha.net/android" />'
        assert _detect_captcha(html) is True

    def test_captcha_detection_hcaptcha_iframe(self) -> None:
        """Test CAPTCHA detected for hCaptcha iframe."""
        html = '<iframe src="https://hcaptcha.com/captcha" />'
        assert _detect_captcha(html) is True

    def test_captcha_detection_recaptcha_class(self) -> None:
        """Test CAPTCHA detected for g-recaptcha element."""
        html = '<div class="g-recaptcha"></div>'
        assert _detect_captcha(html) is True

    def test_captcha_detection_hcaptcha_class(self) -> None:
        """Test CAPTCHA detected for h-captcha element."""
        html = '<div class="h-captcha"></div>'
        assert _detect_captcha(html) is True

    def test_captcha_detection_id_containing_captcha(self) -> None:
        """Test CAPTCHA detected when element id contains captcha."""
        html = '<div id="captcha-container"></div>'
        assert _detect_captcha(html) is True

    def test_no_captcha_normal_page(self) -> None:
        """Test no CAPTCHA on normal page."""
        html = '<h1>Welcome</h1><form><input name="user"/></form>'
        assert _detect_captcha(html) is False


class TestTemplateSubstitution:
    """Tests for _substitute_templates."""

    def test_template_substitution_username(self) -> None:
        """Test {{username}} is replaced."""
        profile = CredentialProfile(label="test", username="alice", password="pass123")
        result = _substitute_templates("Hello {{username}}", profile)
        assert result == "Hello alice"

    def test_template_substitution_password(self) -> None:
        """Test {{password}} is replaced."""
        profile = CredentialProfile(label="test", username="alice", password="pass123")
        result = _substitute_templates("Password: {{password}}", profile)
        assert result == "Password: pass123"

    def test_template_substitution_both(self) -> None:
        """Test both placeholders replaced."""
        profile = CredentialProfile(label="test", username="alice", password="pass123")
        result = _substitute_templates("User: {{username}}, Pass: {{password}}", profile)
        assert result == "User: alice, Pass: pass123"

    def test_template_substitution_none_profile(self) -> None:
        """Test no substitution when profile is None."""
        result = _substitute_templates("Hello {{username}}", None)
        assert result == "Hello {{username}}"

    def test_template_substitution_no_placeholders(self) -> None:
        """Test plain text passes through unchanged."""
        profile = CredentialProfile(label="test", username="alice", password="pass123")
        result = _substitute_templates("Just plain text", profile)
        assert result == "Just plain text"


class TestJourneyScraper:
    """Tests for JourneyScraper class."""

    def test_init_default_timeout(self) -> None:
        """Test JourneyScraper default timeout."""
        scraper = JourneyScraper(starting_url="https://example.com")
        assert scraper.starting_url == "https://example.com"
        assert scraper.timeout_ms == 30_000
        assert scraper.max_retries == 2
        assert scraper.headless is True

    def test_init_custom_timeout(self) -> None:
        """Test JourneyScraper with custom timeout."""
        scraper = JourneyScraper(starting_url="https://example.com", timeout_ms=60_000)
        assert scraper.timeout_ms == 60_000

    def test_init_headful_mode(self) -> None:
        """Test JourneyScraper with headful mode."""
        scraper = JourneyScraper(starting_url="https://example.com", headless=False)
        assert scraper.headless is False


class TestCartSeedingScraper:
    """Tests for CartSeedingScraper class."""

    def test_init_basic(self) -> None:
        """Test CartSeedingScraper basic initialization."""
        scraper = CartSeedingScraper(starting_url="https://example.com")
        assert scraper.starting_url == "https://example.com"
        assert scraper.products_url == "https://example.com/products"

    def test_init_with_explicit_products_url(self) -> None:
        """Test CartSeedingScraper with explicit products URL."""
        scraper = CartSeedingScraper(
            starting_url="https://example.com",
            products_url="https://example.com/shop",
        )
        assert scraper.products_url == "https://example.com/shop"

    def test_derive_products_url(self) -> None:
        """Test _derive_products_url static method."""
        assert CartSeedingScraper._derive_products_url("https://example.com/") == "https://example.com/products"
        assert CartSeedingScraper._derive_products_url("https://example.com") == "https://example.com/products"
        assert CartSeedingScraper._derive_products_url("https://example.com/home") == "https://example.com/products"

    def test_ensure_full_url_absolute(self) -> None:
        """Test _ensure_full_url with absolute URL."""
        assert CartSeedingScraper._ensure_full_url("https://example.com/cart") == "https://example.com/cart"

    def test_ensure_full_url_relative(self) -> None:
        """Test _ensure_full_url with relative URL."""
        assert CartSeedingScraper._ensure_full_url("/view_cart") == "/view_cart"

    def test_cart_seed_selectors_exist(self) -> None:
        """Test that CartSeedingScraper has expected selectors."""
        assert len(CartSeedingScraper.PRODUCT_SELECTORS) > 0
        assert len(CartSeedingScraper.ADD_TO_CART_SELECTORS) > 0
        assert len(CartSeedingScraper.CONTINUE_SHOPPING_SELECTORS) > 0

    def test_product_selectors_contain_expected_patterns(self) -> None:
        """Test that product selectors contain expected patterns."""
        selectors = CartSeedingScraper.PRODUCT_SELECTORS
        assert any("[data-product-id]" in s for s in selectors)
        assert any(".product" in s for s in selectors)

    def test_add_to_cart_selectors_contain_expected_patterns(self) -> None:
        """Test that add-to-cart selectors contain expected patterns."""
        selectors = CartSeedingScraper.ADD_TO_CART_SELECTORS
        assert any("add-to-cart" in s for s in selectors)
        assert any("submit" in s for s in selectors)
