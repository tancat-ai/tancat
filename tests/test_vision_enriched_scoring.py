"""Tests for AI-027 vision-enriched scoring in PlaceholderScorer."""

from __future__ import annotations

from typing import Any

from src.placeholder_scorers import PlaceholderScorer

# ---------------------------------------------------------------------------
# _vision_enriched_bonus
# ---------------------------------------------------------------------------


class TestVisionEnrichedBonus:
    """Verify that vision-enriched fields boost element scores."""

    def _element(self, **overrides: Any) -> dict[str, Any]:
        return {
            "selector": "#test",
            "text": "Add to cart",
            "_enriched": False,
            **overrides,
        }

    def test_no_bonus_when_not_enriched(self) -> None:
        elem = self._element(product_name="Sauce Labs Backpack")
        score = PlaceholderScorer._vision_enriched_bonus("CLICK", "Sauce Labs Backpack add to cart", elem)
        assert score == 0

    def test_no_bonus_when_no_enrichment_fields(self) -> None:
        elem = self._element(_enriched=True)
        score = PlaceholderScorer._vision_enriched_bonus("CLICK", "add to cart", elem)
        assert score == 0

    def test_product_name_word_match(self) -> None:
        elem = self._element(
            _enriched=True,
            product_name="Sauce Labs Backpack",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "Sauce Labs Backpack add to cart",
            elem,
        )
        # 3 word overlap (sauce, labs, backpack) * 5 = 15
        assert score >= 15

    def test_product_name_exact_match(self) -> None:
        elem = self._element(
            _enriched=True,
            product_name="Sauce Labs Backpack",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "click Sauce Labs Backpack in the cart",
            elem,
        )
        # Exact substring match triggers +10
        assert score >= 10

    def test_visual_label_bonus(self) -> None:
        elem = self._element(
            _enriched=True,
            visual_label="backpack product image",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "backpack product",
            elem,
        )
        # 2 word overlap * 2 = 4
        assert score >= 4

    def test_enrichment_note_bonus(self) -> None:
        elem = self._element(
            _enriched=True,
            enrichment_note="product card for backpack",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "product backpack",
            elem,
        )
        # 2 word overlap * 1 = 2
        assert score >= 2

    def test_vision_description_bonus(self) -> None:
        elem = self._element(
            _enriched=True,
            description="blue t-shirt product",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "blue t-shirt product add to cart",
            elem,
        )
        # 3 word overlap * 2 = 6
        assert score >= 6

    def test_combined_fields_stack(self) -> None:
        elem = self._element(
            _enriched=True,
            product_name="Red Fleece",
            visual_label="fleece jacket image",
            enrichment_note="product card",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "Red Fleece jacket product",
            elem,
        )
        # product_name: "red fleece" overlap = 2 * 5 = 10
        # visual_label: "fleece" overlap = 1 * 2 = 2
        # enrichment_note: "product" overlap = 1 = 1
        assert score >= 13

    def test_price_mention_bonus(self) -> None:
        elem = self._element(
            _enriched=True,
            price="$29.99",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "ASSERT",
            "verify the price is correct",
            elem,
        )
        # price present + "price" in description = +3
        assert score >= 3

    def test_no_price_bonus_when_not_mentioned(self) -> None:
        elem = self._element(
            _enriched=True,
            price="$29.99",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "add to cart button",
            elem,
        )
        # No price-related terms in description
        assert score == 0

    def test_null_fields_treated_as_empty(self) -> None:
        elem = self._element(
            _enriched=True,
            product_name=None,
            visual_label=None,
            enrichment_note=None,
            price=None,
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "some description",
            elem,
        )
        assert score == 0

    def test_case_insensitive(self) -> None:
        elem = self._element(
            _enriched=True,
            product_name="SAUCE LABS BACKPACK",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "sauce labs backpack",
            elem,
        )
        assert score > 0

    def test_single_word_overlap_not_enough_for_high_score(self) -> None:
        elem = self._element(
            _enriched=True,
            product_name="Cart",
        )
        score = PlaceholderScorer._vision_enriched_bonus(
            "CLICK",
            "view cart link",
            elem,
        )
        # 1 word overlap only — doesn't trigger 2-word threshold for *5 bonus
        # but "cart" is in "view cart link" so exact substring match triggers +10
        assert score == 10
