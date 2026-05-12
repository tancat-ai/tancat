"""Tests for the UrlResolver module (keyword → URL mapping)."""

from src.url_resolver import UrlResolver, resolve_keywords_to_urls

# ------------------------------------------------------------------
# build_mapping
# ------------------------------------------------------------------


def test_build_mapping_maps_seed_url_to_home() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["cart"],
        scraped_urls=["https://www.saucedemo.com/inventory.html"],
        seed_url="https://www.saucedemo.com/",
    )
    assert resolver.resolve("home") == "https://www.saucedemo.com/"
    assert resolver.resolve("login") == "https://www.saucedemo.com/"
    assert resolver.resolve("homepage") == "https://www.saucedemo.com/"


def test_build_mapping_matches_keyword_to_scraped_url_path() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["cart", "checkout"],
        scraped_urls=[
            "https://www.saucedemo.com/",
            "https://www.saucedemo.com/cart.html",
            "https://www.saucedemo.com/checkout-step-one",
        ],
        seed_url="https://www.saucedemo.com/",
    )
    assert resolver.resolve("cart") == "https://www.saucedemo.com/cart.html"
    assert resolver.resolve("checkout") == "https://www.saucedemo.com/checkout-step-one"


def test_build_mapping_substring_match() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["checkout overview"],
        scraped_urls=[
            "https://www.saucedemo.com/checkout-overview",
        ],
        seed_url="https://www.saucedemo.com/",
    )
    # "checkout" is in "/checkout-overview"
    assert resolver.resolve("checkout overview") == "https://www.saucedemo.com/checkout-overview"


def test_build_mapping_no_match_returns_none() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["nonexistent-page"],
        scraped_urls=[
            "https://www.saucedemo.com/",
            "https://www.saucedemo.com/cart.html",
        ],
        seed_url="https://www.saucedemo.com/",
    )
    assert resolver.resolve("nonexistent-page") is None


def test_build_mapping_skips_already_mapped_keywords() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["home", "cart"],
        scraped_urls=[
            "https://www.saucedemo.com/cart.html",
        ],
        seed_url="https://www.saucedemo.com/",
    )
    # "home" should still map to seed URL, not cart
    assert resolver.resolve("home") == "https://www.saucedemo.com/"
    assert resolver.resolve("cart") == "https://www.saucedemo.com/cart.html"


def test_exact_match_prefers_html_route_over_bare_static_guess() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["cart"],
        scraped_urls=[
            "https://www.saucedemo.com/cart",
            "https://www.saucedemo.com/cart.html",
        ],
        seed_url="https://www.saucedemo.com/",
    )

    assert resolver.resolve("cart") == "https://www.saucedemo.com/cart.html"


def test_build_mapping_with_concepts_generates_candidates() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["products", "cart"],
        scraped_urls=[],  # No scraped URLs — should use common path candidates
        seed_url="https://www.example.com/",
        concepts=["products", "cart"],
    )
    # Should generate common path candidates
    assert resolver.resolve("products") is not None
    assert resolver.resolve("cart") is not None


# ------------------------------------------------------------------
# resolve
# ------------------------------------------------------------------


def test_resolve_case_insensitive() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["Cart"],
        scraped_urls=["https://www.example.com/cart.html"],
        seed_url="https://www.example.com/",
    )
    assert resolver.resolve("cart") == "https://www.example.com/cart.html"
    assert resolver.resolve("CART") == "https://www.example.com/cart.html"
    assert resolver.resolve("Cart") == "https://www.example.com/cart.html"


def test_resolve_partial_keyword_match() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["checkout"],
        scraped_urls=["https://www.example.com/checkout-step-one"],
        seed_url="https://www.example.com/",
    )
    # Partial match: "checkout page" contains "checkout"
    assert resolver.resolve("checkout page") == "https://www.example.com/checkout-step-one"


# ------------------------------------------------------------------
# get_seed_url
# ------------------------------------------------------------------


def test_get_seed_url_returns_seed() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=[],
        scraped_urls=[],
        seed_url="https://www.example.com/",
    )
    assert resolver.get_seed_url() == "https://www.example.com/"


# ------------------------------------------------------------------
# get_all_mappings
# ------------------------------------------------------------------


def test_get_all_mappings_returns_copy() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["cart"],
        scraped_urls=["https://www.example.com/cart.html"],
        seed_url="https://www.example.com/",
    )
    mappings = resolver.get_all_mappings()
    assert "home" in mappings
    assert "cart" in mappings
    # Mutating the returned dict should not affect internal state
    mappings["fake"] = "https://fake.com/"
    assert "fake" not in resolver.get_all_mappings()


# ------------------------------------------------------------------
# resolve_keywords_to_urls convenience function
# ------------------------------------------------------------------


def test_resolve_keywords_to_urls_returns_configured_resolver() -> None:
    resolver = resolve_keywords_to_urls(
        keywords=["cart"],
        scraped_urls=["https://www.example.com/cart.html"],
        seed_url="https://www.example.com/",
    )
    assert resolver.resolve("cart") == "https://www.example.com/cart.html"
    assert resolver.resolve("home") == "https://www.example.com/"


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


def test_empty_keywords_and_urls() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=[],
        scraped_urls=[],
        seed_url="https://www.example.com/",
    )
    assert resolver.resolve("home") == "https://www.example.com/"
    assert resolver.resolve("nonexistent") is None


def test_url_with_query_params() -> None:
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["cart"],
        scraped_urls=["https://www.example.com/cart?item=1"],
        seed_url="https://www.example.com/",
    )
    # Should still match "cart" from path
    assert resolver.resolve("cart") == "https://www.example.com/cart?item=1"


def test_multiple_urls_exact_segment_match_before_prefix() -> None:
    """Exact segment match takes priority over prefix match.

    'product' matches /product/123 exactly (segment 'product'), while /products
    only matches as a prefix. Exact match should win.
    """
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["product"],
        scraped_urls=[
            "https://www.example.com/products",
            "https://www.example.com/product/123",
        ],
        seed_url="https://www.example.com/",
    )
    # Exact segment match wins over prefix match
    assert resolver.resolve("product") == "https://www.example.com/product/123"


def test_prefix_match_returns_first_candidate() -> None:
    """When only prefix matches exist, return the first scraped URL that matches."""
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["product"],
        scraped_urls=[
            "https://www.example.com/products",
            "https://www.example.com/products/123",
        ],
        seed_url="https://www.example.com/",
    )
    # Both are prefix matches; first URL in scraped list wins
    assert resolver.resolve("product") == "https://www.example.com/products"
