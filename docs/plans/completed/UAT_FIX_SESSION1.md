# Session 1: LLM Disambiguation for Placeholder Resolution

**UAT Fix Series — Session 1 of 3**  
**Created:** 2026-05-13  
**Depends on:** AI-024 (accessibility_enricher.py — a11y tree capture already complete)  
**Original backlog:** BACKLOG.md "Session 1 — Visibility Filtering" (lines 921-948)

---

## Goal

Add LLM-based disambiguation to `PlaceholderResolver` for tied candidates. When rule-based scoring in `rank_candidates()` produces top-2 candidates within a score threshold, delegate the final decision to the local LLM using Aria snapshot context.

**Problem**: "Products link" resolves to brand product link because rule-based scoring can't distinguish navigation elements from embedded marketing links. Adding more scoring rules creates layering debt.

**Solution**: Keep rule-based scoring as the fast path. When rules can't decide (near-tie), use the LLM with Aria snapshot context — one targeted call replaces dozens of scoring rules.

**Deliverables:**
- `src/placeholder_resolver.py` — `_disambiguate_with_llm()` method + integration in `find_best_element()`
- `tests/test_placeholder_resolver_disambiguation.py` — unit tests for disambiguation
- BACKLOG.md updated

---

## Current State

### `src/placeholder_resolver.py`

- `rank_candidates()` (line 331): Returns scored candidates descending. ~60 lines of scoring special cases already exist.
- `find_best_element()` (line 252): Iterates ranked candidates, applies text validation + confidence threshold, returns first match.
- No LLM integration currently — resolver is pure rule-based.

### `src/accessibility_enricher.py`

- Already captures a11y tree via `page.accessibility.snapshot()` (AI-024).
- Elements enriched with `accessible_name` field.
- Data available in element dicts passed to resolver.

### `src/llm_client.py` (PROTECTED — add method only)

- `LLMClient.create_completion()` exists for text prompts.
- Can be reused for disambiguation prompts — no new method needed.

### `src/llm_reasoning_filter.py`

- `strip_reasoning_text()` already exists — strips LLM prose, returns clean answer.
- Can be used to parse the disambiguation response (single index number).

---

## Implementation Tasks

### Task 1: Add `_disambiguate_with_llm()` to PlaceholderResolver

```python
def _disambiguate_with_llm(
    self,
    action: str,
    description: str,
    top_candidates: list[tuple[int, dict[str, Any]]],
    aria_snapshot: str | None = None,
) -> dict[str, Any] | None:
    """Use the LLM to pick the best element when rule-based scoring produces a tie.

    When the top-2 candidates are within DISAMBIGUATION_THRESHOLD points,
    delegate to the LLM with structured context (Aria snapshot + candidate details).

    Args:
        action: Placeholder action (CLICK, FILL, ASSERT, GOTO).
        description: Placeholder description text.
        top_candidates: Top N scored candidates from rank_candidates().
        aria_snapshot: Aria snapshot text from page.ariaSnapshot() — optional fallback context.

    Returns:
        The winning element dict, or None if LLM unavailable or response unparsable.
    """
```

**Design decisions:**
- `DISAMBIGUATION_THRESHOLD = 5` — trigger when top-2 scores differ by ≤5 points
- `MAX_CANDIDATES_FOR_DISAMBIGUATION = 3` — send top 3 to LLM (not all, keeps prompt small)
- Prompt format — structured, minimal tokens:

```
Pick the element that matches: {action} "{description}"

Options:
1. text="{text}", role="{role}", selector="{selector}", id="{id}"
2. text="{text}", role="{role}", selector="{selector}", id="{id}"
3. text="{text}", role="{role}", selector="{selector}", id="{id}"

{aria_snapshot_context_if_available}

Return only the number (1-3) of the best match.
```

- Response parsing — extract single digit, validate against candidate count
- Fallback — if LLM call fails or returns unparsable response, fall back to rule-based (return highest-scored candidate)
- Config — `USE_LLM_DISAMBIGUATION` env var (default: true), `DISAMBIGUATION_THRESHOLD` env var (default: 5)

### Task 2: Integrate disambiguation into `find_best_element()`

In `find_best_element()` (line 252), after `rank_candidates()` returns:

```python
ranked_candidates = self.rank_candidates(action, description, page_elements)
if not ranked_candidates:
    return None

# Check if disambiguation is needed — top-2 within threshold
if len(ranked_candidates) >= 2:
    top_score = ranked_candidates[0][0]
    second_score = ranked_candidates[1][0]
    if top_score - second_score <= self.disambiguation_threshold:
        llm_pick = self._disambiguate_with_llm(
            action, description, ranked_candidates[:3],
            aria_snapshot=aria_snapshot  # passed from caller
        )
        if llm_pick:
            return llm_pick
```

### Task 3: Pass Aria snapshot context through the pipeline

