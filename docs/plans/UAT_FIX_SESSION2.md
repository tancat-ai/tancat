# Session 2: ASSERT Description Refinement via LLM

**UAT Fix Series — Session 2 of 3**  
**Created:** 2026-05-13  
**Depends on:** Session 1 (LLM disambiguation infrastructure)  
**Original backlog:** BACKLOG.md "Session 3 — Skeleton Prompt: Specific Assertions" (lines 977-995)

---

## Goal

Add post-generation refinement of vague ASSERT placeholders. After skeleton generation detects ASSERT placeholders with generic descriptions (e.g., `ASSERT:button visible`, `ASSERT:message displayed`), send them to the LLM for contextual rewrite using the test function's other steps as context.

**Problem**: ASSERT placeholders like `ASSERT:button visible` resolve to wrong elements (e.g., `.cart_quantity_delete` instead of confirmation popup). Adding growing lists of "good vs bad" examples to the skeleton prompt creates prompt explosion.

**Solution**: Detect vague ASSERT descriptions after generation, use the LLM to rewrite them with context from sibling steps — one targeted call per vague placeholder, not a growing prompt template.

**Deliverables:**
- `src/skeleton_parser.py` or new `src/assert_refiner.py` — `_refine_assert_descriptions()` function
- `tests/test_assert_refiner.py` — unit tests
- BACKLOG.md updated

---

## Current State

### `src/prompt_utils.py`

- `get_skeleton_prompt_template()` (line 83): Specifies `{{ASSERT:visible element description}}` format.
- Example (line 125): `{{ASSERT:welcome message}}` — decent but not explicit enough.
- No guidance on making ASSERT descriptions contextual and specific.

### `src/skeleton_parser.py`

- Parses skeleton output, extracts placeholder tokens.
- Already identifies placeholder type (CLICK, FILL, ASSERT, GOTO) and description.

### Why post-generation refinement instead of prompt engineering

Adding examples to the skeleton prompt means:
1. More prompt tokens = slower LLM responses
2. Each new edge case = another example to add
3. Examples compete for LLM attention — too many = worse compliance

Post-generation approach:
1. Detect vague patterns with simple heuristics (no prompt changes needed)
2. One small LLM call per vague placeholder (~50 tokens each)
3. Uses actual test context (sibling steps) as guidance

---

## Implementation Tasks

### Task 1: Create `src/assert_refiner.py`

```python
"""ASSERT placeholder refinement module.

After skeleton generation, detects vague ASSERT descriptions and rewrites
them using the LLM with contextual information from sibling test steps.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Patterns that indicate a vague ASSERT description.
# These are descriptions that are too generic to resolve reliably.
VAGUE_ASSERT_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(button|link|element|message|text|content)\s*(visible|displayed|shown|present|available)?$", re.I),
    re.compile(r"^(it|there)\s+", re.I),  # "it is visible", "there is a message"
    re.compile(r"^success(ful)?\s*(message|text)?$", re.I),
    re.compile(r"^confirmation(\s*message)?$", re.I),
]

# Minimum meaningful word count for an ASSERT description.
# "button visible" = 2 words but both are generic → still vague.
# "product added to cart confirmation" = 5 words, specific → not vague.
MIN_SPECIFIC_WORDS: int = 3

# Generic words that don't add specificity to ASSERT descriptions.
GENERIC_ASSERT_WORDS: set[str] = {
    "button", "link", "element", "message", "text", "content",
    "visible", "displayed", "shown", "present", "available",
    "the", "a", "an", "is", "are", "it", "its",
}


def is_vague_assert(description: str) -> bool:
    """Check if an ASSERT description is too vague to resolve reliably.

    A description is vague if:
    1. It matches a known vague pattern (e.g., "button visible")
    2. It has fewer than MIN_SPECIFIC_WORDS non-generic words

    Args:
        description: The ASSERT placeholder description text.

    Returns:
        True if the description is too vague for reliable resolution.
    """


def refine_assert_descriptions(
    skeletons: list[dict[str, Any]],
    llm_client: Any,  # LLMClient — avoid circular import
    user_story: str,
) -> list[dict[str, Any]]:
    """Rewrite vague ASSERT descriptions using the LLM.

    For each skeleton with vague ASSERT placeholders, sends the test context
    (user story + sibling steps) to the LLM and replaces the description.

    Args:
        skeletons: List of skeleton dicts with placeholder steps.
        llm_client: LLMClient instance for refinement calls.
        user_story: The user story text for context.

    Returns:
        Skeletons with refined ASSERT descriptions. Unchanged if LLM unavailable.
    """
```

**Refinement prompt template:**

```
Refine this ASSERT placeholder to be more specific.

User Story: {user_story}

Test steps so far:
{steps_before_assert}

Current ASSERT placeholder: {{ASSERT:{current_description}}}

What element should be visible on the page after these steps?
Return only the specific element description (no placeholder braces).

Examples:
- "button visible" → "product added to cart confirmation message"
- "message displayed" → "order confirmation success banner"
- "text shown" → "cart item count updated to 1"
```

**Key design:**
- Only processes ASSERT placeholders that fail `is_vague_assert()`
- Uses the steps *before* the ASSERT as context (what actions led here?)
- LLM returns plain text description — wrapped back into `{{ASSERT:...}}`
- If LLM call fails, keeps original description (no hard failure)
- Config: `USE_ASSERT_REFINEMENT` env var (default: true)

