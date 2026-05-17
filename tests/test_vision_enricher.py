"""Tests for src/vision_enricher.py.

Covers:
- is_vision_capable() detection logic
- crop_element_from_screenshot() edge cases
- _parse_enrichment_response() JSON and fallback parsing
- enrich_elements() graceful degradation when no vision model
- VISION_MODEL_PATTERNS coverage
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.vision_enricher import VisionEnricher

# ---------------------------------------------------------------------------
# Helpers to create tiny test images
# ---------------------------------------------------------------------------


def _make_image(width: int = 100, height: int = 100, color: tuple = (255, 255, 255)) -> bytes:
    """Create a small solid-color PNG image in memory."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# is_vision_capable
# ---------------------------------------------------------------------------


class TestIsVisionCapable:
    """Test vision model name pattern detection."""

    @pytest.mark.parametrize(
        "model",
        [
            "qwen2.5-vl",
            "qwen3.0-vl",
            "qwen3.6-35b-a3b",
            "qwen3.6-35b-a3b-instruct",
            "llava",
            "llava-1.5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt_4_vision",
            "gemini-pro-vision",
            "gemini-2.0-flash",
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku",
            "glm-4v",
            "internvl",
            "llama-3.2-vl",
            "llama-3.2-vision",
            "my-vision-model",
            "test-vl",
            "test-mm",
        ],
    )
    def test_returns_true_for_known_vision_models(self, model: str) -> None:
        assert VisionEnricher.is_vision_capable("ollama", model) is True
        assert VisionEnricher.is_vision_capable("lm-studio", model) is True
        assert VisionEnricher.is_vision_capable("openai", model) is True

    @pytest.mark.parametrize(
        "model",
        [
            "qwen2.5:7b",
            "qwen3.5:35b",
            "llama2",
            "mistral",
            "gpt-4",
            "gpt-4-turbo",
            "claude-2",
            "random-model",
        ],
    )
    def test_returns_false_for_non_vision_models(self, model: str) -> None:
        assert VisionEnricher.is_vision_capable("ollama", model) is False
        assert VisionEnricher.is_vision_capable("lm-studio", model) is False

    def test_case_insensitive(self) -> None:
        assert VisionEnricher.is_vision_capable("ollama", "QWEN2.5-VL") is True
        assert VisionEnricher.is_vision_capable("ollama", "Llava") is True
        assert VisionEnricher.is_vision_capable("ollama", "GPT-4O") is True


# ---------------------------------------------------------------------------
# crop_element_from_screenshot
# ---------------------------------------------------------------------------


class TestCropElementFromScreenshot:
    """Test element cropping from screenshots."""

    def test_crops_valid_region(self) -> None:
        screenshot = _make_image(200, 200)
        bbox: dict[str, float] = {"x": 10.0, "y": 20.0, "width": 50.0, "height": 30.0}
        result = VisionEnricher.crop_element_from_screenshot(screenshot, bbox, padding=0)
        img = Image.open(io.BytesIO(result))
        assert img.size == (50, 30)

    def test_crops_with_padding(self) -> None:
        screenshot = _make_image(200, 200)
        bbox = {"x": 10.0, "y": 20.0, "width": 50.0, "height": 30.0}
        result = VisionEnricher.crop_element_from_screenshot(screenshot, bbox, padding=5)
        img = Image.open(io.BytesIO(result))
        assert img.size == (60, 40)

    def test_clamps_to_image_bounds(self) -> None:
        screenshot = _make_image(100, 100)
        # Crop region extends beyond image
        bbox = {"x": 90.0, "y": 90.0, "width": 50.0, "height": 50.0}
        result = VisionEnricher.crop_element_from_screenshot(screenshot, bbox, padding=0)
        img = Image.open(io.BytesIO(result))
        # Should be clamped to image edge
        assert img.size[0] <= 10
        assert img.size[1] <= 10

    def test_invalid_crop_returns_1x1(self) -> None:
        screenshot = _make_image(100, 100)
        # Negative dimensions
        bbox = {"x": 50.0, "y": 50.0, "width": -10.0, "height": 30.0}
        result = VisionEnricher.crop_element_from_screenshot(screenshot, bbox, padding=0)
        img = Image.open(io.BytesIO(result))
        assert img.size == (1, 1)

    def test_zero_padding_default(self) -> None:
        screenshot = _make_image(200, 200)
        bbox = {"x": 10.0, "y": 20.0, "width": 50.0, "height": 30.0}
        result = VisionEnricher.crop_element_from_screenshot(screenshot, bbox, padding=0)
        img = Image.open(io.BytesIO(result))
        assert img.size == (50, 30)


