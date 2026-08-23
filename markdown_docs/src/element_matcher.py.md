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
