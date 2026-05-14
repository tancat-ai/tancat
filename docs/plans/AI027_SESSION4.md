# Session 4: Journey Selector Propagation + Resolver Integration

**AI-027 — Visual Element Enrichment**  
**Created:** 2026-05-13  
**Depends on:** Session 3 (Vision enrichment service complete)  
**Original spec:** `docs/specs/FEATURE_SPEC_visual_element_enrichment.md`

---

## Goal

Propagate journey-discovered selectors to the placeholder resolver and integrate enriched element metadata into the resolution pipeline. This is the final session that ties everything together.

**Deliverables:**
- `src/orchestrator.py` — modified: merge journey selectors into resolver pool
- `src/placeholder_orchestrator.py` — modified: use enriched metadata for matching
- `tests/test_journey_selector_propagation.py` — Integration tests
- Updated documentation
- End-to-end verification with saucedemo.com UAT script

---

## Current State of Relevant Files

### src/orchestrator.py
- `TestOrchestrator.run_pipeline()` — orchestrates scraping → journey discovery → resolution
- Journey discovery results contain verified selectors but they're not passed to resolver
- **Needs:** Merge journey-discovered selectors into resolver element pool

### src/placeholder_orchestrator.py
- `PlaceholderOrchestrator.resolve_placeholders()` — resolves `{{ACTION:description}}` placeholders
- Uses static-scraped elements only
- **Needs:** Access to journey-discovered selectors + enriched metadata

### src/placeholder_resolver.py
- `PlaceholderResolver._resolve_action_placeholder()` — matches descriptions to elements
- Text matching against class names, IDs, data attributes
- **Needs:** Use enriched `product_name` field for product-specific matching

### src/vision_enricher.py (from Sessions 1-3)
- Full implementation with vision LLM calls
- Enriched elements have `product_name`, `price`, `description`, `visual_label` fields
- **Needs:** Integration into resolver pipeline

---

## Implementation Tasks

### Task 1: Modify `TestOrchestrator.run_pipeline()` in `src/orchestrator.py`

**After journey discovery phase, merge selectors:**

```python
def run_pipeline(
    self,
    user_story: str,
    target_urls: list[str],
    journey_steps: list[dict] | None = None,
    credential_profile: dict[str, Any] | None = None,
    provider: str = "ollama",
    model: str = "qwen3.5:35b",
) -> PipelineRunResult:
    # ... existing pipeline code ...

    # Phase: journey_discovery
    journey_results = self._execute_journey_discovery(
        target_urls, journey_steps, credential_profile, provider, model
    )

    # NEW: Merge journey-discovered selectors into element pool
    journey_selectors = self._extract_journey_selectors(journey_results)

    # Phase: resolve_placeholders — pass enriched elements + journey selectors
    resolved_skeletons = self.placeholder_orchestrator.resolve_placeholders(
        skeletons=skeletons,
        scraped_data=page_contexts,
        journey_selectors=journey_selectors,
        provider=provider,
        model=model,
    )

    # ... rest of pipeline ...

def _extract_journey_selectors(
    self, journey_results: list[Any]
) -> list[dict[str, Any]]:
    """Extract verified selectors from journey discovery results.

    Returns list of selector dicts:
    {
        "selector": str,
        "url": str,
        "step_type": str,
        "step_label": str,
        "is_journey_discovered": True,
    }
    """
```

### Task 2: Modify `PlaceholderOrchestrator.resolve_placeholders()` in `src/placeholder_orchestrator.py`

