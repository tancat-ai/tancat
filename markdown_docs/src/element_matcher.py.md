# `src/element_matcher.py` — Multi-Pass Element Matching Engine

## Purpose
4-pass resolution pipeline (Pass 0–3) for matching placeholder descriptions to scraped DOM elements. Extracted from `placeholder_orchestrator.py`. Includes LLM-based semantic ASSERT resolution (B-020).

## Class: `ElementMatcher`
- `find_best_element_for_current_page(action, description, elements, ...) -> str | None` — single placeholder resolution
- `find_best_elements_batch(requests: list[dict]) -> list[dict]` — batched resolution (Pass 0-2 per request, Pass 3 in one LLM call)
- `role_contradicts_click(element) -> bool` — *(staticmethod)* **AI-052 S5:** True when the element's effective ARIA role contradicts CLICK intent — heading/status/banner-class regions (`_CLICK_CONTRADICTORY_ROLES`), text-entry roles (`_CLICK_FILLABLE_ARIA_ROLES`: textbox/searchbox/combobox/…), or structurally fillable inputs (`_is_fillable`) — so date/number/text fields can't win a CLICK on text overlap alone. `computed_role` (authoritative, from the accessibility enricher) wins over `role`; generic `div`/`span` containers deliberately stay eligible (B-025 clickable containers depend on them).

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

## AI-052 Update (2026-08-23, S5 — ARIA role gate)

Second, independent line of defence for wrong-role matches: the fast passes
(0/D/1/2) used to return their first match outright, so a heading or text
field sharing words with a CLICK description could win **before** the
role-aware Pass 3 scoring ran. Now:

- In both `find_best_element_for_current_page` and `find_best_elements_batch`,
  each fast-pass CLICK candidate goes through a local
  `_defer_if_role_contradicted(candidate, pass_name)` gate:
  role-contradicted matches are **deferred, not dropped** (penalty-first) —
  appended to a `role_deferred` list so the deeper role-aware passes can
  compete.
- If every later pass comes up empty, the first deferred candidate is
  returned as a **last resort** — the gate is never a hard filter, so a page
  whose only matching element has an odd role still resolves.
- FILL and ASSERT paths are untouched (the gate is CLICK-scoped via the
  `action != "CLICK"` early-out), and B-014-excluded candidates can't
  re-enter through deferral (exclusion is checked before the gate).

## How It Works (Internals)

Private `_`-helpers — the module's real logic. Grouped under the public function that uses them:

### `find_best_element_for_current_page` / `find_best_elements_batch` (S5 role gate)
- `_defer_if_role_contradicted(candidate, pass_name) -> bool` (local function, defined inside each of the two resolvers) — True → caller may return the candidate; False → role-contradicted CLICK candidate deferred to `role_deferred` (last-resort list, consulted only if all passes fail).

### `ElementMatcher`
- `flush_pass3_batch(...)` — public: drains queued Pass 3 work (the batch path serves many placeholders with one LLM call)
- `_queue_pass3(request, pages_data)` — queues a Pass 3 resolution for the batch flush
- `_resolve_assert_semantically(...)` — LLM-based semantic ASSERT resolution (B-020), the Pass 3 path for ASSERT placeholders
- `_is_excluded(element: dict[str, str], excluded_selectors: set[str]) -> bool` — check if an element should be excluded from consideration (B-014 step-context exclusion)
- `_log_resolve_pass(pass_number: int, pass_name: str, description: str, element: dict[str, str] | None) -> None` — debug-log which pass won a resolution
- `_validate_text_match(element: dict[str, str] | None, description: str, resolver: PlaceholderResolver) -> dict[str, str] | None` — validate that the element's visible text plausibly matches the description

### Internal utilities (module level)
- `_named_role_in_description(description, role) -> bool` — detects an explicit role name ("heading", "button", …) in a description, used to bias/penalise role mismatches
- module constants `_CLICK_CONTRADICTORY_ROLES` / `_CLICK_FILLABLE_ARIA_ROLES` — the S5 role sets consulted by `role_contradicts_click`

