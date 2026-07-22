# `src/element_matcher.py`

## High-Level Purpose

Multi-pass element matching engine for placeholder resolution. Extracted from `placeholder_orchestrator.py`. Implements a 4-pass resolution pipeline (Pass 0–3) for matching placeholder descriptions to scraped DOM elements, plus LLM-based semantic ASSERT resolution (B-020).

## Module Metadata

- **Lines:** ~700
- **Imports:** `re`, `logging`, `typing`, `src.intent_matcher`, `src.locator_builder`, `src.placeholder_resolver`, `src.role_mapper`, `src.semantic_candidate_ranker`, `src.semantic_matcher`
- **Extracted from:** `placeholder_orchestrator.py`

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `TEXT_BEARING_ROLES` | `{heading, paragraph, text, status, alert, region, article, listitem, cell, columnheader, rowheader}` | ARIA roles for ASSERT text matching (B-016) |
| `TEXT_BEARING_TAGS` | `{h1-h6, p, span, label, li, td, th}` | HTML tags for ASSERT text matching |
| `MIN_SCORE_FOR_TEXT_FALLBACK` | `5` | Minimum score threshold for text fallback when no LLM selection available (B-020) |

## Class: `ElementMatcher`

### `__init__(self, resolver: PlaceholderResolver, generator: AsyncGeneratorLike | None = None)`
- `resolver`: PlaceholderResolver instance for text matching and ranking
- `generator`: B-020 LLM generator for semantic candidate ranking (nullable)

### Resolution Pipeline

**Pass 0 — Exact text match:**
- `pass0_exact_text_match(action, description, pages_data) -> dict | None`
- For ASSERT descriptions wrapped in quotes (`ASSERT:"exact text here"`) — strips quotes and does literal string equality against element text
- Bypasses all scoring and LLM calls for the simple "verify text is X" case

**Pass 1 — Text match:**
- `pass1_text_match(action, description, pages_data) -> dict | None`
- Fast text match for CLICK/FILL — returns first element whose normalised text is contained in the description
- ASSERT tokens for page state fall through to scoring path
- Minimum element text length of 3 characters
- R-001: Key phrase extraction for verbose descriptions (quoted phrases, context boundary words)

**Pass 1b — ASSERT text match:**
- `pass1_assert_text_match(action, description, pages_data) -> dict | None`
- ASSERT-specific text matching against elements with `TEXT_BEARING_ROLES` or `TEXT_BEARING_TAGS`
- B-016: Filters to display/text roles only

**Pass 2 — Structural match:**
- `pass2_structural_match(action, description, pages_data, excluded_selectors=None) -> dict | None`
- Structural attribute match (id, data-test, aria-label, name, class)
- Falls back to text-bearing elements for ASSERT when no structural match found

**Pass 3 — Scoring + LLM:**
- `async find_best_element_for_current_page(action, description, pages_data, *, excluded_selectors=None, current_url="", resolved_context=None, golden_patterns=None) -> tuple[dict | None, float, str]`
- **Main entry point** — orchestrates all passes + scoring
- Returns `(element, score, source)` where source identifies which pass resolved the match
- **RAG (2026-07-21):** Accepts optional `golden_patterns` from `RAGRetriever` — forwarded to `PlaceholderScorer.compute_element_score()` for bonus
- `_resolve_assert_semantically(action, description, candidates, current_url, resolved_context)` — LLM-based semantic ASSERT resolution (B-020)

## Module-Level Functions

### `_is_excluded(element, excluded_selectors) -> bool`
Check if element's selector is in the excluded set.

### `_validate_text_match(element, description) -> bool`
Validate that text match element has at least some text content.

### `_log_resolve_pass(element, action, description, pass_name, score=0)`
Standardised logging for resolution results.

### `select_page_loaded_candidate(candidates) -> dict | None`
Select the best candidate from page-loaded detection results.

## Key Design Decisions

- **4-pass pipeline:** Early passes (0-2) are fast/cheap; Pass 3 (scoring + LLM) is the expensive fallback
- **Pass ordering:** exact text → fast text → structural → scoring/LLM
- **B-020:** LLM semantic ranking for ASSERT resolution when generator is provided
- **B-016:** ASSERT text matching filters to display roles (heading, paragraph, text, etc.)
- **RAG integration:** `golden_patterns` kwarg flows through `find_best_element_for_current_page()` → `PlaceholderScorer.compute_element_score()` — zero behaviour change when `None`

## Dependencies

- `src.placeholder_resolver.PlaceholderResolver` — text matching and ranking
- `src.semantic_candidate_ranker.SemanticCandidateRanker` — LLM-based ranking
- `src.semantic_matcher.SemanticMatcher` — semantic text matching
- `src.intent_matcher.SemanticFillStrategy` — fill strategy detection
- `src.locator_builder.build_robust_locator` — locator construction
- `src.role_mapper` — role classification utilities

## Depended On By

- `src/placeholder_orchestrator.py` — calls `find_best_element_for_current_page()` with golden_patterns
- `tests/test_element_matcher.py` — unit tests