### Task 2: Integrate into the skeleton pipeline

In `src/orchestrator.py` or `src/pipeline_models.py` (where skeleton generation flows), add the refinement step after skeleton parsing:

```python
# After skeleton parsing, before placeholder resolution:
from src.assert_refiner import refine_assert_descriptions

skeletons = refine_assert_descriptions(
    skeletons=parsed_skeletons,
    llm_client=self.llm_client,
    user_story=user_story,
)
```

### Task 3: Create `tests/test_assert_refiner.py`

```python
"""Tests for ASSERT description refinement."""

import pytest
from unittest.mock import MagicMock, patch

from src.assert_refiner import is_vague_assert, refine_assert_descriptions


class TestIsVagueAssert:
    """Test vague ASSERT detection."""

    def test_button_visible_is_vague(self) -> None:
        assert is_vague_assert("button visible") is True

    def test_message_displayed_is_vague(self) -> None:
        assert is_vague_assert("message displayed") is True

    def test_element_shown_is_vague(self) -> None:
        assert is_vague_assert("element shown") is True

    def test_success_message_is_vague(self) -> None:
        assert is_vague_assert("success message") is True

    def test_product_added_confirmation_is_specific(self) -> None:
        assert is_vague_assert("product added to cart confirmation message") is False

    def test_cart_badge_updated_is_specific(self) -> None:
        assert is_vague_assert("cart badge updated") is False

    def test_welcome_message_is_specific(self) -> None:
        assert is_vague_assert("welcome message") is False

    def test_it_is_visible_is_vague(self) -> None:
        assert is_vague_assert("it is visible") is True

    def test_confirmation_message_is_vague(self) -> None:
        assert is_vague_assert("confirmation message") is True


class TestRefineAssertDescriptions:
    """Test the LLM refinement of ASSERT descriptions."""

    def test_vague_assert_is_refined(self) -> None:
        """Vague ASSERT gets rewritten by LLM."""

    def test_specific_assert_is_not_changed(self) -> None:
        """Specific ASSERT passes through unchanged."""

    def test_refinement_uses_sibling_steps_as_context(self) -> None:
        """LLM prompt includes steps before the ASSERT."""

    def test_refinement_uses_user_story_as_context(self) -> None:
        """LLM prompt includes the user story."""

    def test_refinement_falls_back_on_llm_error(self) -> None:
        """When LLM fails, keeps original description."""

    def test_refinement_disabled_via_env(self) -> None:
        """USE_ASSERT_REFINEMENT=false skips refinement."""

    def test_multiple_asserts_in_one_skeleton(self) -> None:
        """Multiple vague ASSERTs in one test are all refined."""


class TestUATRegression:
    """Regression tests for UAT failures."""

    def test_add_to_cart_assert_refined(self) -> None:
        """
        'ASSERT:button visible' after 'CLICK:add to cart' should refine to
        something like 'product added to cart confirmation'.
        """

    def test_checkout_assert_refined(self) -> None:
        """
        'ASSERT:message displayed' after 'GOTO:checkout' should refine to
        something contextual about checkout confirmation.
        """
```

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Helper functions:** Go in `src/`, NOT in `streamlit_app.py`
- **Quality gates:** ruff → mypy → pytest → human reviews diff → commit
- **Protected files — DO NOT TOUCH:**
  - `src/llm_client.py` — use existing `create_completion()`
  - `src/test_generator.py`
  - `.github/workflows/ci.yml`

---

## Verification Steps

1. `ruff check src/assert_refiner.py` — clean
2. `mypy src/assert_refiner.py` — clean
3. `pytest tests/test_assert_refiner.py -v` — all green
4. `pytest tests/ -v` — full suite passes (no regressions)
5. Manual test: Generate skeleton with vague ASSERT, verify refinement occurs

---

## Expected Test Count

- `test_assert_refiner.py`: 16 tests minimum
  - 9 tests for `is_vague_assert()` detection
  - 7 tests for `refine_assert_descriptions()` refinement logic

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM refinement adds latency | Only triggered for vague ASSERTs (estimated 10-20% of ASSERT placeholders). Configurable. |
| LLM refinement makes description worse | Unlikely — LLM is better at contextual description than vague patterns. Monitor via UAT. |
| Extra LLM tokens | ~50 tokens per vague ASSERT. Minimal cost. |
| Refinement changes working ASSERTs | `is_vague_assert()` only targets known vague patterns. Specific descriptions pass through unchanged. |

---

## Files Modified

| File | Change |
|------|--------|
| `src/assert_refiner.py` | NEW — vague detection + LLM refinement |
| `src/orchestrator.py` | Integrate refinement step in skeleton pipeline |
| `tests/test_assert_refiner.py` | NEW — 16 tests |
| `BACKLOG.md` | Update Session 2 status to IN PROGRESS |

---

## Relationship to Session 1

Session 1 adds LLM disambiguation to the __resolver__ (runtime matching). Session 2 adds LLM refinement to the __skeleton pipeline__ (generation time). They work together:

1. Session 2 improves ASSERT descriptions at generation time → fewer vague placeholders reach the resolver
2. Session 1 handles cases where even good descriptions produce tied candidates → LLM picks the winner

Both use `LLMClient.create_completion()` — no new infrastructure needed beyond what Session 1 establishes.