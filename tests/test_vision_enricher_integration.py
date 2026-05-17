"""Integration tests for the vision enrichment pipeline."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

from PIL import Image

from src.scraper import ScrapeResult, scrape_with_enrichment
from src.vision_enricher import VisionEnricher


def _make_image(width: int = 100, height: int = 100) -> bytes:
    """Create a test PNG image in memory."""
    image = Image.new("RGB", (width, height), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _element_with_bbox() -> dict[str, Any]:
    """Return a representative scraped element with a crop bbox."""
    return {
        "tag": "button",
        "text": "Add to Cart",
        "attributes": {"data-test": "add-to-cart"},
        "_bbox": {"x": 5.0, "y": 5.0, "width": 40.0, "height": 20.0},
    }


class TestVisionEnricherFullPipeline:
    """Test full enrichment pipeline with mocked LLM calls."""

    def test_enrich_elements_calls_vision_llm(self) -> None:
        """Enrichment should call create_vision_completion for each element."""
        mock_client = MagicMock()
        mock_client.create_vision_completion.return_value = "{}"

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            VisionEnricher.enrich_elements([_element_with_bbox()], _make_image(), "ollama", "qwen2.5-vl")

        mock_client.create_vision_completion.assert_called_once()

    def test_enrich_elements_stores_metadata_in_elements(self) -> None:
        """Enriched elements should have product metadata fields."""
        mock_client = MagicMock()
        mock_client.create_vision_completion.return_value = json.dumps(
            {
                "product_name": "Sauce Labs Backpack",
                "price": "$29.99",
                "description": "Backpack product card",
                "visual_label": "add to cart button",
                "enrichment_note": "Product context is visible",
            }
        )

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            result = VisionEnricher.enrich_elements([_element_with_bbox()], _make_image(), "ollama", "qwen2.5-vl")

        assert result[0]["product_name"] == "Sauce Labs Backpack"
        assert result[0]["price"] == "$29.99"
        assert result[0]["description"] == "Backpack product card"
        assert result[0]["_enriched"] is True

    def test_enrich_elements_handles_llm_timeout(self) -> None:
        """Timeout should not crash; element is kept with an error note."""
        mock_client = MagicMock()
        mock_client.create_vision_completion.side_effect = TimeoutError("vision timed out")

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            result = VisionEnricher.enrich_elements([_element_with_bbox()], _make_image(), "ollama", "qwen2.5-vl")

        assert result[0]["text"] == "Add to Cart"
        assert result[0]["_enriched"] is False
        assert result[0]["_enrichment_error"] == "vision timed out"

    def test_enrich_elements_handles_garbled_llm_response(self) -> None:
        """Garbled response should not crash and should keep None metadata values."""
        mock_client = MagicMock()
        mock_client.create_vision_completion.return_value = "not json"

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            result = VisionEnricher.enrich_elements([_element_with_bbox()], _make_image(), "ollama", "qwen2.5-vl")

        assert result[0]["product_name"] is None
        assert result[0]["price"] is None
        assert result[0]["_enriched"] is True

    def test_enrich_elements_returns_unchanged_for_non_vision_model(self) -> None:
        """Non-vision models should return elements unchanged."""
        elements = [_element_with_bbox()]
        result = VisionEnricher.enrich_elements(elements, _make_image(), "ollama", "qwen3.5:35b")

        assert result == elements
        assert "_enriched" not in result[0]

    def test_enrich_elements_handles_empty_elements(self) -> None:
        """Empty element list should return empty list."""
        assert VisionEnricher.enrich_elements([], _make_image(), "ollama", "qwen2.5-vl") == []

    def test_enrich_elements_handles_empty_screenshot(self) -> None:
        """Empty screenshot bytes should return elements unchanged."""
        elements = [_element_with_bbox()]
        result = VisionEnricher.enrich_elements(elements, b"", "ollama", "qwen2.5-vl")

        assert result == elements
        assert "_enriched" not in result[0]

    def test_scrape_with_enrichment_enriches_scrape_results(self) -> None:
        """Scraper integration should attach bbox data and enrich result elements."""
        result = ScrapeResult(
            url="https://example.com",
            elements=[{"selector": "#add", "tag": "button", "text": "Add"}],
            screenshot_bytes=_make_image(),
            element_boxes=[
                {
                    "selector": "#add",
                    "bbox": {"x": 0.0, "y": 0.0, "width": 20.0, "height": 20.0},
                    "element_index": 0,
                    "is_visible": True,
                }
            ],
        )
        mock_client = MagicMock()
        mock_client.create_vision_completion.return_value = json.dumps({"visual_label": "add button"})

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            enriched = scrape_with_enrichment([result], "ollama", "qwen2.5-vl")

        assert enriched[0].elements[0]["_bbox"] == {"x": 0.0, "y": 0.0, "width": 20.0, "height": 20.0}
        assert enriched[0].elements[0]["visual_label"] == "add button"
        assert enriched[0].elements[0]["_enriched"] is True

    def test_scrape_with_enrichment_skips_non_vision_model(self) -> None:
        """Scraper integration should skip unchanged when model is not vision capable."""
        result = ScrapeResult(
            url="https://example.com", elements=[{"selector": "#add"}], screenshot_bytes=_make_image()
        )

        assert scrape_with_enrichment([result], "ollama", "qwen3.5:35b") == [result]


class TestVisionEnricherPromptBuilding:
    """Test vision prompt construction."""

    def test_prompt_includes_element_type(self) -> None:
        """Prompt should include element tag type."""
        prompt = VisionEnricher._build_vision_prompt({"tag": "button"})
        assert "button element" in prompt

    def test_prompt_includes_text_content(self) -> None:
        """Prompt should include element text content."""
        prompt = VisionEnricher._build_vision_prompt({"text": "Add to Cart"})
        assert "Add to Cart" in prompt

    def test_prompt_includes_attributes(self) -> None:
        """Prompt should include element attributes."""
        prompt = VisionEnricher._build_vision_prompt({"attributes": {"data-test": "add"}})
        assert "data-test" in prompt

    def test_prompt_requests_json_output(self) -> None:
        """Prompt should request structured JSON output."""
        prompt = VisionEnricher._build_vision_prompt({})
        assert "Return ONLY a JSON object" in prompt
        assert "product_name" in prompt
