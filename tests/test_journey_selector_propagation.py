"""Tests for journey selector propagation into the resolver element pool."""

from __future__ import annotations

from typing import Any

from src.orchestrator import TestOrchestrator
from src.placeholder_resolver import PlaceholderResolver


class TestExtractJourneySelectors:
    """Test synthetic resolver entries built from journey-discovered selectors."""

    def test_extracts_selectors_from_scraped_data(self) -> None:
        """Journey selectors should be extracted from all_scraped_data."""
        orchestrator = TestOrchestrator.__new__(TestOrchestrator)
        all_scraped: dict[str, list[dict[str, Any]]] = {
            "https://example.com": [
                {
                    "selector": "#login-button",
                    "text": "Login",
                    "role": "button",
                    "href": "",
                    "aria_label": "",
                    "accessible_name": "",
                    "is_visible": True,
                },
            ]
        }

        result = orchestrator._extract_journey_selectors(all_scraped)

        assert "https://example.com" in result
        assert result["https://example.com"][0]["selector"] == "#login-button"
        assert result["https://example.com"][0]["_journey_discovered"] == "true"

    def test_skips_elements_without_selector(self) -> None:
        """Elements with no selector should be skipped."""
        orchestrator = TestOrchestrator.__new__(TestOrchestrator)
        all_scraped: dict[str, list[dict[str, Any]]] = {
            "https://example.com": [
                {"selector": "", "text": "empty"},
                {
                    "selector": "#btn",
                    "text": "Button",
                    "role": "button",
                    "href": "",
                    "aria_label": "",
                    "accessible_name": "",
                    "is_visible": True,
                },
            ]
        }

        result = orchestrator._extract_journey_selectors(all_scraped)

        assert len(result["https://example.com"]) == 1
        assert result["https://example.com"][0]["selector"] == "#btn"

    def test_empty_scraped_data_returns_empty(self) -> None:
        """Empty input should return empty dict."""
        orchestrator = TestOrchestrator.__new__(TestOrchestrator)

        result = orchestrator._extract_journey_selectors({})

        assert result == {}

    def test_preserves_text_and_role_fields(self) -> None:
        """Extracted elements should preserve text and role fields."""
        orchestrator = TestOrchestrator.__new__(TestOrchestrator)
        all_scraped: dict[str, list[dict[str, Any]]] = {
            "https://example.com": [
                {
                    "selector": "#checkout",
                    "text": "Checkout",
                    "role": "button",
                    "href": "",
                    "aria_label": "",
                    "accessible_name": "Checkout",
                    "is_visible": True,
                },
            ]
        }

        result = orchestrator._extract_journey_selectors(all_scraped)
        element = result["https://example.com"][0]

        assert element["text"] == "Checkout"
        assert element["role"] == "button"
        assert element["accessible_name"] == "Checkout"


class TestJourneySelectorScoring:
    """Test resolver scoring for journey-discovered selectors."""

    def test_journey_discovered_element_gets_score_bonus(self) -> None:
        """Journey-discovered elements should beat otherwise identical candidates."""
        resolver = PlaceholderResolver()
        elements = [
            {"selector": "#checkout-static", "text": "Checkout", "role": "button", "id": "checkout-static"},
            {
                "selector": "#checkout-journey",
                "text": "Checkout",
                "role": "button",
                "id": "checkout-journey",
                "_journey_discovered": "true",
            },
        ]

        ranked = resolver.rank_candidates("CLICK", "checkout button", elements)

        assert ranked[0][1]["selector"] == "#checkout-journey"
        assert ranked[0][0] == ranked[1][0] + 5