# ---------------------------------------------------------------------------
# _parse_enrichment_response
# ---------------------------------------------------------------------------


class TestParseEnrichmentResponse:
    """Test parsing of vision LLM responses."""

    def test_parses_valid_json(self) -> None:
        data = {
            "product_name": "Sauce Labs Backpack",
            "price": "$29.99",
            "description": "backpack product image",
            "visual_label": "product card",
            "enrichment_note": "product name visible",
        }
        json_str = json.dumps(data)
        result = VisionEnricher._parse_enrichment_response(json_str)
        assert result["product_name"] == "Sauce Labs Backpack"
        assert result["price"] == "$29.99"
        assert result["description"] == "backpack product image"
        assert result["visual_label"] == "product card"
        assert result["enrichment_note"] == "product name visible"

    def test_parses_json_with_null_values(self) -> None:
        data = {
            "product_name": None,
            "price": None,
            "description": None,
            "visual_label": None,
            "enrichment_note": None,
        }
        json_str = json.dumps(data)
        result = VisionEnricher._parse_enrichment_response(json_str)
        assert result["product_name"] is None
        assert result["price"] is None

    def test_parses_json_with_markdown_fence(self) -> None:
        data = {
            "product_name": "Test Product",
            "price": None,
            "description": None,
            "visual_label": None,
            "enrichment_note": None,
        }
        json_str = "```json\n" + json.dumps(data) + "\n```"
        result = VisionEnricher._parse_enrichment_response(json_str)
        assert result["product_name"] == "Test Product"

    def test_fallback_to_text_extraction(self) -> None:
        text = """Here is my analysis:
product_name: Sauce Labs Backpack
price: $29.99
description: product image
visual_label: product card
enrichment_note: visible product"""
        result = VisionEnricher._parse_enrichment_response(text)
        assert result["product_name"] == "Sauce Labs Backpack"
        assert result["price"] == "$29.99"
        assert result["description"] == "product image"
        assert result["visual_label"] == "product card"
        assert result["enrichment_note"] == "visible product"

    def test_returns_defaults_on_invalid_input(self) -> None:
        result = VisionEnricher._parse_enrichment_response("not valid json at all {{{")
        assert result["product_name"] is None
        assert result["price"] is None
        assert result["description"] is None
        assert result["visual_label"] is None
        assert result["enrichment_note"] is None

    def test_returns_defaults_on_empty_input(self) -> None:
        result = VisionEnricher._parse_enrichment_response("")
        assert all(v is None for v in result.values())


# ---------------------------------------------------------------------------
# enrich_elements (no vision model — graceful degradation)
# ---------------------------------------------------------------------------


class TestEnrichElementsNoVision:
    """Test enrich_elements when no vision model is available."""

    def test_returns_elements_unchanged_when_no_vision_model(self) -> None:
        elements: list[dict[str, Any]] = [
            {"tag": "button", "text": "Add to Cart", "attributes": {}},
            {"tag": "img", "text": "", "attributes": {"src": "product.png"}},
        ]
        screenshot = _make_image(200, 200)
        result = VisionEnricher.enrich_elements(
            elements,
            screenshot,
            provider="ollama",
            model="qwen2.5:7b",  # non-vision model
        )
        assert len(result) == 2
        for elem in result:
            assert "_enriched" not in elem
            assert elem["tag"] in ("button", "img")

    def test_returns_empty_list_when_no_elements(self) -> None:
        result = VisionEnricher.enrich_elements(
            [],
            _make_image(200, 200),
            provider="ollama",
            model="qwen2.5-vl",
        )
        assert result == []

    def test_returns_elements_unchanged_when_no_screenshot(self) -> None:
        elements: list[dict[str, Any]] = [{"tag": "button", "text": "Submit", "attributes": {}}]
        result = VisionEnricher.enrich_elements(
            elements,
            b"",
            provider="ollama",
            model="qwen2.5-vl",
        )
        assert len(result) == 1
        assert "_enriched" not in result[0]


