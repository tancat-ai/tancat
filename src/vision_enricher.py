"""Vision-based element enrichment service.

Uses vision-capable LLMs to analyze cropped element images and return
structured text metadata for improved placeholder resolution.

Architecture:
- Vision is a metadata enricher, not a matcher — the text-based resolver
  always does matching
- Zero regression — users without vision LLMs get exactly what they have today
- Auto-detection — no user config needed; vision capability detected from model name
- In-memory only — images stored as base64 in element dicts, discarded after enrichment

Session 1: Vision capability detection + model registry
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from PIL import Image

# Known vision-capable model name patterns (order matters — first match wins)
VISION_MODEL_PATTERNS: list[str] = [
    # Qwen2.5-VL / Qwen3.x-VL family
    r"qwen2\.5-vl",
    r"qwen3\.[0-9]+-vl",
    r"qwen3\.[0-9]+-a3b",
    r"qwen3\.6-35b-a3b",
    r"qwen2\.5-vl",
    # LLaVA family
    r"llava",
    # GPT-4 vision family
    r"gpt[-_]4[vo]",
    r"gpt[-_]4[.-][0-9]+",
    # Gemini vision family
    r"gemini[-_]?pro[-_]?vision",
    r"gemini[-_]?2\.0",
    # Claude vision family
    r"claude[-_]?3[.-][0-9]+",
    r"claude[-_]?3[-_]?opus",
    r"claude[-_]?opus",
    r"claude[-_]?3[-_]?sonnet",
    r"claude[-_]?sonnet",
    r"claude[-_]?3[-_]?haiku",
    r"claude[-_]?haiku",
    # GLM vision
    r"glm[-_]?4v",
    # InternVL
    r"internvl",
    # Llama 3.2 vision
    r"llama[.-]3[.-]2[vl]",
    # Generic vision patterns
    r"vision",
    r"-vl",
    r"-mm",
]


class VisionEnricher:
    """Enrich scraped elements with vision-derived metadata.

    Uses a vision-capable LLM to analyze cropped element images and return
    structured text metadata (product name, price, description, visual label).

    Design:
    - Vision is a metadata enricher, not a matcher
    - The text-based resolver always does matching
    - Works with or without vision capability
    - Auto-detected — no user config needed
    """

    @classmethod
    def is_vision_capable(cls, provider: str, model: str) -> bool:
        """Detect whether the configured LLM supports vision input.

        Detection logic (in order of priority):
        1. Model name against known vision-capable patterns
        2. Graceful fallback to False if no pattern matches

        Args:
            provider: LLM provider name (e.g., 'ollama', 'lm-studio', 'openai').
            model: LLM model name (e.g., 'qwen3.6-35b-a3b').

        Returns:
            True if the model supports vision input, False otherwise.
        """
        model_lower = model.lower()

        for pattern in VISION_MODEL_PATTERNS:
            if re.search(pattern, model_lower):
                return True

        return False

    @classmethod
    def crop_element_from_screenshot(
        cls,
        screenshot_bytes: bytes,
        bbox: dict[str, float],
        padding: int = 2,
    ) -> bytes:
        """Crop a single element from a screenshot using bounding box coordinates.

        Args:
            screenshot_bytes: Full-page screenshot PNG bytes.
            bbox: Bounding box dict with keys 'x', 'y', 'width', 'height'.
            padding: Extra pixels to add around the element (default 2).

        Returns:
            Cropped element as PNG bytes.
        """
        img = Image.open(io.BytesIO(screenshot_bytes))
        width, height = img.size

        # Extract bounding box coordinates with padding
        left = max(0, int(bbox["x"]) - padding)
        top = max(0, int(bbox["y"]) - padding)
        right = min(width, int(bbox["x"] + bbox["width"]) + padding)
        bottom = min(height, int(bbox["y"] + bbox["height"]) + padding)

        # Clamp to image bounds
        left = max(0, left)
        top = max(0, top)
        right = min(width, right)
        bottom = min(height, bottom)

        # Ensure valid crop region
        if right <= left or bottom <= top:
            # Return empty 1x1 white pixel if crop region is invalid
            empty_img = Image.new("RGB", (1, 1), (255, 255, 255))
            buf = io.BytesIO()
            empty_img.save(buf, format="PNG")
            return buf.getvalue()

        cropped = img.crop((left, top, right, bottom))

        # Convert to PNG bytes
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()

    @classmethod
    def _build_vision_prompt(cls, element: dict[str, Any]) -> str:
        """Build the prompt for the vision LLM for a single element.

        Args:
            element: Scraped element dict with metadata.

        Returns:
            Prompt string for the vision LLM.
        """
        element_type = element.get("tag", "unknown")
        text_content = element.get("text", "")
        attributes = element.get("attributes", {})

        return (
            f"Analyze this {element_type} element from a web page.\n"
            f"Text content: {text_content}\n"
            f"Attributes: {attributes}\n\n"
            "Return ONLY a JSON object with these keys:\n"
            "- product_name: product name if this is a product card/image (null otherwise)\n"
            "- price: price if visible (null otherwise)\n"
            "- description: brief description of what this element shows (null if nothing useful)\n"
            "- visual_label: what this element visually represents (e.g., 'backpack product image', 'add to cart button')\n"
            "- enrichment_note: any additional context about this element (null if nothing useful)\n\n"
            "Example output:\n"
            '{"product_name": "Sauce Labs Backpack", "price": null, '
            '"description": "backpack product image", '
            '"visual_label": "product card", "enrichment_note": "product name visible"}'
        )

    @classmethod
    def enrich_elements(
        cls,
        elements: list[dict[str, Any]],
        screenshot_bytes: bytes,
        provider: str,
        model: str,
        timeout: int = 60,
    ) -> list[dict[str, Any]]:
        """Enrich elements with vision-derived metadata.

        For each element:
        1. Check if vision LLM is available
        2. Crop the element from the screenshot
        3. Send cropped image + metadata to vision LLM
        4. Parse structured response
        5. Store metadata in element dict
        6. Handle timeouts and errors gracefully

        Args:
            elements: List of scraped element dicts.
            screenshot_bytes: Full-page screenshot PNG bytes.
            provider: LLM provider name.
            model: LLM model name.
            timeout: Max seconds per element (default 60).

        Returns:
            Enriched elements with new fields:
            - "product_name": str or None
            - "price": str or None
            - "description": str or None
            - "visual_label": str or None
            - "enrichment_note": str or None
            - "_enriched": bool (True if enriched, False if skipped/errored)
        """
        if not cls.is_vision_capable(provider, model):
            # No vision capability — return elements unchanged
            for elem in elements:
                elem["_enriched"] = False
            return elements

        if not elements or not screenshot_bytes:
            for elem in elements:
                elem["_enriched"] = False
            return elements

        # Import here to avoid circular import
        from src.llm_client import LLMClient

        enriched = []
        for _i, element in enumerate(elements):
            try:
                # Get bounding box for this element
                bbox = element.get("_bbox")
                if not bbox:
                    enriched_element = dict(element)
                    enriched_element["_enriched"] = False
                    enriched.append(enriched_element)
                    continue

                # Crop element from screenshot
                cropped = cls.crop_element_from_screenshot(screenshot_bytes, bbox)

                # Build vision prompt
                prompt = cls._build_vision_prompt(element)

                # Convert to base64
                image_b64 = base64.b64encode(cropped).decode("ascii")

                # Call vision LLM
                client = LLMClient(provider=provider, model=model)
                response = client.create_vision_completion(
                    image_base64=image_b64,
                    prompt=prompt,
                )

                # Parse response
                metadata = cls._parse_enrichment_response(response)

                # Store in element dict
                enriched_element = dict(element)
                enriched_element.update(metadata)
                enriched_element["_enriched"] = True
                enriched.append(enriched_element)

            except Exception as exc:
                # Enrichment failed for this element — keep original
                enriched_element = dict(element)
                enriched_element["_enrichment_error"] = str(exc)
                enriched_element["_enriched"] = False
                enriched.append(enriched_element)

        return enriched

    @classmethod
    def _parse_enrichment_response(cls, response_text: str) -> dict[str, str | None]:
        """Parse the vision LLM's structured response into element metadata.

        Tries JSON parsing first, falls back to text extraction.
        Returns None values for all fields if parsing fails.

        Args:
            response_text: Raw text response from the vision LLM.

        Returns:
            Dict with keys: product_name, price, description, visual_label, enrichment_note.
        """
        defaults: dict[str, str | None] = {
            "product_name": None,
            "price": None,
            "description": None,
            "visual_label": None,
            "enrichment_note": None,
        }

        # Try JSON parsing
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_text = response_text.strip()
            # Remove markdown code fence if present
            if json_text.startswith("```"):
                lines = json_text.split("\n")
                json_text = "\n".join(lines[1:-1]) if len(lines) > 2 else lines[1] if len(lines) > 1 else ""
            data = json.loads(json_text)
            return {k: data.get(k) for k in defaults}
        except json.JSONDecodeError, ValueError:
            pass

        # Fallback: extract key-value pairs from text
        for key in defaults:
            pattern = rf"{key}[:\s]+([^\n]+)"
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                defaults[key] = match.group(1).strip().strip('"').strip("'")

        return defaults
