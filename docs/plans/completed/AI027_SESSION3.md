# Session 3: Vision Enrichment Service + Crop + LLM Call

**AI-027 — Visual Element Enrichment**  
**Created:** 2026-05-13  
**Depends on:** Session 2 (Screenshot capture during scraping)  
**Original spec:** `docs/specs/FEATURE_SPEC_visual_element_enrichment.md`

---

## Goal

Complete the vision enrichment pipeline: crop elements from screenshots, send to vision LLM, parse structured responses, store metadata in element dicts. This is the core "vision" phase.

**Deliverables:**
- `src/vision_enricher.py` — full implementation with crop, LLM call, response parsing
- `src/scraper.py` — integration: call enrichment after screenshot capture
- `tests/test_vision_enricher_integration.py` — integration tests
- Updated documentation

---

## Current State of Relevant Files

### src/vision_enricher.py (from Session 1)
- `is_vision_capable()` — implemented and tested
- `crop_element_from_screenshot()` — implemented and tested
- `enrich_elements()` — skeleton only, needs full implementation
- `create_vision_completion()` — added to `src/llm_client.py`

### src/scraper.py (from Session 2)
- `capture_page_screenshot()` — implemented and tested
- `ScrapeResult` dataclass — has `screenshot_bytes` and `element_boxes` fields
- **Needs:** Integration with `VisionEnricher.enrich_elements()`

---

## Implementation Tasks

### Task 1: Complete `VisionEnricher.enrich_elements()` in `src/vision_enricher.py`

```python
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
    """
    if not cls.is_vision_capable(provider, model):
        # No vision capability — return elements unchanged
        return elements

    if not elements or not screenshot_bytes:
        return elements

    enriched = []
    for i, element in enumerate(elements):
        try:
            # Get bounding box for this element
            bbox = element.get("_bbox")
            if not bbox:
                enriched.append(element)
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
                max_tokens=256,
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
            enriched.append(enriched_element)

    return enriched
```

### Task 2: Implement `_build_vision_prompt()`

```python
@classmethod
def _build_vision_prompt(cls, element: dict[str, Any]) -> str:
    """Build the prompt for the vision LLM for a single element.

    Returns structured JSON output:
    {
        "product_name": "string or null",
        "price": "string or null",
        "description": "string or null",
        "visual_label": "string or null",
        "enrichment_note": "string or null"
    }
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
```

### Task 3: Implement `_parse_enrichment_response()`

```python
@classmethod
def _parse_enrichment_response(cls, response_text: str) -> dict[str, str | None]:
    """Parse the vision LLM's structured response into element metadata.

    Tries JSON parsing first, falls back to text extraction.
    Returns None values for all fields if parsing fails.
    """
    defaults = {
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
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: extract key-value pairs from text
    for key in defaults:
        pattern = rf"{key}[:\s]+([^\n]+)"
        match = re.search(pattern, response_text, re.IGNORECASE)
        if match:
            defaults[key] = match.group(1).strip().strip('"').strip("'")

    return defaults
```

### Task 4: Integrate with `src/scraper.py`

**Modified in `src/scraper.py`:**

After screenshot capture in the scraping flow:

```python
def scrape_with_enrichment(
    scrape_results: list[ScrapeResult],
    provider: str,
    model: str,
    timeout: int = 60,
) -> list[ScrapeResult]:
    """Apply vision enrichment to all scrape results.

    For each result with screenshot data:
    1. Check if vision LLM is available
    2. Enrich elements with vision-derived metadata
    3. Return enriched results

    Args:
        scrape_results: List of ScrapeResult objects with screenshot data.
        provider: LLM provider name.
        model: LLM model name.
        timeout: Max seconds per element.

    Returns:
        Enriched ScrapeResult objects (elements have new metadata fields).
    """
    from src.vision_enricher import VisionEnricher

    if not VisionEnricher.is_vision_capable(provider, model):
        # No vision capability — return results unchanged
        return scrape_results

    enriched_results = []
    for result in scrape_results:
        if result.screenshot_bytes and result.element_boxes:
            # Map bounding boxes to elements
            for box in result.element_boxes:
                idx = box.get("element_index")
                if idx is not None and idx < len(result.elements):
                    result.elements[idx]["_bbox"] = box["bbox"]

            # Enrich elements
            enriched_elements = VisionEnricher.enrich_elements(
                elements=result.elements,
                screenshot_bytes=result.screenshot_bytes,
                provider=provider,
                model=model,
                timeout=timeout,
            )
            result.elements = enriched_elements

        enriched_results.append(result)

    return enriched_results
```

