# FEATURE SPEC: AI-027 — Visual Element Enrichment

**Status:** Design complete — ready for implementation  
**Priority:** High — placeholder resolution quality on multi-product sites  
**Created:** 2026-05-13  
**Spec author:** Architecture review  
**Cline sessions:** 4 (strict order, one session per task)

---

## Problem Statement

The placeholder resolver fails to correctly identify elements on multi-product e-commerce sites because it relies solely on text matching against scraped DOM metadata. The latest UAT run against saucedemo.com revealed:

| Symptom | Root Cause |
|---------|-----------|
| `#add-to-cart-test.allthethings\(\)-t-shirt-\(red\)` matched for "Sauce Labs Backpack add to cart button" | Resolver matched on shared `data-product-id` attribute, not product identity |
| `#user-name` matched for "Sauce Labs Backpack item name visible in cart" | Resolver found first element with matching attribute, not the product name element |
| `.product_sort_container` matched for "checkout information form loaded" | Cross-page element returned because resolver couldn't distinguish page context |
| `.product_sort_container[data-test="product-sort-container"]` matched for "first name input:John" | Resolver fell back to any element with matching class, ignoring semantic meaning |
| "shopping cart icon", "checkout button", "finish button" — all unresolved | Elements existed on pages but weren't in the resolver's element pool |

**Core problem:** The resolver has no way to distinguish "add to cart button for Product A" from "add to cart button for Product B" when both have similar DOM structure. Text matching against class names, IDs, and data attributes is insufficient when e-commerce sites use generic patterns like `data-product-id="42"` on every product card.

---

## Solution: Vision-Based Metadata Enrichment

### Design Principle

**Vision is a metadata enricher, not a matcher.** The vision LLM converts element images → structured text. The actual element matching is always done by the existing text-based resolver.

This means:
- Users with vision-capable LLMs get enriched element metadata → better matching
- Users without vision-capable LLMs get exactly what they have today → zero regression
- The resolver code path is unchanged — it always works with text fields

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Scraping Phase (NEW)                                    │
│                                                          │
│  1. Scrape DOM → elements with text metadata (existing)  │
│  2. Capture full-page screenshot (NEW)                   │
│  3. Crop element bounding boxes (NEW)                    │
│  4. [IF vision LLM] Analyze cropped images (NEW)         │
│     → Returns: product name, price, description          │
│     → Stored as text fields on elements                  │
│  5. Store cropped images as base64 in element dict       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Placeholder Resolution (UNCHANGED)                       │
│                                                          │
│  - Uses text fields: product_name, price, description    │
│  - Works with or without vision enrichment               │
│  - Falls back to best available match                    │
│  - No code path changes                                  │
└─────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vision as enricher | Structured text output, not direct matching | Keeps resolver unchanged; vision is optional |
| Image storage | Base64 in element dict (in-memory only) | No disk I/O; images used once during enrichment |
| Vision detection | Auto-detect from LLM provider config | No user config needed; graceful degradation |
| Fallback | Skip enrichment if vision unavailable | Zero regression for text-only users |
| Screenshot scope | One screenshot per page during scraping | Minimal overhead; covers all elements on page |

---

## Phase 1: Image Capture + Vision Enrichment

### 1.1 Screenshot Capture During Scraping

**New method in `src/scraper.py`:**

```python
def capture_page_screenshot(
    page: Page,
    url: str,
    full_page: bool = True,
) -> tuple[bytes, list[dict]]:
    """Capture a full-page screenshot and extract element bounding boxes.

    Returns:
        (screenshot_bytes, element_boxes) where element_boxes is a list of:
        {
            "selector": str,           # Element selector
            "bbox": dict,              # {x, y, width, height} in viewport coords
            "element": dict,           # Original scraped element metadata
            "is_visible": bool,        # Whether element is visible
        }
    """
```

**Behavior:**
- Captures one full-page screenshot per URL during scraping
- Iterates all interactive elements (`button, a, input, select, [onclick], [role=button]`)
- Extracts bounding box via `element.bounding_box()` in the browser
- Filters out elements with zero dimensions or outside viewport
- Returns screenshot bytes + list of element boxes

### 1.2 Vision Enrichment Service

**New file: `src/vision_enricher.py`**

```python
class VisionEnricher:
    """Enrich scraped elements with vision-based metadata.

    Uses a vision-capable LLM to analyze cropped element images
    and return structured text metadata.
    """

    @classmethod
    def enrich_elements(
        cls,
        elements: list[dict],
        screenshot_bytes: bytes,
        provider: str,
        model: str,
    ) -> list[dict]:
        """Enrich elements with vision-derived metadata.

        Args:
            elements: List of scraped element dicts.
            screenshot_bytes: Full-page screenshot PNG bytes.
            provider: LLM provider name (ollama, lm-studio, etc.).
            model: LLM model name.

        Returns:
            Enriched elements with new fields:
            - "product_name": str or None
            - "price": str or None
            - "description": str or None
            - "visual_label": str or None  # e.g., "backpack product image"
            - "enrichment_note": str or None  # e.g., "product card"
        """

    @classmethod
    def is_vision_capable(
        cls,
        provider: str,
        model: str,
    ) -> bool:
        """Detect whether the configured LLM supports vision.

        Checks:
        1. Model name against known vision-capable list
        2. Provider API for vision capability metadata
        3. Graceful fallback to False if detection fails
        """
```

### 1.3 Vision Capability Detection

**Detection logic (in order of priority):**

1. **Model name heuristics** — Check against known vision-capable models:
   - Qwen: `qwen2.5-vl`, `qwen3.6-35b-a3b`, `qwen3.5-35b`
   - LLaVA: `llava`, `llava-1.6`
   - GPT-4: `gpt-4-vision`, `gpt-4o`
   - Gemini: `gemini-pro-vision`, `gemini-2.0`
   - Claude: `claude-3-opus`, `claude-3-sonnet`, `claude-3.5-sonnet`
   - Any model containing `vl`, `vision`, or `mm` in name → likely vision

