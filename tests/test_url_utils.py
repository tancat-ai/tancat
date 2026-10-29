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


def test_no_fixed_route_table_survives_in_url_utils() -> None:
    """t-0877: the invented-address helpers are gone, not just unused.

    These two tests used to pin ``build_common_path_candidates`` (a fixed route
    table that turned story concepts into /cart.html, /view_cart, /basket,
    /inventory.html ... on the seed domain) and its empty-input edges. The
    owner's rule (2026-10-23) deleted the whole path: "if its not something a
    real user would have then its not accurate testing behaviour". Inverted
    rather than dropped, so a future re-introduction fails here.
    """
    import src.url_utils as url_utils

    assert not hasattr(url_utils, "build_common_path_candidates")
    assert not hasattr(url_utils, "heuristic_url_from_description")


def test_concept_extraction_remains_but_creates_no_urls() -> None:
    """Concepts still name routes discovery looks for; they never build one."""
    from src.url_utils import extract_route_concepts

    concepts = extract_route_concepts(["add a product to the cart and check out"])
    assert {"products", "cart", "checkout"} <= concepts
    # A concept is a word, never an address.
    assert all("/" not in concept and "." not in concept for concept in concepts)


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
