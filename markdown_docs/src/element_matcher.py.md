# `src/element_matcher.py` — Multi-Pass Element Matching Engine

## Purpose
4-pass resolution pipeline (Pass 0–3) for matching placeholder descriptions to scraped DOM elements. Extracted from `placeholder_orchestrator.py`. Includes LLM-based semantic ASSERT resolution (B-020).

## Class: `ElementMatcher`
- `find_best_element_for_current_page(action, description, elements, ...) -> str | None` — single placeholder resolution
- `find_best_elements_batch(requests: list[dict]) -> list[dict]` — batched resolution (Pass 0-2 per request, Pass 3 in one LLM call)

## Resolution Passes
- **Pass 0**: Exact text match (accessible_name, aria_label, text)
- **Pass 1**: Action-verb-aware substring match (B-012)
- **Pass 2**: Structural match (ID, data-test, name attributes + camelCase splitting)
- **Pass 3**: LLM semantic ranking via `SemanticCandidateRanker`

## Related
- `src/placeholder_orchestrator.py` — consumer
- `src/semantic_candidate_ranker.py` — Pass 3 LLM ranking
- `src/placeholder_scorers.py` — scoring functions
