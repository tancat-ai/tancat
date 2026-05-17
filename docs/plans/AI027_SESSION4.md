# Session 4 (Corrected): Journey Selector Propagation

**AI-027 — Visual Element Enrichment**
**Replaces:** AI027_SESSION4.md (stale method references)
**Created:** 2026-05-17
**Depends on:** Sessions 1-3 complete (but can run independently of 2-3)

---

## What This Session Does

Merges journey-discovered selectors into the scraped_data dict so the
placeholder resolver can use verified selectors from journey discovery.

This directly fixes:
- B-013: "finish button" unresolved because checkout-step-two not scraped
- B-012 (partial): correct add-to-cart selector was clicked during discovery
  but not available to resolver

---

## Critical: Stale References in Original Spec

The original Session 4 spec references these methods which DO NOT EXIST
or are wrong:

| Original spec says | Actual live code |
|-------------------|-----------------|
| `PlaceholderOrchestrator.resolve_placeholders()` | Does not exist |
| `PlaceholderResolver._resolve_action_placeholder()` | Does not exist in live path |
| `_build_combined_element_pool()` | Does not exist |

The live entry point is:
`PlaceholderOrchestrator._replace_placeholders_sequentially()` at line 197.

Called from `src/orchestrator.py` line 320:
```python
final_code = await self._placeholder_orchestrator._replace_placeholders_sequentially(
    skeleton_code=...,
    journeys=...,
    page_requirements=...,
    seed_urls=...,
    scraped_data=scraped_data,   ← this is where journey selectors merge
    scraped_errors=...,
)
```

---

## Implementation

### Task 1: Add `_extract_journey_selectors()` to `src/orchestrator.py`

Add this private method to `TestOrchestrator`:

```python
def _extract_journey_selectors(
    self,
    all_scraped_data: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, str]]]:
    """Build synthetic element entries from journey-discovered selectors.

    For each URL scraped during journey discovery, creates a lightweight
    element dict from the selector that was successfully clicked/filled.
    These elements get a _journey_discovered flag so the resolver can
    apply a score bonus.

    Args:
        all_scraped_data: The scraped_data dict from journey discovery,
            keyed by URL with element lists as values.

    Returns:
        Dict in the same format as scraped_data — safe to merge directly.
    """
    journey_elements: dict[str, list[dict[str, str]]] = {}
    for url, elements in all_scraped_data.items():
        synthetic = []
        for element in elements:
            selector = element.get("selector", "")
            if not selector:
                continue
            synthetic.append({
                "selector": selector,
                "text": element.get("text", ""),
                "role": element.get("role", ""),
                "href": element.get("href", ""),
                "aria_label": element.get("aria_label", ""),
                "accessible_name": element.get("accessible_name", ""),
                "is_visible": element.get("is_visible", "true"),
                "_journey_discovered": "true",
            })
        if synthetic:
            journey_elements[url] = synthetic
    return journey_elements
```

### Task 2: Merge journey selectors into scraped_data in `src/orchestrator.py`

Find the call to `_replace_placeholders_sequentially` at line 320.
Before that call, find where `all_scraped_data` is built from journey
discovery (around lines 280-315). After `all_scraped_data` is populated,
add:

```python
# Merge journey-discovered selectors into scraped_data so the resolver
# can use verified selectors from journey execution.
journey_selector_data = self._extract_journey_selectors(all_scraped_data)
for url, elements in journey_selector_data.items():
    if url not in scraped_data:
        scraped_data[url] = elements
    else:
        # Append journey elements — don't replace static scrape
        scraped_data[url] = scraped_data[url] + elements
```

Do NOT modify `_replace_placeholders_sequentially` signature.
Do NOT modify `PlaceholderOrchestrator`.
Do NOT modify `PlaceholderResolver`.

### Task 3: Add journey score bonus in `src/placeholder_orchestrator.py`

In `_pass1_text_match()` and `_pass1_assert_text_match()`, after the
existing text match check returns an element, check whether it is a
journey-discovered element. No change needed — Pass 1 already returns
the first text match regardless of source.

In `_find_best_element_for_current_page()`, Pass 3 calls
`resolver.rank_candidates()`. In `src/placeholder_resolver.py`,
find `rank_candidates()` and add journey bonus:

```python
# Journey-discovered elements get +5 score bonus (verified at runtime)
if element.get("_journey_discovered") == "true":
    score += 5
```

Add this bonus inside the scoring loop in `rank_candidates()`, after
the existing score calculation for each element.

### Task 4: Create `tests/test_journey_selector_propagation.py`

```python
"""Tests for journey selector propagation into the resolver element pool."""
from __future__ import annotations

import pytest
from src.orchestrator import TestOrchestrator


class TestExtractJourneySelectors:

    def test_extracts_selectors_from_scraped_data(self) -> None:
        """Journey selectors should be extracted from all_scraped_data."""
        orchestrator = TestOrchestrator.__new__(TestOrchestrator)
        all_scraped = {
            "https://example.com": [
                {"selector": "#login-button", "text": "Login",
                 "role": "button", "href": "", "aria_label": "",
                 "accessible_name": "", "is_visible": "true"},
            ]
        }
        result = orchestrator._extract_journey_selectors(all_scraped)
        assert "https://example.com" in result
        assert result["https://example.com"][0]["selector"] == "#login-button"
        assert result["https://example.com"][0]["_journey_discovered"] == "true"

    def test_skips_elements_without_selector(self) -> None:
        """Elements with no selector should be skipped."""
        orchestrator = TestOrchestrator.__new__(TestOrchestrator)
        all_scraped = {
            "https://example.com": [
                {"selector": "", "text": "empty"},
                {"selector": "#btn", "text": "Button",
                 "role": "button", "href": "", "aria_label": "",
                 "accessible_name": "", "is_visible": "true"},
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
        all_scraped = {
            "https://example.com": [
                {"selector": "#checkout", "text": "Checkout",
                 "role": "button", "href": "", "aria_label": "",
                 "accessible_name": "Checkout", "is_visible": "true"},
            ]
        }
        result = orchestrator._extract_journey_selectors(all_scraped)
        elem = result["https://example.com"][0]
        assert elem["text"] == "Checkout"
        assert elem["role"] == "button"
        assert elem["accessible_name"] == "Checkout"
```

---

## Files Modified

| File | Change |
|------|--------|
| `src/orchestrator.py` | Add `_extract_journey_selectors()`, merge into scraped_data before resolution |
| `src/placeholder_resolver.py` | Add +5 journey bonus in `rank_candidates()` |
| `tests/test_journey_selector_propagation.py` | NEW — 4 tests |

## Files NOT Modified

- `src/placeholder_orchestrator.py` — no signature change needed
- `src/llm_client.py` — protected
- `src/test_generator.py` — protected

---

## Protected Files (DO NOT TOUCH)

`src/llm_client.py`, `src/test_generator.py`, `.github/workflows/ci.yml`

---

## Verification

```bash
bash fix.sh
pytest tests/test_journey_selector_propagation.py -v
pytest tests/ -v
python scripts/uat/uat_automationexercise.py --provider lm-studio --site saucedemo --run
```

Expected: "finish button" now resolves from checkout-step-two journey data.

Stop after these changes. Do not modify any other files.