### Task 5: Create `tests/test_vision_enricher_integration.py`

```python
"""Integration tests for vision enrichment pipeline."""

import pytest

from src.vision_enricher import VisionEnricher


class TestVisionEnricherFullPipeline:
    """Test full enrichment pipeline with mocked LLM calls."""

    def test_enrich_elements_calls_vision_llm(self, mock_llm_client) -> None:
        """Enrichment should call create_vision_completion for each element."""

    def test_enrich_elements_stores_metadata_in_elements(self, mock_llm_client) -> None:
        """Enriched elements should have product_name, price, description fields."""

    def test_enrich_elements_handles_llm_timeout(self, mock_llm_timeout) -> None:
        """Timeout should not crash — element kept with error note."""

    def test_enrich_elements_handles_garbled_llm_response(self, mock_llm_garbled) -> None:
        """Garbled response should not crash — element kept with None values."""

    def test_enrich_elements_returns_unchanged_for_non_vision_model(self) -> None:
        """Non-vision models should return elements unchanged."""

    def test_enrich_elements_handles_empty_elements(self) -> None:
        """Empty element list should return empty list."""

    def test_enrich_elements_handles_none_screenshot(self) -> None:
        """None screenshot should return elements unchanged."""


class TestVisionEnricherPromptBuilding:
    """Test vision prompt construction."""

    def test_prompt_includes_element_type(self) -> None:
        """Prompt should include element tag type."""

    def test_prompt_includes_text_content(self) -> None:
        """Prompt should include element text content."""

    def test_prompt_includes_attributes(self) -> None:
        """Prompt should include element attributes."""

    def test_prompt_requests_json_output(self) -> None:
        """Prompt should request structured JSON output."""
```

---

## Documentation Updates

### docs/ARCHITECTURE.md
Add to "Context Extraction Layer":
```
| `src/scraper.py` (`PageScraper`) | DOM scraping + screenshot capture + bounding box extraction.
|                                     | `scrape_with_enrichment()` applies vision enrichment to all results.
```

### docs/PROJECT_KNOWLEDGE.md
Add to "Architecture Decisions":
```
| Vision enrichment pipeline | After screenshot capture, VisionEnricher.enrich_elements() crops each element,
|                            | sends to vision LLM, parses structured JSON response, stores metadata in element dicts.
|                            | Failed enrichment is silent — original element preserved.
```

### BACKLOG.md
Update AI-027 status:
```
### AI-027 — Visual Element Enrichment (IN PROGRESS — Session 3 of 4)
**Session 1 complete:** VisionEnricher + vision capability detection
**Session 2 complete:** Screenshot capture during scraping
**Session 3 in progress:** Vision enrichment service + crop + LLM call
```

### CHANGELOG.md
Add entry:
```
| 1.8.0 | 2026-05-13 | AI-027 Session 3: Vision enrichment service with crop + LLM call
```

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Protected files — DO NOT TOUCH:**
  - `src/test_generator.py`
  - `src/llm_providers/`
  - `.github/workflows/ci.yml`

---

## Verification Steps

1. `ruff check src/vision_enricher.py src/scraper.py` — clean
2. `mypy src/vision_enricher.py src/scraper.py` — clean
3. `pytest tests/test_vision_enricher_integration.py -v` — all green
4. `pytest tests/ -v` — ALL existing tests still pass
5. End-to-end: Run UAT script against saucedemo with vision-capable model (qwen3.6-35b-a3b)
   - Should see enriched elements in logs
   - Should see improved placeholder resolution (product-specific matches)

---

## Expected Test Count

- `test_vision_enricher_integration.py`: 12 tests minimum
  - 7 tests for full enrichment pipeline
  - 4 tests for prompt building
  - 1 test for error handling