2. **Provider API check** — For OpenAI/Anthropic/Gemini providers,
   query the API for available models and their capabilities

3. **Graceful fallback** — If detection fails, return `False` (no enrichment)

### 1.4 Integration with Scraper Pipeline

**Modified in `src/scraper.py`:**

After existing DOM scraping for each URL:
1. Capture full-page screenshot
2. Extract bounding boxes for all interactive elements
3. If `VisionEnricher.is_vision_capable()`:
   a. Crop each element from screenshot using bounding box
   b. Send cropped images + element metadata to vision LLM
   c. Store returned metadata in element dicts
4. Return enriched elements + screenshot bytes to orchestrator

**Modified in `src/orchestrator.py`:**

After scraping phase, pass enriched elements to placeholder orchestrator.
No changes to placeholder resolver — it reads the new text fields.

---

## Phase 2: Journey-Discovered Selector Propagation

### Problem

Several placeholders remain unresolved because the elements were found during
journey discovery but never passed to the placeholder resolver. The resolver
only sees static-scraped elements.

### Solution

**Modify `src/orchestrator.py`:**

After journey discovery completes, merge journey-discovered selectors into
the element pool available to the placeholder resolver:

```python
# After journey_discovery phase:
for journey_result in journey_results:
    for step in journey_result.steps:
        if step.selector:
            # Add to resolver's element pool
            resolver_element_pool.append({
                "selector": step.selector,
                "url": journey_result.url,
                "step_type": step.type,
                "step_label": step.label,
                "is_journey_discovered": True,
            })
```

**Modified in `src/placeholder_orchestrator.py`:**

The resolver now has access to both:
1. Static-scraped elements (from all pages)
2. Journey-discovered selectors (from execution)

When resolving a placeholder, check both pools. Journey-discovered selectors
get a small score bonus (+5) because they were verified to work at runtime.

---

## Phase 3: Enhanced Resolver Text Matching

### Problem

Even with vision-enriched metadata, the resolver needs to match descriptions
like "Sauce Labs Backpack add to cart button" to the correct element when
multiple product cards have identical DOM structure.

### Solution

**Modified in `src/placeholder_resolver.py`:**

When resolving a placeholder with a product name or specific identifier:

1. **Primary filter** — Match description text against enriched `product_name` field
2. **Secondary filter** — If no vision enrichment, match against element text content
3. **Tertiary filter** — Match against element's parent context (product card text)
4. **Score boost** — +15 confidence for exact product name match

**Example:**

Placeholder: `"Sauce Labs Backpack add to cart button"`
Enriched elements:
- Element A: `product_name="Sauce Labs Backpack"`, `selector="#add-to-cart-sauce-labs-backpack"`
- Element B: `product_name="Sauce Labs Fleece Jacket"`, `selector="#add-to-cart-sauce-labs-fleece-jacket"`

Resolution: Element A wins (product name match)

---

## Phase 4: Test-Time Image Verification (Future)

### Not in Scope for This Feature

A future enhancement could capture screenshots during test execution and
compare them against expected states. This is out of scope for the initial
implementation.

---

## Implementation Sequence (4 Cline Sessions)

| Order | Session | Scope | Files |
|-------|---------|-------|-------|
| 1 | AI-027-S1 | Vision capability detection + model registry | `src/vision_enricher.py`, `tests/test_vision_enricher.py` |
| 2 | AI-027-S2 | Screenshot capture during scraping | `src/scraper.py` (modified), `tests/test_scraper_screenshot.py` |
| 3 | AI-027-S3 | Vision enrichment service + crop + LLM call | `src/vision_enricher.py` (full), `src/scraper.py` (integration) |
| 4 | AI-027-S4 | Journey selector propagation + resolver integration | `src/orchestrator.py`, `src/placeholder_orchestrator.py`, `tests/test_journey_selector_propagation.py` |

**Rule:** Each session must end with `bash fix.sh` → `pytest tests/ -v` → green
before committing. Do not combine sessions.

---

## Documentation Updates (Per Session)

Each session must update:
- `docs/ARCHITECTURE.md` — Add new module to architecture diagram
- `docs/PROJECT_KNOWLEDGE.md` — Add vision enrichment to architecture decisions
- `BACKLOG.md` — Mark AI-027 as complete with session details
- `CHANGELOG.md` — Add version entry

---

## Quality Gates

All sessions must pass:
- `ruff check` — clean
- `mypy` — clean (all type annotations correct)
- `pytest` — green (all existing + new tests)
- End-to-end verification with saucedemo.com UAT script

---

## Acceptance Criteria

1. ✅ Users with vision-capable LLMs get enriched element metadata during scraping
2. ✅ Users without vision-capable LLMs experience zero regression
3. ✅ Vision capability auto-detected — no user config needed
4. ✅ Product-specific placeholders resolve correctly on saucedemo.com
5. ✅ Journey-discovered selectors are available to placeholder resolver
6. ✅ All existing tests continue to pass
7. ✅ New tests cover vision detection, screenshot capture, enrichment, and selector propagation

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Vision LLM adds significant scraping time | Crop + analyze in parallel; timeout after 30s per element |
| Non-vision LLM returns garbled output | Structured output format; validation before storing |
| Screenshot capture fails on slow pages | Retry once; proceed without enrichment if both attempts fail |
| Base64 images increase memory usage | Images stored only in-memory during scraping; discarded after enrichment |
| Bounding boxes inaccurate on dynamic pages | Use Playwright's `bounding_box()` which returns actual rendered coords |