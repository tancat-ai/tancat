# `src/element_matcher.py` — Multi-Pass Element Matching Engine

## Purpose
4-pass resolution pipeline (Pass 0–3) for matching placeholder descriptions to scraped DOM elements. Extracted from `placeholder_orchestrator.py`. Includes LLM-based semantic ASSERT resolution (B-020).

## Class: `ElementMatcher`
- `find_best_element_for_current_page(action, description, elements, ...) -> str | None` — single placeholder resolution
- `find_best_elements_batch(requests: list[dict]) -> list[dict]` — batched resolution (Pass 0-2 per request, Pass 3 in one LLM call)

## Resolution Passes
- **Pass 0**: Exact text match (accessible_name, aria_label, text)
- **Pass 1**: Action-verb-aware substring match (B-012)
  - **B-024g (2026-08-03):** separator-normalized word-subset fallback for FILL — every description word appearing as a word in the element text matches, so "zip code" → placeholder "Zip/Postal Code" (saucedemo checkout fields)
  - FILL gate: containers whose accessible_name collides with a field label must not win over the real input
- **Pass 2**: Structural match (ID, data-test, name attributes + camelCase splitting)
- **Pass 3**: LLM semantic ranking via `SemanticCandidateRanker`

## Related
- `src/placeholder_orchestrator.py` — consumer
- `src/semantic_candidate_ranker.py` — Pass 3 LLM ranking
- `src/placeholder_scorers.py` — scoring functions
- `src/role_mapper.py` — `normalise_element_text` (now includes placeholder)

---

## AI-035 / B-036 Update (2026-08-03)

### `site_hash` parameter
`find_best_element_for_current_page(..., golden_patterns=None, site_hash=None)`
gained a `site_hash` kwarg, forwarded to
`PlaceholderResolver.rank_candidates(..., site_hash=site_hash)` — enables the
same-site learned-pattern bonus (+5, AI-035 Phase 2). Optional; absent → no
learned bonus (unchanged behavior).


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `select_page_loaded_candidate(candidates: list[dict[str, str]], description: str = '') -> dict[str, str] | None` (function)

Pick a stable visible page element for generic "page loaded" assertions.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (3 items). Grouped under the public function that uses them:

### `ElementMatcher`
- `_is_excluded(element: dict[str, str], excluded_selectors: set[str]) -> bool` (function) — Check if an element should be excluded from consideration.
- `_log_resolve_pass(pass_number: int, pass_name: str, description: str, element: dict[str, str] | None) -> None` (function) — (no docstring)
- `_validate_text_match(element: dict[str, str] | None, description: str, resolver: PlaceholderResolver) -> dict[str, str] | None` (function) — Validate that the element's visible text plausibly matches the description.
