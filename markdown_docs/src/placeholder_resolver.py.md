# `src/placeholder_resolver.py`

## High-Level Purpose
Core placeholder resolution engine that matches `{{TOKEN:description}}` tokens against scraped DOM candidates using semantic matching, confidence scoring, and page-context validation.

## Module Metadata
- **Lines:** ~530
- **Imports:** `re`, `logging`, `dataclasses`, `typing`, `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`
- **RAG update:** 2026-07-21 — `golden_patterns` optional kwarg on `rank_candidates()`

## Classes

### `PlaceholderContext` (dataclass)
Holds token, description, and resolved selector for a single placeholder.

### `PlaceholderResolver`
Main resolution class.
| Method | Description |
|--------|-------------|
| `resolve(code: str, pages: list[PageData]) -> list[PlaceholderContext]` | Finds all placeholder tokens and resolves each against page candidates |
| `resolve_single(token: str, candidates: list[Element]) -> ScoreResult` | Resolves one token against candidate elements |
| `resolve_url(description, pages_data, known_urls=None)` | Resolve navigation placeholders to the best matching scraped URL (direct URL → known_urls substring → discovered hrefs → semantic word scoring) |
| `_find_candidates(token: str, pages: list[PageData]) -> list[Element]` | Scrapes matching elements across pages |
| `_apply_page_context(token: str, candidates: list[Element]) -> list[Element]` | Filters candidates by page-context rules |
| `rank_candidates(candidates, description, *, golden_patterns=None)` | Scores and ranks candidates; `golden_patterns` (Phase 3 RAG) adds bonus for golden pattern matches |

## Key Design Decisions
- Token-only placeholders in skeleton phase (no real selectors)
- Page-context validation prevents cross-page mismatches
- Confidence threshold gate before accepting a match
- `resolve_url` scoring gives +4 bonuses for product/cart/checkout path words; the product bonus set includes `inventory` (2026-08-03) so saucedemo's `/inventory.html` wins "products page loaded" style resolutions
- **RAG golden_patterns (2026-07-21):** Optional kwarg passed through to `PlaceholderScorer.compute_element_score()` — advisory bonus, zero behaviour change when None

## Dependencies
- `src.semantic_matcher`, `src.placeholder_scorers`, `src.page_context_tracker`

---

## AI-035 / B-036 Update (2026-08-03)

### `site_hash` parameter
`rank_candidates(action, description, page_elements, golden_patterns=None, site_hash=None)`
gained a `site_hash` kwarg, forwarded to
`PlaceholderScorer.compute_element_score(..., site_hash=site_hash)` — enables
the same-site learned-pattern bonus (+5, AI-035 Phase 2). Callers that don't
pass it get identical behavior (bonus only applies when a site hash is present).

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### Internal utilities
- `_css_escape_id(value: str) -> str` (function) — Escape a raw ID value for safe use in a CSS #id selector.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `PlaceholderResolver.__init__` (method of `PlaceholderResolver`): `PlaceholderResolver.__init__(match_threshold: int = 1, min_confidence: float | None = None) -> None`
- `PlaceholderResolver.text_matches_description` (method of `PlaceholderResolver`): `PlaceholderResolver.text_matches_description(element_text: str, action_description: str) -> bool` - Check if element's visible text plausibly matches the action description. Strategy (fast-to-slow): 1. Negation gate (B-016) - reject absence-vs-presence contradictions. 2. Direct containment - substring match after no...


### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

### `PlaceholderResolver.__init__(match_threshold: int = 1, min_confidence: float | None = None) -> None` - method of `PlaceholderResolver`

- `_default_min_confidence() -> float` (function): Return the minimum confidence threshold from environment or default.

### `PlaceholderResolver.rank_candidates(action: str, description: str, page_elements: list[dict[str, Any]], golden_patterns: list | None = None, site_hash: str | None = None) -> list[tuple[int, dict[str, Any]]]` - method of `PlaceholderResolver`

- `_build_element_haystack(element: dict[str, Any]) -> str` (method of `PlaceholderResolver`): Return a single string containing all searchable metadata for an element. All delimiters (hyphens, underscores) are normalized to spaces to ensure that 'login button' matches 'login-button'.
- `_is_assertion_candidate(element: dict[str, Any]) -> bool` (method of `PlaceholderResolver`): Return True when the scraped element is plausible for visibility assertions.

### `PlaceholderResolver.text_matches_description(element_text: str, action_description: str) -> bool` - method of `PlaceholderResolver`

- `_is_negated(element_text: str, action_description: str) -> bool` (method of `PlaceholderResolver`): Return True when element text signals absence but description signals presence. E.g. element says "Your cart is empty!" but description says "cart content with items". This is a domain-agnostic heuristic - negation vs...

### `PlaceholderResolver.resolve_url(description: str, pages_data: dict[str, list[dict[str, Any]]], known_urls: list[str] | None = None) -> str | None` - method of `PlaceholderResolver`

- `_discover_urls_from_elements(pages_data: dict[str, list[dict[str, Any]]]) -> set[str]` (method of `PlaceholderResolver`): Extract navigable URLs from anchor hrefs in already-scraped elements. Links like <a href="./cart.html"> on inventory.html are captured by the scraper as element href fields but never surfaced as known URLs. Th...
