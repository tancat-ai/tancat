"""Regression tests for AI-037 semantic/locator/matcher/scorer fixes."""

from __future__ import annotations

from typing import Any

from src.element_matcher import ElementMatcher
from src.locator_builder import build_robust_locator
from src.placeholder_resolver import PlaceholderResolver
from src.placeholder_scorers import PlaceholderScorer
from src.semantic_matcher import SemanticMatcher

# ---------------------------------------------------------------------------
# SemanticMatcher — camelCase splitting in get_words()
# ---------------------------------------------------------------------------


class TestCamelCaseSplitInGetWords:
    def test_vehicle_reg_splits_into_reg(self) -> None:
        words = SemanticMatcher.get_words("vehicleReg")
        assert "reg" in words
        assert "vehicle" in words

    def test_usage_type_splits(self) -> None:
        words = SemanticMatcher.get_words("usageType")
        assert "usage" in words
        assert "type" in words

    def test_plain_words_unchanged(self) -> None:
        words = SemanticMatcher.get_words("password")
        assert "password" in words
        assert "pass" in words  # existing stem expansion preserved


# ---------------------------------------------------------------------------
# LocatorBuilder — radio/checkbox name+value
# ---------------------------------------------------------------------------


class TestRadioLocator:
    def test_radio_with_name_and_value(self) -> None:
        element = {
            "role": "radio",
            "name": "usageType",
            "value": "SDP",
            "text": "",
            "id": "",
            "aria_label": "",
            "selector": 'input[name="usageType"][value="SDP"]',
        }
        assert build_robust_locator(element) == 'input[name="usageType"][value="SDP"]'

    def test_radio_with_name_only(self) -> None:
        element = {
            "role": "radio",
            "name": "usageType",
            "value": "",
            "text": "",
            "id": "",
            "aria_label": "",
        }
        assert build_robust_locator(element) == 'input[name="usageType"]'

    def test_id_still_preferred_over_radio_format(self) -> None:
        element = {"role": "radio", "id": "pref", "name": "usageType", "value": "SDP", "text": ""}
        assert build_robust_locator(element) == "#pref"


# ---------------------------------------------------------------------------
# ElementMatcher — Pass 1 skips synthetic ARIA containers
# ---------------------------------------------------------------------------


class TestPass1SyntheticSkip:
    def _matcher(self) -> ElementMatcher:
        return ElementMatcher(PlaceholderResolver(), generator=None)

    def test_synthetic_group_not_matched_for_click(self) -> None:
        """A synthetic container must not win Pass 1 over a real target."""
        matcher = self._matcher()
        elements: list[dict[str, Any]] = [
            {
                "id": "vehicle_usage",
                "text": "Vehicle Usage",
                "accessible_name": "Vehicle Usage",
                "role": "group",
                "synthetic_id": True,
                "selector": "#vehicle_usage",
            },
            {
                "id": "",
                "name": "usageType",
                "value": "SDP",
                "text": "",
                "accessible_name": "Social, Domestic & Pleasure",
                "role": "radio",
                "selector": 'input[name="usageType"][value="SDP"]',
            },
        ]
        result = matcher.pass1_text_match("CLICK", "usage type", {"p": elements})
        assert result is None  # radio has no text → Pass 1 correctly falls through


# ---------------------------------------------------------------------------
# PlaceholderScorer — proportional text bonus + synthetic container exclusion
# ---------------------------------------------------------------------------


class TestTextContentBonus:
    def test_proportional_reward_for_more_overlapping_tokens(self) -> None:
        desc = "compulsory excess information"
        weak = {"text": "Voluntary Excess"}  # 1 overlapping token
        strong = {"text": "Compulsory Excess: £250 minimum amount"}  # 2 overlapping tokens
        weak_score = PlaceholderScorer._text_content_bonus(desc, weak)
        strong_score = PlaceholderScorer._text_content_bonus(desc, strong)
        assert strong_score > weak_score

    def test_punctuation_normalised(self) -> None:
        desc = "compulsory excess information"
        element = {"text": "Compulsory Excess: £250 this is the minimum amount"}
        assert PlaceholderScorer._text_content_bonus(desc, element) > 5


class TestSyntheticContainerBonus:
    def test_synthetic_container_gets_no_click_bonus(self) -> None:
        synthetic = {"role": "group", "computed_role": "group", "id": "add_vehicle", "synthetic_id": True}
        real = {"role": "group", "computed_role": "group", "id": "real_div"}
        synthetic_bonus = PlaceholderScorer._click_role_bonus("CLICK", synthetic)
        real_bonus = PlaceholderScorer._click_role_bonus("CLICK", real)
        assert synthetic_bonus < real_bonus

    def test_radio_role_gets_click_bonus(self) -> None:
        radio = {"role": "radio", "id": "", "text": ""}
        assert PlaceholderScorer._click_role_bonus("CLICK", radio) >= 3