```python
def resolve_placeholders(
    self,
    skeletons: list[str],
    scraped_data: list[PageContext],
    journey_selectors: list[dict[str, Any]] | None = None,
    provider: str = "ollama",
    model: str = "qwen3.5:35b",
) -> list[str]:
    """Resolve placeholders in skeleton tests.

    Args:
        skeletons: List of skeleton test strings.
        scraped_data: List of scraped page contexts with enriched elements.
        journey_selectors: Optional journey-discovered selectors.
        provider: LLM provider name.
        model: LLM model name.

    Returns:
        Resolved test strings.
    """
    # Build combined element pool: static-scraped + journey-discovered
    element_pool = self._build_combined_element_pool(scraped_data, journey_selectors)

    # Resolve placeholders using enriched element pool
    resolved = []
    for skeleton in skeletons:
        resolved_text = self._resolve_skeleton(skeleton, element_pool, provider, model)
        resolved.append(resolved_text)

    return resolved

def _build_combined_element_pool(
    self,
    scraped_data: list[PageContext],
    journey_selectors: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build combined element pool from static-scraped + journey-discovered elements.

    Journey-discovered selectors get a +5 score bonus because they were
    verified to work at runtime.
    """
    pool: list[dict[str, Any]] = []

    # Add static-scraped elements (with enriched metadata if available)
    for ctx in scraped_data:
        for elem in ctx.elements:
            pool_elem = dict(elem)
            pool_elem["_source"] = "static"
            pool.append(pool_elem)

    # Add journey-discovered selectors
    if journey_selectors:
        for sel in journey_selectors:
            pool_elem = {
                "selector": sel["selector"],
                "url": sel["url"],
                "step_type": sel["step_type"],
                "step_label": sel["step_label"],
                "text": sel.get("step_label", ""),
                "_source": "journey",
                "_journey_bonus": True,
            }
            pool.append(pool_elem)

    return pool
```

### Task 3: Modify `PlaceholderResolver._resolve_action_placeholder()` in `src/placeholder_resolver.py`

**Enhanced matching with enriched metadata:**

```python
def _resolve_action_placeholder(
    self,
    action: str,
    elements: list[dict[str, Any]],
    current_url: str | None = None,
) -> str | None:
    """Resolve an action placeholder to the best matching element selector.

    Enhanced matching order:
    1. Match description against enriched product_name field (+15 confidence)
    2. Match description against element text content (+10 confidence)
    3. Match description against element attributes (+5 confidence)
    4. Fallback to best available match
    """
    best_match: str | None = None
    best_score = 0

    for elem in elements:
        score = self._calculate_match_score(action, elem)

        # Journey-discovered bonus (+5)
        if elem.get("_journey_bonus"):
            score += 5

        # Product name enrichment bonus (+15)
        product_name = elem.get("product_name")
        if product_name and product_name.lower() in action.lower():
            score += 15

        if score > best_score:
            best_score = score
            best_match = elem.get("selector")

    return best_match if best_score > self._min_confidence else None

def _calculate_match_score(
    self,
    action: str,
    element: dict[str, Any],
) -> int:
    """Calculate match score between action description and element.

    Uses enriched metadata fields when available.
    """
    score = 0
    action_lower = action.lower()

    # Text content match
    elem_text = (element.get("text") or "").lower()
    if elem_text and any(word in action_lower for word in elem_text.split()):
        score += 10

    # Description field match (from vision enrichment)
    description = (element.get("description") or "").lower()
    if description and any(word in action_lower for word in description.split()):
        score += 8

    # Visual label match (from vision enrichment)
    visual_label = (element.get("visual_label") or "").lower()
    if visual_label and any(word in action_lower for word in visual_label.split()):
        score += 7

    # Attribute-based matching (existing logic)
    for attr_name, attr_value in element.get("attributes", {}).items():
        if attr_value and attr_value.lower() in action_lower:
            score += 3

    # Locator scorer bonus (existing logic)
    selector = element.get("selector", "")
    score += self.locator_scorer.score_selector(selector)

    return score
```

### Task 4: Create `tests/test_journey_selector_propagation.py`

