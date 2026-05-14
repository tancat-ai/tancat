# Session 1: Vision Capability Detection + Model Registry

**AI-027 — Visual Element Enrichment**  
**Created:** 2026-05-13  
**Depends on:** None (standalone)  
**Original spec:** `docs/specs/FEATURE_SPEC_visual_element_enrichment.md`

---

## Goal

Implement `VisionEnricher` with vision capability detection. This session creates the foundation — the model registry and detection logic that all subsequent sessions depend on.

**Deliverables:**
- `src/vision_enricher.py` — VisionEnricher class with `is_vision_capable()` and `enrich_elements()`
- `tests/test_vision_enricher.py` — Unit tests for all detection and enrichment methods
- Updated documentation (ARCHITECTURE.md, PROJECT_KNOWLEDGE.md, BACKLOG.md, CHANGELOG.md)

---

## Current State of Relevant Files

### src/scraper.py
- DOM scraping via `PageScraper.scrape_all()` and `PageScraper.scrape_url()`
- No screenshot capture during scraping
- **Needs:** Integration point for vision enrichment (will be added in Session 2)

### src/orchestrator.py
- `TestOrchestrator.run_pipeline()` orchestrates scraping → resolution → generation
- No vision enrichment integration yet
- **Needs:** Pass enriched elements to placeholder orchestrator (Session 4)

### src/llm_client.py
- `LLMClient` with `create_completion()` method
- Supports ollama and lm-studio providers
- **Needs:** New method `create_vision_completion()` for vision-capable LLM calls

### pyproject.toml
- Dependencies managed by uv
- **Needs:** `pillow` (Pillow) for image cropping — `uv add pillow`

---

## Implementation Tasks

### Task 1: Create `src/vision_enricher.py`

```python
"""Vision-based element enrichment service.

Uses vision-capable LLMs to analyze cropped element images and return
structured text metadata for improved placeholder resolution.
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

from PIL import Image


# Known vision-capable model name patterns
VISION_MODEL_PATTERNS: list[str] = [
    r"qwen2\.5-vl",
    r"qwen3\.6-35b-a3b",
    r"qwen3\.5-35b",
    r"qwen[23]\.[0-9]+-vl",
    r"llava",
    r"gpt[-_]4[vo]",
    r"gpt[-_]4[.-][0-9]+",
    r"gemini[-_]?pro[-_]?vision",
    r"gemini[-_]?2\.0",
    r"claude[-_]?3[.-][0-9]+",
    r"claude[-_]?opus",
    r"claude[-_]?sonnet",
    r"claude[-_]?haiku",
    r"glm[-_]?4v",
    r"internvl",
    r"llama[.-]3[.-]2[vl]",
    r"vision",
    r"-vl",
    r"-mm",
]


class VisionEnricher:
    """Enrich scraped elements with vision-derived metadata.

    Uses a vision-capable LLM to analyze cropped element images and return
    structured text metadata (product name, price, description, visual label).
    """

    @classmethod
    def is_vision_capable(cls, provider: str, model: str) -> bool:
        """Detect whether the configured LLM supports vision input.

        Detection logic (in order of priority):
        1. Model name against known vision-capable patterns
        2. Provider-specific API check (if available)
        3. Graceful fallback to False if detection fails

        Args:
            provider: LLM provider name (e.g., 'ollama', 'lm-studio', 'openai').
            model: LLM model name (e.g., 'qwen3.6-35b-a3b').

        Returns:
            True if the model supports vision input, False otherwise.
        """

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

    @classmethod
    def _build_vision_prompt(cls, element: dict[str, Any]) -> str:
        """Build the prompt for the vision LLM for a single element.

        Args:
            element: Scraped element dict with metadata.

        Returns:
            Prompt string for the vision LLM.
        """

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
        1. Crop the element from the screenshot
        2. Send cropped image + metadata to vision LLM
        3. Parse structured response
        4. Store metadata in element dict

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
        """

    @classmethod
    def _parse_enrichment_response(cls, response_text: str) -> dict[str, str | None]:
        """Parse the vision LLM's structured response into element metadata.

        Args:
            response_text: Raw text response from the vision LLM.

        Returns:
            Dict with keys: product_name, price, description, visual_label, enrichment_note.
        """
```

### Task 2: Create `tests/test_vision_enricher.py`

