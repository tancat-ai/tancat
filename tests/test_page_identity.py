"""The page-identity rule and the story-named-query exception (t-0937).

Identity is scheme + host + path, so a query difference alone is the same page.
A story that names the bit after the ``?`` pins the query instead. The rule
lives in ``src/page_identity.py``; these tests hold both directions.
"""

from __future__ import annotations

from src.page_identity import query_pairs, same_page, story_pins_query, story_query_pairs

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
    assert story_pins_query("Filter: color=blue&size=large", CART + "?color=blue&size=large")


def test_story_full_url_pins_the_query() -> None:
    assert story_pins_query(f"Open {CART}?item=blue-top and check the cart.", CART + "?item=blue-top")


def test_story_cannot_pin_a_candidate_with_no_query() -> None:
    assert not story_pins_query("The cart URL must contain item=blue-top.", CART)


def test_query_pair_extraction_ignores_prose_punctuation() -> None:
    pairs = story_query_pairs("Expect item=blue-top, then size=large.")
    assert ("item", "blue-top") in pairs
    assert ("size", "large") in pairs
    assert not any(key == "then" for key, _ in pairs)


def test_query_pairs_reads_the_candidate_query() -> None:
    assert query_pairs(CART + "?item=blue-top&empty=") == {("item", "blue-top"), ("empty", "")}
