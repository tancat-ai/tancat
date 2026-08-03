"""Tests for pure URL-path helpers in src/url_utils.py."""

from src.url_utils import is_stateful_cart_checkout_path, normalize_url_path


def test_cart_checkout_paths_are_stateful() -> None:
    """Cart/checkout paths need session state regardless of site vocabulary."""
    assert is_stateful_cart_checkout_path("/view_cart") is True
    assert is_stateful_cart_checkout_path("/cart") is True
    assert is_stateful_cart_checkout_path("/cart.html") is True
    assert is_stateful_cart_checkout_path("/checkout") is True
    assert is_stateful_cart_checkout_path("/checkout-step-one.html") is True
    assert is_stateful_cart_checkout_path("/checkout-step-two.html") is True
    assert is_stateful_cart_checkout_path("/checkout-complete.html") is True
    assert is_stateful_cart_checkout_path("/basket") is True


def test_non_cart_paths_are_not_stateful() -> None:
    assert is_stateful_cart_checkout_path("/") is False
    assert is_stateful_cart_checkout_path("") is False
    assert is_stateful_cart_checkout_path("/inventory.html") is False
    assert is_stateful_cart_checkout_path("/products") is False
    assert is_stateful_cart_checkout_path("/product_details/1") is False
    assert is_stateful_cart_checkout_path("/login") is False


def test_path_matching_is_case_insensitive() -> None:
    assert is_stateful_cart_checkout_path("/Cart.html") is True
    assert is_stateful_cart_checkout_path("/CHECKOUT") is True


def test_normalize_url_path_still_works() -> None:
    assert normalize_url_path("category-product/1") == "category_products/1"
    assert normalize_url_path("") == ""


def test_build_common_path_candidates_concept_driven_and_same_domain() -> None:
    """Candidates come from the shared route vocabulary, scoped to the seed domain."""
    from src.url_utils import build_common_path_candidates

    candidates = build_common_path_candidates(["https://www.saucedemo.com/"], {"cart", "checkout", "products"})
    assert "https://www.saucedemo.com/cart.html" in candidates
    assert "https://www.saucedemo.com/checkout-step-one.html" in candidates
    assert "https://www.saucedemo.com/inventory.html" in candidates
    # Same-domain only — never other hosts
    assert all("saucedemo.com" in c for c in candidates)


def test_build_common_path_candidates_empty_inputs() -> None:
    from src.url_utils import build_common_path_candidates

    assert build_common_path_candidates([], {"cart"}) == []
    assert build_common_path_candidates(["https://example.com/"], set()) == []
    assert build_common_path_candidates(["https://example.com/"], {"home"}) == []


def test_alias_match_products_to_inventory() -> None:
    """Saucedemo names its product page /inventory.html — generic alias handles it."""
    from src.url_resolver import UrlResolver

    urls = [
        "https://www.saucedemo.com/",
        "https://www.saucedemo.com/cart.html",
        "https://www.saucedemo.com/inventory.html",
    ]
    assert UrlResolver._match_keyword_to_url("products", urls) == "https://www.saucedemo.com/inventory.html"
    assert UrlResolver._match_keyword_to_url("cart", urls) == "https://www.saucedemo.com/cart.html"
    assert UrlResolver._match_keyword_to_url("products", ["https://shop.example.com/catalog"]) == (
        "https://shop.example.com/catalog"
    )