The Aria snapshot needs to reach `find_best_element()`. Two options:

**Option A (preferred)**: Store per-page Aria snapshots in `page_elements` as a metadata element. The orchestrator already has access to a11y data.

**Option B**: Add `aria_snapshot: str | None` parameter to `find_best_element()` and `resolve_all()`.

Option A is cleaner — no API changes. The Aria snapshot can be stored as a special element dict:
```python
{"__meta__": "aria_snapshot", "text": "<aria snapshot string>"}
```

### Task 4: Create `tests/test_placeholder_resolver_disambiguation.py`

```python
"""Tests for LLM-based disambiguation in PlaceholderResolver."""

import pytest
from unittest.mock import patch, MagicMock

from src.placeholder_resolver import PlaceholderResolver


class TestDisambiguationTrigger:
    """Test that disambiguation triggers on near-ties."""

    def test_disambiguation_triggers_on_tie(self) -> None:
        """Top-2 candidates with same score should trigger LLM disambiguation."""

    def test_disambiguation_triggers_on_near_tie(self) -> None:
        """Top-2 candidates within threshold should trigger LLM disambiguation."""

    def test_disambiguation_skipped_on_clear_winner(self) -> None:
        """Top-2 candidates far apart should NOT trigger LLM disambiguation."""

    def test_disambiguation_skipped_when_single_candidate(self) -> None:
        """Only one candidate — no disambiguation needed."""


class TestDisambiguationLLMCall:
    """Test the LLM disambiguation method directly."""

    def test_disambiguation_returns_correct_element(self) -> None:
        """LLM picks option 2 → returns second candidate element."""

    def test_disambiguation_handles_out_of_range_response(self) -> None:
        """LLM returns invalid number → falls back to None."""

    def test_disambiguation_handles_llm_error(self) -> None:
        """LLM call raises exception → returns None (fallback to rules)."""

    def test_disambiguation_prompt_includes_action_and_description(self) -> None:
        """Prompt contains the action type and description text."""

    def test_disambiguation_prompt_includes_candidate_details(self) -> None:
        """Prompt contains text, role, selector for each candidate."""

    def test_disambiguation_with_aria_snapshot(self) -> None:
        """Aria snapshot context is included when available."""


class TestProductsLinkScenario:
    """Regression test for the 'Products link' vs brand product link scenario."""

    def test_products_link_prefers_navigation(self) -> None:
        """
        Given two 'Products' links — one in navigation, one brand marketing —
        the LLM should pick the navigation link for 'Products link'.
        """

    def test_products_link_fallback_to_rules(self) -> None:
        """
        When LLM unavailable, fall back to rule-based scoring.
        (May still pick wrong element — but doesn't crash.)
        """


class TestDisambiguationConfig:
    """Test environment variable configuration."""

    def test_disambiguation_disabled_via_env(self) -> None:
        """USE_LLM_DISAMBIGUATION=false skips LLM call."""

    def test_custom_threshold(self) -> None:
        """DISAMBIGUATION_THRESHOLD=10 uses custom threshold."""
```

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Helper functions:** Go in `src/`, NOT in `streamlit_app.py`
- **Quality gates:** ruff → mypy → pytest → human reviews diff → commit
- **Protected files — DO NOT TOUCH:**
  - `src/llm_client.py` — use existing `create_completion()`, do not modify
  - `src/test_generator.py`
  - `.github/workflows/ci.yml`

---

## Verification Steps

1. `ruff check src/placeholder_resolver.py` — clean
2. `mypy src/placeholder_resolver.py` — clean
3. `pytest tests/test_placeholder_resolver_disambiguation.py -v` — all green
4. `pytest tests/test_placeholder_resolver.py -v` — existing tests still pass
5. `pytest tests/ -v` — full suite passes
6. Manual test: Create scenario with two near-identical candidates, verify LLM is called

---

## Expected Test Count

- `test_placeholder_resolver_disambiguation.py`: 14 tests minimum
  - 4 tests for disambiguation trigger logic
  - 6 tests for LLM disambiguation method
  - 2 tests for Products link regression scenario
  - 2 tests for configuration

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM call adds latency | Only triggered on near-ties (estimated <5% of resolutions). Threshold configurable. |
| LLM unavailable (Ollama down) | Falls back to rule-based scoring. No hard failure. |
| LLM picks wrong element | Better than nothing — LLM understands context rules can't encode. Monitor via UAT. |
| Prompt tokens add up | Minimal prompt (~100 tokens per call). Only 3 candidates max. |

---

## Files Modified

| File | Change |
|------|--------|
| `src/placeholder_resolver.py` | Add `_disambiguate_with_llm()`, integrate in `find_best_element()`, add config params |
| `tests/test_placeholder_resolver_disambiguation.py` | NEW — 14 tests |
| `BACKLOG.md` | Update Session 1 status to IN PROGRESS |