```python
"""Tests for VisionEnricher — vision capability detection and element enrichment."""

import pytest

from src.vision_enricher import VisionEnricher


class TestVisionEnricherIsVisionCapable:
    """Test vision capability detection against known model names."""

    def test_qwen3_6_35b_a3b_is_vision_capable(self) -> None:
        """qwen3.6-35b-a3b should be detected as vision-capable."""

    def test_qwen2_5_vl_is_vision_capable(self) -> None:
        """qwen2.5-vl models should be detected as vision-capable."""

    def test_llava_is_vision_capable(self) -> None:
        """llava models should be detected as vision-capable."""

    def test_gpt_4o_is_vision_capable(self) -> None:
        """gpt-4o should be detected as vision-capable."""

    def test_gemini_pro_vision_is_vision_capable(self) -> None:
        """gemini-pro-vision should be detected as vision-capable."""

    def test_claude_3_sonnet_is_vision_capable(self) -> None:
        """claude-3-sonnet should be detected as vision-capable."""

    def test_qwen3_5_35b_is_not_vision_capable(self) -> None:
        """qwen3.5:35b (text-only) should NOT be detected as vision-capable."""

    def test_llama_3_1_8b_is_not_vision_capable(self) -> None:
        """llama3.1:8b (text-only) should NOT be detected as vision-capable."""

    def test_unknown_model_defaults_to_not_vision_capable(self) -> None:
        """Unknown model names should default to False."""

    def test_vision_pattern_contains_vl(self) -> None:
        """Model names containing '-vl' should be detected as vision-capable."""

    def test_vision_pattern_contains_vision(self) -> None:
        """Model names containing 'vision' should be detected as vision-capable."""

    def test_case_insensitive_detection(self) -> None:
        """Detection should be case-insensitive."""


class TestVisionEnricherCropElement:
    """Test element cropping from screenshots."""

    def test_crop_element_with_padding(self) -> None:
        """Cropping should respect padding parameter."""

    def test_crop_element_with_no_padding(self) -> None:
        """Cropping with padding=0 should use exact bounding box."""

    def test_crop_element_clamps_to_image_bounds(self) -> None:
        """Cropping should not exceed image boundaries."""

    def test_crop_element_returns_valid_png(self) -> None:
        """Cropped output should be valid PNG bytes decodable by PIL."""


class TestVisionEnricherEnrichElements:
    """Test full enrichment pipeline."""

    def test_enrich_elements_returns_enriched_dicts(self) -> None:
        """Enriched elements should have new metadata fields."""

    def test_enrich_elements_handles_non_vision_model(self) -> None:
        """Non-vision models should return elements unchanged."""

    def test_enrich_elements_handles_empty_element_list(self) -> None:
        """Empty element list should return empty list."""

    def test_parse_enrichment_response_valid(self) -> None:
        """Valid JSON response should parse correctly."""

    def test_parse_enrichment_response_invalid(self) -> None:
        """Invalid response should return None values for all fields."""
```

### Task 3: Add `create_vision_completion()` to `src/llm_client.py`

**Touch:** `src/llm_client.py` (PROTECTED — add method, do not modify existing code)

```python
def create_vision_completion(
    self,
    image_base64: str,
    prompt: str,
    max_tokens: int = 256,
) -> str:
    """Send a vision-capable LLM an image + text prompt.

    Args:
        image_base64: Base64-encoded PNG image string (data URI without prefix).
        prompt: Text prompt for the vision LLM.
        max_tokens: Maximum tokens in response (default 256).

    Returns:
        Text response from the vision LLM.

    Raises:
        ValueError: If the provider/model does not support vision.
    """
```

**Implementation notes:**
- Uses the same provider infrastructure as `create_completion()`
- For ollama/lm-studio: uses `/api/chat` with `images` field
- For openai: uses `chat.completions.create()` with `image_url` content part
- Returns raw text — caller is responsible for parsing structured output

---

## Documentation Updates

### docs/ARCHITECTURE.md
Add to "Context Extraction Layer" table:
```
| `src/vision_enricher.py` (`VisionEnricher`) | Vision-based element enrichment. Detects vision-capable LLMs, crops element images,
|                                             | sends them to vision LLMs, stores structured metadata in element dicts.
```

### docs/PROJECT_KNOWLEDGE.md
Add to "Architecture Decisions" table:
```
| Vision enrichment | Vision LLM converts element images → structured text. Text-based resolver always does matching.
|                   | Works with or without vision capability. Auto-detected. No user config needed.
```

### BACKLOG.md
Add new section at top:
```
### AI-027 — Visual Element Enrichment (IN PROGRESS — Session 1 of 4)
**What:** Vision-based element enrichment for improved placeholder resolution on multi-product sites.
**Phase 1:** Screenshot capture + vision enrichment service + auto-detection of vision capability.
**Phase 2:** Journey-discovered selector propagation to placeholder resolver.
**Phase 3:** Enhanced resolver text matching with product name enrichment.
**Spec:** `docs/specs/FEATURE_SPEC_visual_element_enrichment.md`
**Priority:** High — placeholder resolution quality on multi-product sites
```

### CHANGELOG.md
Add version entry:
```
| 1.8.0 | 2026-05-13 | AI-027 Visual Element Enrichment — vision-based element metadata enrichment,
             |            | journey selector propagation, enhanced resolver text matching
```

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Helper functions:** Go in `src/`, NOT in `streamlit_app.py`
- **Quality gates:** ruff → mypy → pytest → human reviews diff → commit
- **Protected files — DO NOT TOUCH:**
  - `src/llm_client.py` — add method only, do not modify existing code
  - `src/test_generator.py`
  - `src/llm_providers/`
  - `.github/workflows/ci.yml`

---

## Verification Steps

1. `uv add pillow` — install image processing dependency
2. `ruff check src/vision_enricher.py` — clean
3. `mypy src/vision_enricher.py` — clean
4. `pytest tests/test_vision_enricher.py -v` — all green
5. `pytest tests/ -v` — ALL existing tests still pass
6. Manual test: `python -c "from src.vision_enricher import VisionEnricher; print(VisionEnricher.is_vision_capable('lm-studio', 'qwen3.6-35b-a3b'))"` → should print `True`
7. Manual test: `python -c "from src.vision_enricher import VisionEnricher; print(VisionEnricher.is_vision_capable('ollama', 'qwen3.5:35b'))"` → should print `False`

---

## Expected Test Count

- `test_vision_enricher.py`: 19 tests minimum
  - 11 tests for `is_vision_capable()`
  - 4 tests for `crop_element_from_screenshot()`
  - 4 tests for `enrich_elements()` and response parsing