```python
"""Tests for journey selector propagation and enriched resolver integration."""

import pytest

from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_resolver import PlaceholderResolver


class TestJourneySelectorPropagation:
    """Test journey-discovered selectors are merged into resolver pool."""

    def test_journey_selectors_added_to_element_pool(self) -> None:
        """Journey-discovered selectors should be in the combined element pool."""

    def test_journey_selectors_get_score_bonus(self) -> None:
        """Journey-discovered selectors should get +5 score bonus."""

    def test_journey_selectors_preserve_step_metadata(self) -> None:
        """Journey selectors should include step_type and step_label."""


class TestEnrichedResolverMatching:
    """Test resolver matching with enriched metadata."""

    def test_product_name_match_gets_bonus(self) -> None:
        """Elements with matching product_name should get +15 confidence."""

    def test_description_field_match_gets_bonus(self) -> None:
        """Elements with matching description should get +8 confidence."""

    def test_visual_label_match_gets_bonus(self) -> None:
        """Elements with matching visual_label should get +7 confidence."""

    def test_journey_bonus_applied_to_matching_selector(self) -> None:
        """Journey bonus should be applied when selector matches."""

    def test_enriched_elements_override_text_only_elements(self) -> None:
        """Enriched element should beat text-only element on score."""

    def test_non_enriched_elements_still_match(self) -> None:
        """Elements without enrichment should still match via text/attributes."""


class TestCombinedElementPool:
    """Test combined element pool construction."""

    def test_pool_contains_static_elements(self) -> None:
        """Static-scraped elements should be in the pool."""

    def test_pool_contains_journey_selectors(self) -> None:
        """Journey-discovered selectors should be in the pool."""

    def test_static_elements_marked_source(self) -> None:
        """Static elements should have _source='static'."""

    def test_journey_elements_marked_source(self) -> None:
        """Journey elements should have _source='journey'."""
```

### Task 5: Update documentation

### docs/ARCHITECTURE.md
Update "Orchestration Layer" table:
```
| `src/orchestrator.py` (`TestOrchestrator`) | Pipeline brain. Manages execution via run_pipeline():
|                                             | analysis → skeleton generation → scraping → journey discovery →
|                                             | selector propagation → placeholder resolution → post-processing.
```

### docs/PROJECT_KNOWLEDGE.md
Add to "Architecture Decisions":
```
| Resolver element pool | Combined pool: static-scraped elements + journey-discovered selectors.
|                       | Journey selectors get +5 bonus. Enriched elements get product_name/description/
|                       | visual_label fields for improved matching (+15/+8/+7 bonuses).
```

### BACKLOG.md
Update AI-027 status:
```
### AI-027 — Visual Element Enrichment (COMPLETE — All 4 sessions done)
**Session 1 complete:** VisionEnricher + vision capability detection
**Session 2 complete:** Screenshot capture during scraping
**Session 3 complete:** Vision enrichment service + crop + LLM call
**Session 4 complete:** Journey selector propagation + resolver integration
**End-to-end verification:** saucedemo.com UAT script — all 6 tests pass
```

### CHANGELOG.md
Add entry:
```
| 1.8.0 | 2026-05-13 | AI-027 COMPLETE: Visual element enrichment, journey selector propagation,
             |            | enhanced resolver text matching — end-to-end verified on saucedemo.com
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

1. `ruff check src/orchestrator.py src/placeholder_orchestrator.py src/placeholder_resolver.py` — clean
2. `mypy src/orchestrator.py src/placeholder_orchestrator.py src/placeholder_resolver.py` — clean
3. `pytest tests/test_journey_selector_propagation.py -v` — all green
4. `pytest tests/ -v` — ALL existing tests still pass
5. **End-to-end: Run UAT script against saucedemo with vision-capable model**
   ```bash
   python scripts/uat/uat_automationexercise.py --provider lm-studio --site saucedemo --run
   ```
   Expected: All 6 tests pass (was 4/6 before this feature)

---

## Expected Test Count

- `test_journey_selector_propagation.py`: 14 tests minimum
  - 3 tests for journey selector propagation
  - 6 tests for enriched resolver matching
  - 4 tests for combined element pool
  - 1 test for error handling