## Metadata
- **Lines:** 1362 (at refresh, 2026-08-23)

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `ElementMatcher.__init__` (method of `ElementMatcher`): `ElementMatcher.__init__(resolver: PlaceholderResolver, generator: AsyncGeneratorLike | None = None, *, resolution_timeout: float = DEFAULT_RESOLUTION_TIMEOUT, enable_thinking: bool | None = None) -> None` - Initialize the element matcher. Args: resolver: PlaceholderResolver instance for text matching and ranking. generator: B-020 LLM generator for semantic candidate ranking. resolution_timeout: Hard limit (seconds) for e...
- `ElementMatcher.pass0_exact_text_match` (method of `ElementMatcher`): `ElementMatcher.pass0_exact_text_match(action: str, description: str, pages_data: dict[str, list[dict[str, str]]]) -> dict[str, str] | None` - Pass 0 - exact text match for ASSERT descriptions wrapped in quotes. B-020: When the skeleton emits ASSERT:"exact text here", strip the quotes and do literal string equality against element text. This bypasses all sco...
- `ElementMatcher.pass_dialog_action` (method of `ElementMatcher`): `ElementMatcher.pass_dialog_action(action: str, description: str, pages_data: dict[str, list[dict[str, str]]]) -> dict[str, str] | None` - Pass D - dialog-action scoping for CLICK placeholders. When the description implies a dialog/dismiss/confirm action ("OK", "close popup", "dismiss", "Continue Shopping"), resolve it against the modal/dialog's OWN inte...
- `ElementMatcher.pass1_text_match` (method of `ElementMatcher`): `ElementMatcher.pass1_text_match(action: str, description: str, pages_data: dict[str, list[dict[str, str]]]) -> dict[str, str] | None` - Pass 1 - fast text match before scoring. Returns the first element whose normalised text is contained in the normalised description. Only fires for CLICK and FILL - ASSERT tokens for page state will not match element...
- `ElementMatcher.pass1_assert_text_match` (method of `ElementMatcher`): `ElementMatcher.pass1_assert_text_match(action: str, description: str, pages_data: dict[str, list[dict[str, str]]]) -> dict[str, str] | None` - Pass 1 (ASSERT) - match text-bearing elements whose label appears in the description. Requires the element text to contain at least 2 of the description's content words to avoid false positives like "Summary" matching...
- `ElementMatcher.pass2_structural_match` (method of `ElementMatcher`): `ElementMatcher.pass2_structural_match(action: str, description: str, pages_data: dict[str, list[dict[str, str]]]) -> dict[str, str] | None` - Pass 2 - match stable attributes (id, data-test, aria) to description keywords.
- `TEXT_BEARING_ROLES` (constant): `TEXT_BEARING_ROLES = {'heading', 'paragraph', 'text', 'status', 'alert', 'regi...`
- `TEXT_BEARING_TAGS` (constant): `TEXT_BEARING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'label'...`
- `MIN_SCORE_FOR_TEXT_FALLBACK` (constant): `MIN_SCORE_FOR_TEXT_FALLBACK = 5`
- `DIALOG_INTENT_TERMS` (constant): `DIALOG_INTENT_TERMS = ('ok', 'okay', 'close', 'dismiss', 'confirm', 'cancel', '...`
- `DIALOG_SCOPED_ROLES` (constant): `DIALOG_SCOPED_ROLES = frozenset({'button', 'link', 'submit', 'a', 'menuitem', '...`


### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

### `ElementMatcher.pass1_text_match(action: str, description: str, pages_data: dict[str, list[dict[str, str]]]) -> dict[str, str] | None` - method of `ElementMatcher`

- `_pick_best_text_match(action: str, description: str, candidates: list[dict[str, str]], pages_data: dict[str, list[dict[str, str]]]) -> dict[str, str]` (method of `ElementMatcher`): B-096: tie-break equal-rule Pass 1 matches with the deterministic scorer. Several elements can match the same text rule on one page (an account holder and an additional driver share "Years Licensed"; a vehicle make an...

### `ElementMatcher.find_best_element_for_current_page(action: str, description: str, current_url: str | None, pages_data: dict[str, list[dict[str, str]]], excluded_selectors: set[str] | None = None, resolved_steps: list[str] | None = None, golden_patterns: list | None = None, site_hash: str | None = None) -> dict[str, str] | None` - method of `ElementMatcher`

- `_find_best_element_for_current_page(action: str, description: str, current_url: str | None, pages_data: dict[str, list[dict[str, str]]], excluded_selectors: set[str] | None = None, resolved_steps: list[str] | None = None, golden_patterns: list | None = None, site_hash: str | None = None) -> dict[str, str] | None` (method of `ElementMatcher`): Return the best element match across the supplied page mapping. IMPORTANT: Collects candidates from ALL pages first, then selects the global best match. This prevents returning a low-quality match from an early page w...
