"""The page-identity rule and the story-named-query exception (t-0937).

Identity is scheme + host + path, so a query difference alone is the same page.
A story that names the bit after the ``?`` pins the query instead. The rule
lives in ``src/page_identity.py``; these tests hold both directions.
"""

from __future__ import annotations

from src.page_identity import (
    carries_story_query,
    query_pairs,
    same_page,
    story_pins_query,
    story_query_pairs,
    story_query_url,
)

CART = "https://shop.example.com/cart.html"


def test_query_difference_is_the_same_page_by_default() -> None:
    assert same_page(CART + "?item=blue-top", CART + "?item=red-top")
    assert same_page(CART, CART + "?item=red-top")


def test_different_path_is_not_the_same_page() -> None:
    assert not same_page(CART, "https://shop.example.com/checkout.html")


def test_story_that_names_no_query_does_not_pin() -> None:
    assert not story_pins_query("Open the cart page and check the item.", CART + "?item=blue-top")
    assert not story_pins_query("The cart shows the blue-top variant.", CART + "?item=blue-top")


def test_story_that_names_the_query_pair_pins_it() -> None:
    assert story_pins_query("The cart URL must contain item=blue-top.", CART + "?item=blue-top")
    assert story_pins_query("Filter: /products?color=blue&size=large", CART + "?color=blue&size=large")


def test_path_token_pins_the_query() -> None:
    assert story_pins_query("the shopper opens /cart?item=blue-top", CART + "?item=red-top")
    assert story_query_pairs("the shopper opens /cart?item=blue-top") == {("item", "blue-top")}


def test_pair_after_a_path_token_pins_the_query() -> None:
    assert story_pins_query("the shopper opens /cart with item=blue-top", CART)


def test_bare_pair_in_prose_does_not_pin() -> None:
    assert not story_pins_query("the receipt shows total=10", CART)
    assert story_query_pairs("the receipt shows total=10") == set()
    assert story_query_url("the receipt shows total=10", CART) is None


def test_a_url_elsewhere_in_the_sentence_does_not_pin_a_prose_pair() -> None:
    story = "The URL is /cart and the receipt shows total=10"
    assert not story_pins_query(story, CART)
    assert story_query_pairs(story) == set()

    # "and" only chains to another query pair, never to a bare prose pair.
    assert story_query_pairs("The URL is /cart and total=10") == set()


def test_a_cue_before_the_pair_pins_it() -> None:
    assert story_pins_query("the page address is item=blue-top", CART)
    story = "the cart URL must contain item=blue-top and size=large"
    assert story_query_pairs(story) == {("item", "blue-top"), ("size", "large")}


def test_story_full_url_pins_the_query() -> None:
    assert story_pins_query(f"Open {CART}?item=blue-top and check the cart.", CART + "?item=blue-top")


def test_story_pins_even_when_the_candidate_has_no_query() -> None:
    assert story_pins_query("The cart URL must contain item=blue-top.", CART)


def test_story_query_url_uses_the_story_pair_not_the_candidate_query() -> None:
    assert story_query_url("The cart URL must contain item=blue-top.", CART + "?item=red-top") == (
        CART + "?item=blue-top"
    )
    assert story_query_url("The cart URL must contain item=blue-top.", CART) == CART + "?item=blue-top"


def test_story_full_url_is_the_expected_url() -> None:
    story = "Open https://shop.example.com/cart.html?item=blue-top and check the cart."
    assert story_query_url(story, CART + "?item=red-top") == "https://shop.example.com/cart.html?item=blue-top"


def test_carries_story_query_allows_extra_tracking_parameters() -> None:
    expected = CART + "?item=blue-top"
    assert carries_story_query(CART + "?item=blue-top", expected)
    assert carries_story_query(CART + "?item=blue-top&utm_source=x", expected)
    assert not carries_story_query(CART + "?item=red-top", expected)
    assert not carries_story_query(CART, expected)
    assert not carries_story_query("https://shop.example.com/checkout.html?item=blue-top", expected)


def test_query_pair_extraction_ignores_prose_punctuation() -> None:
    pairs = story_query_pairs("Expect /cart?item=blue-top, then /cart?size=large.")
    assert ("item", "blue-top") in pairs
    assert ("size", "large") in pairs
    assert not any(key == "then" for key, _ in pairs)


def test_query_pairs_reads_the_candidate_query() -> None:
    assert query_pairs(CART + "?item=blue-top&empty=") == {("item", "blue-top"), ("empty", "")}
