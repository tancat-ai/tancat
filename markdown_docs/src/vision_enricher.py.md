# `src/vision_enricher.py`

## Purpose
Vision-based element enrichment service. Uses vision-capable LLMs to analyze cropped element screenshots and return structured text metadata (product_name, price, visual_label) for improved placeholder resolution. Vision is a metadata enricher, not a matcher — text-based resolver always does matching.

## Metadata
- **Lines:** 307
- **Imports:** base64, io, json, re, typing, PIL.Image

## Classes
| Class | Description |
|-------|-------------|
| `VisionEnricher` | Static methods for vision detection, cropping, enrichment |

## Key Constants
| Constant | Description |
|----------|-------------|
| `VISION_MODEL_PATTERNS` | Regex patterns for vision-capable model names (qwen-vl, llava, gpt-4v, gemini, claude, glm-4v, internvl, llama-3.2-vl) |

## Methods
| Method | Description |
|--------|-------------|
| `is_vision_capable(provider, model)` | Detect vision support by matching model name against known patterns |
| `crop_element_from_screenshot(screenshot_bytes, bbox, padding=2)` | Crop element from full-page screenshot using bounding box |
| `enrich_elements(elements, screenshot_bytes, provider, model, timeout=60)` | Main enrichment pipeline: crop → vision LLM → parse → merge metadata |
| `_build_vision_prompt(element)` | Build prompt asking vision LLM for structured JSON metadata |
| `_parse_enrichment_response(response_text)` | Parse vision LLM response: JSON first, then regex fallback |

## Enrichment Flow
1. Check `is_vision_capable` — skip if no vision model
2. For each element with `_bbox`: crop from screenshot → base64 encode
3. Call `LLMClient.create_vision_completion()` with cropped image + prompt
4. Parse structured response → merge into element dict
5. Set `_enriched=True` on success, `_enriched=False` + `_enrichment_error` on failure

## Design Principles
- Zero regression: users without vision LLMs get unchanged behavior
- Auto-detection: no user config needed
- In-memory only: images stored as base64, discarded after enrichment
- Graceful degradation: per-element errors don't fail the batch