# ---------------------------------------------------------------------------
# enrich_elements (with vision model — mocked LLM calls)
# ---------------------------------------------------------------------------


class TestEnrichElementsWithVision:
    """Test enrich_elements when vision model is available (mocked)."""

    def test_enriches_elements_with_vision_model(self) -> None:
        elements: list[dict[str, Any]] = [
            {
                "tag": "img",
                "text": "Sauce Labs Backpack",
                "attributes": {"src": "backpack.png"},
                "_bbox": {"x": 10.0, "y": 20.0, "width": 50.0, "height": 30.0},
            },
        ]
        screenshot = _make_image(200, 200)
        mock_response = json.dumps(
            {
                "product_name": "Sauce Labs Backpack",
                "price": None,
                "description": "backpack product image",
                "visual_label": "product card",
                "enrichment_note": "product name visible",
            }
        )

        mock_client = MagicMock()
        mock_client.create_vision_completion.return_value = mock_response

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            result = VisionEnricher.enrich_elements(
                elements,
                screenshot,
                provider="ollama",
                model="qwen2.5-vl",
            )

        assert len(result) == 1
        assert result[0]["_enriched"] is True
        assert result[0]["product_name"] == "Sauce Labs Backpack"
        assert result[0]["description"] == "backpack product image"
        assert result[0]["visual_label"] == "product card"
        assert result[0]["tag"] == "img"  # original fields preserved

    def test_handles_enrichment_error_gracefully(self) -> None:
        elements: list[dict[str, Any]] = [
            {
                "tag": "button",
                "text": "Submit",
                "attributes": {},
                "_bbox": {"x": 10.0, "y": 20.0, "width": 50.0, "height": 30.0},
            },
        ]
        screenshot = _make_image(200, 200)

        mock_client = MagicMock()
        mock_client.create_vision_completion.side_effect = RuntimeError("LLM service unavailable")

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            result = VisionEnricher.enrich_elements(
                elements,
                screenshot,
                provider="ollama",
                model="qwen2.5-vl",
            )

        assert len(result) == 1
        assert result[0]["_enriched"] is False
        assert result[0]["_enrichment_error"] == "LLM service unavailable"
        assert result[0]["tag"] == "button"  # original fields preserved

    def test_skips_elements_without_bbox(self) -> None:
        elements: list[dict[str, Any]] = [
            {
                "tag": "span",
                "text": "Some text",
                "attributes": {},
                # No _bbox key
            },
        ]
        screenshot = _make_image(200, 200)

        mock_client = MagicMock()

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            result = VisionEnricher.enrich_elements(
                elements,
                screenshot,
                provider="ollama",
                model="qwen2.5-vl",
            )

        assert len(result) == 1
        assert result[0]["_enriched"] is False
        # LLM should not have been called
        mock_client.create_vision_completion.assert_not_called()

    def test_multiple_elements_all_enriched(self) -> None:
        elements: list[dict[str, Any]] = [
            {
                "tag": "img",
                "text": "Product A",
                "attributes": {},
                "_bbox": {"x": 0.0, "y": 0.0, "width": 50.0, "height": 50.0},
            },
            {
                "tag": "button",
                "text": "Add to Cart",
                "attributes": {},
                "_bbox": {"x": 60.0, "y": 0.0, "width": 50.0, "height": 30.0},
            },
        ]
        screenshot = _make_image(200, 200)
        mock_response = json.dumps(
            {
                "product_name": None,
                "price": None,
                "description": "button element",
                "visual_label": "action button",
                "enrichment_note": None,
            }
        )

        mock_client = MagicMock()
        mock_client.create_vision_completion.return_value = mock_response

        with patch("src.llm_client.LLMClient", return_value=mock_client):
            result = VisionEnricher.enrich_elements(
                elements,
                screenshot,
                provider="ollama",
                model="qwen2.5-vl",
            )

        assert len(result) == 2
        assert all(e["_enriched"] is True for e in result)
        assert mock_client.create_vision_completion.call_count == 2
