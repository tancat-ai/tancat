"""Tests for the journey_scraper module."""

from __future__ import annotations

from src.journey_scraper import CartSeedingScraper, JourneyScraper, JourneyStep


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
        assert any("Shop Now" in s for s in selectors)

    def test_add_to_cart_selectors_contain_expected_patterns(self) -> None:
        """Test that add-to-cart selectors contain expected patterns."""
        selectors = CartSeedingScraper.ADD_TO_CART_SELECTORS
        assert any("Add to cart" in s for s in selectors)
        assert any('button:has-text("Add to cart")' in s for s in selectors)
