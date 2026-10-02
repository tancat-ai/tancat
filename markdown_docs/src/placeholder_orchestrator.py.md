# `src/placeholder_orchestrator.py`

## High-Level Purpose

Coordinates placeholder resolution, scraping, and page artifact generation. Transforms AI-generated test code with `{{ACTION:description}}` placeholders into complete, runnable tests by orchestrating scraping, placeholder resolution, and Page Object Model (POM) generation. Supports both flat `evidence_tracker` style and POM-mode output.

## Module Metadata

- **Lines:** 1828
- **Imports:** `re`, `logging`, `typing`, `urllib.parse`, `src.code_postprocessor`, `src.journey_models`, `src.journey_scraper`, `src.locator_builder`, `src.page_object_builder`, `src.pipeline_models`, `src.placeholder_resolver`, `src.scraper`, `src.semantic_candidate_ranker`, `src.semantic_matcher`, `src.stateful_scraper`, `src.url_inference`, `src.url_resolver`, `src.url_utils`

## Constants

- `DISPLAY_ROLES`: Frozenset of ARIA roles for ASSERT filtering (heading, paragraph, text, status, alert, listitem, cell, etc.)
- `ROLE_FALLBACK_GAP`: Maximum score gap before falling back to non-display elements (default: 3)

## Class: `PlaceholderOrchestrator`

### `__init__(starting_url=None, credential_profile=None, pom_mode=False, generator=None, rag_retriever=None)`
- `starting_url`: Base URL for session-aware scraping
- `credential_profile`: Credentials for stateful scraping (authenticated flows)
- `pom_mode`: When True, generate tests using evidence-aware POM classes instead of flat `evidence_tracker` calls
- `generator`: LLM generator for semantic candidate ranking (B-020). When None, ASSERT resolution falls back to mechanical `toBeVisible`
- `rag_retriever`: Optional `RAGRetriever` for golden-pattern scoring (Phase 3 RAG, 2026-07-21). When None, RAG is disabled — zero behaviour change.

### Properties
- `pom_mode(self) -> bool`: Whether POM-mode output is enabled
- `rag_retriever` → stored as `self._rag_retriever`; accessed via `_retrieve_golden_patterns()`

### Key Methods

#### Scraping & State Management
- `_ensure_scraped(url, scraped_data, scraped_errors=None)`: Scrape URL once and cache into scraped_data — drops near-empty SPA 404/login-wall shells (<3 elements)
- `_upgrade_stateful_pages(scraped_data) -> dict`: Replace stateless scrapes with session-backed scrapes for cart/checkout pages; ends with `_drop_dead_pages` (removes <3-element shells)
- `_drop_dead_pages(scraped_data)`: Remove near-empty shells (SPA 404 pages, login walls) that pollute resolution
- `_drop_redirect_duplicates(scraped_data, redirects)`: Remove pages whose stateless scrape redirected to another page AND whose content duplicates that target (automationexercise serves 200 + redirect-to-home for guessed routes)
- `_is_navigation_description(description) -> bool`: True for cart/basket navigation descriptions ("cart icon", "shopping cart") — excludes action verbs (add/remove) and "button" targets
- `_build_scraped_page_records(pages_to_scrape, scraped_data, scraped_errors=None, redirects=None) -> list[ScrapedPage]`: Build typed scraped-page records in journey order

#### Page Object Model (POM) Helpers
- `_build_page_object_artifacts(scraped_pages) -> list[GeneratedPageObject]`: Generate page objects from scraped pages
- `_build_pom_url_map(page_objects) -> dict[str, GeneratedPageObject]`: Map URLs to page objects
- `_build_pom_imports(page_objects) -> list[str]`: Generate import statements for POM mode
- `_build_pom_instantiation(page_objects, use_evidence_tracker=True) -> list[str]`: Generate POM instance instantiation lines
- `_get_pom_instance_name(url, page_objects) -> str | None`: Get POM instance variable name for URL
- `_get_pom_method_call(action, description, resolved_selector, pom_instance_name, fill_value="") -> str | None`: Generate POM method call (CLICK/FILL only; ASSERT/GOTO remain direct)

#### RAG Retrieval (Phase 3, 2026-07-21)
- `_retrieve_golden_patterns(action, description) -> list | None`: Queries `RAGRetriever` for golden patterns matching the placeholder. Returns None when RAG is disabled or no patterns found above confidence threshold. Called before `find_best_element_for_current_page()` — results are forwarded as `golden_patterns` kwarg.

#### Placeholder Resolution
- `_replace_placeholders_sequentially(skeleton_code, journeys, page_requirements, seed_urls, scraped_data, scraped_errors=None) -> str`: Main resolution method — resolves placeholders step-by-step while tracking active page
  - Phase 1: Resolve placeholders inside test functions with journey context
  - Phase 2: Resolve remaining placeholders using fallback context
  - Phase 3: Apply line-level replacements (supports POM mode)
  - Phase 4: Insert consolidated pytest.skip() per journey
  - Phase 5: Remove old per-placeholder skip lines
  - Phase 6: Remove raw placeholder lines

#### Helper Methods
- `_extract_fill_text(line) -> str | None`: Extract second argument from evidence_tracker.fill() call
- `_all_placeholder_uses(code) -> list`: Parse all placeholder uses from code
- `_remove_old_placeholder_skips(lines, journeys) -> list[str]`: Filter out old per-placeholder skip lines
- `_remove_raw_placeholder_lines(lines) -> list[str]`: Remove remaining raw placeholder tokens

## Key Features

### Placeholder Resolution Strategy
1. **Journey-aware resolution**: Resolves placeholders in journey step order, tracking current URL
2. **Selector tracking**: Tracks last interactive selector for ASSERT exclusion (B-014)
3. **LLM semantic context**: Records resolved steps for LLM-assisted ASSERT resolution (B-020)
4. **Fallback resolution**: Unresolved placeholders use fallback page URL
5. **Consolidated skips**: Groups unresolved placeholders into single pytest.skip() at test top

### POM Mode
- Generates tests that import and use evidence-aware Page Object Model classes
- Assertions remain as direct `evidence_tracker` calls regardless of POM mode
- CLICK/FILL actions delegate to POM methods (e.g., `home_page.click("label")`)
- GOTO/URL remain as direct `page.goto()` calls

### Stateful Scraping
- **Cart/checkout pages**: Uses `CartSeedingScraper` for session-backed scraping — now passed `credential_profile` (2026-08-03) so auth-gated sites (saucedemo) can seed the cart
- **Stateful routing (2026-08-03):** cart/checkout detection uses `url_utils.is_stateful_cart_checkout_path` (site-agnostic tokens) instead of the hardcoded `{/view_cart, /checkout}` set
- **Stateful re-scrape**: Re-scrapes pages that returned 0 elements
- **Journey execution**: Supports authenticated flows via `execute_journey()`
- **URL matching**: Matches on both domain and path to avoid mixing data from different sites

### Navigation-Intent Fallback (2026-08-03)
SPA sites render cart/basket links as icon elements with no accessible name, so text matching can't resolve "cart icon"/"shopping cart". When element matching fails on a cart/basket navigation description, the pipeline re-resolves it as a GOTO to the verified page URL — keeping the page context advancing through cart → checkout.

### Post-Login ASSERT Mapping (2026-08-03)
Page-state assertions mentioning "logged in"/"login successful" resolve to the post-auth page (inventory/products) instead of the login page itself.

### GOTO Resolution Scope (2026-08-03)
GOTO/URL placeholders resolve against ALL verified pages (not just the current page's scope) — navigation is global, so dead shells or scoped pages can't hijack it.

### ASSERT Resolution (B-014, B-016, B-020)
- **B-014**: Excludes last interactive selector from ASSERT candidates
- **B-016**: Filters by display roles (heading, paragraph, text, etc.) to avoid matching interactive elements
- **B-020**: Uses LLM semantic candidate ranking for ASSERT resolution when generator provided

## Dependencies

- `src.code_postprocessor.replace_token_in_line` — token replacement logic
- `src.journey_scraper.CartSeedingScraper, execute_journey` — cart seeding and journey execution
- `src.locator_builder.build_robust_locator` — locator construction
- `src.page_object_builder.PageObjectBuilder` — POM generation
- `src.pipeline_models.*` — data models
- `src.placeholder_resolver.PlaceholderResolver` — core placeholder resolution
- `src.scraper.PageScraper` — static scraping
- `src.semantic_candidate_ranker.SemanticCandidateRanker` — LLM-assisted ranking
- `src.semantic_matcher.SemanticMatcher` — semantic matching
- `src.stateful_scraper.StatefulPageScraper` — stateful scraping
- `src.url_inference.infer_next_page_url` — URL inference
- `src.url_resolver.UrlResolver` — URL resolution
- `src.url_utils.*` — URL utilities

## Depended On By

- `src/orchestrator.py` — core pipeline orchestration
- `src/ui_pipeline.py` — Streamlit UI pipeline execution

## Notes

- Largest module in the project (1833 lines at refresh 2026-08-23)
- Extracted from `TestOrchestrator` to separate concerns
- Supports both legacy flat mode and modern POM mode
- Handles complex stateful scraping scenarios (cart, checkout, authentication)
- B-014/B-016/B-020 improvements for ASSERT resolution quality
- **B-021 (2026-07-20):** `_is_page_state_assertion()` + URL assertion routing → `expect(page).to_have_url(...)`
- **B-022 (2026-07-20):** Cart-seeding upgrade now always prefers seeded data for `/view_cart` and `/checkout`; product URL detection from scraped data
- **B-023 (2026-07-20):** Modal dismissal integrated via `JourneyScraper._dismiss_modals()`
- **2026-08-03 (saucedemo checkout cluster):** soft-404 dead-page filter, redirect-duplicate filter, navigation-intent GOTO fallback, post-login ASSERT mapping, site-agnostic stateful routing, CartSeedingScraper credentials
- **Phase 3 RAG (2026-07-21):** `rag_retriever` kwarg + `_retrieve_golden_patterns()` → golden patterns flow into `ElementMatcher.find_best_element_for_current_page()` → `PlaceholderScorer.compute_element_score()` for +GOLDEN_PATTERN_BONUS
- Consolidated skip logic reduces noise in generated tests
---

## AI-052 Update (2026-08-23, S2 + S3 — consuming the observed trail)

`_replace_placeholders_sequentially(skeleton_code, journeys, page_requirements,
seed_urls, scraped_data, scraped_errors=None, observed_trails=None)` gained the
`observed_trails: dict[str, ObservedTrail] | None` kwarg (journey test name →
the trail `src/journey_scraper.py` captured during discovery). The resolver now
**derives each step's page from the observation instead of guessing**:

- **Strict scoping** — a step resolves only against the page the trail says it
  is on. There is **never an all-pages fallback**: when the trail evidences no
  scraped page for a step (or a token was skipped under strict scope), the
  placeholder becomes an honest `pytest.skip` ("unresolved placeholders for…")
  instead of a locator from the wrong page. Tokens in `strict_skipped_tokens`
  are additionally barred from the all-pages batch fallback — that path would
  have resurrected the exact cross-page locator this fix removes.
- **`_map_trail_to_placeholders(journey, trail_steps) -> dict[str, ObservedStep]`
  **(new helper)** — aligns skeleton placeholders to trail steps by
  `(action, description)` with a monotonic cursor (GOTO→"navigate",
  ASSERT→"scrape"). Exact index alignment can't be assumed (GOTOs that
  resolved to no URL produced no scrape step; a trailing final-page scrape is
  appended). Unmatched placeholders get no entry → "unknown" state.
- **GOTO from observed landings** — a GOTO's target URL comes from the trail's
  observed `to_url` (factual), not from keyword/href inference
  (`src/url_inference.py` is now the non-trail fallback only, and itself
  evidence-only after S4).
- **Pending-evidence anchor** — when WE emit a CLICK whose real `href` targets
  an unscraped page, the runtime browser will land there; `pending_evidence`
  marks that move so the next step resolves against the *new* page instead of
  the stale verified one.
- **Divergence-aware replay** — the trail's `selector_used` was PROVEN (clicked
  successfully during discovery, `error is None`). When the resolver picks a
  different element for a CLICK: ours navigates via a real `href` → keep ours
  (the href is evidence); ours has no `href` (JS-driven link, navigation
  behaviour unknowable) → **replay the proven selector** so the generated test
  re-enacts the observed journey; ours found nothing scoped → fall back to the
  proven selector instead of skipping. A navigation-intent click that provably
  stayed put is emitted as a navigation to a verified page rather than a dead
  click (proven-static navigation intent).
- **Divergence latch** — once our emitted path departs from the observed one
  (href navigation / proven-static override), `diverged` latches True: from
  then on the trail describes a different journey than the generated test, and
  only our own verified anchor (`last_verified_url`) is trustworthy.
- **URL canonicalisation** — trail URLs come straight from `page.url` while
  `scraped_data` keys are normalised; every membership check goes through a
  `normalize_url`-based map so `https://x/` vs `https://x` never mismatches.
- **Debug** — with `PIPELINE_DEBUG=1`, each journey logs its observed trail on
  stderr (`[resolve] test_N observed trail: [url1 -> url2 …]`).

Cross-links: `src/journey_scraper.py` (trail capture, S1) ·
`src/journey_models.py` (`ObservedStep` / `ObservedTrail`) ·
`src/url_inference.py` (evidence-only fallback, S4) ·
`src/element_matcher.py` (S5 role gate, second line of defence).

## AI-035 / B-036 Update (2026-08-03)

### Site-scoped learned-pattern bonus
`_resolve_placeholder()` now computes the current site's hash from
`current_url` (`src.rag_learn.site_hash(domain_from_url(...))`) and threads it
as `site_hash` into `ElementMatcher.find_best_element_for_current_page(...)` →
`PlaceholderResolver.rank_candidates(...)` → `PlaceholderScorer.compute_element_score(...)`.
Learned patterns from the same site earn +5; cross-site earned 0. Golden
patterns are unaffected (+20 anywhere).


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `polarity_assertion_type(description: str) -> str | None` (function)

Return ``"toBeHidden"`` for negative-state ASSERT descriptions, else None.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `attribute_assertion_type` (function): `attribute_assertion_type(description: str) -> str | None` - Return structured assertion type for attribute-condition ASSERT descriptions. "href does not contain TBD" / "every image has a non-empty alt" / "meta description" must read the element's attribute rather than assert c...
- `PlaceholderOrchestrator.test_resolution_counts` (method of `PlaceholderOrchestrator`): `PlaceholderOrchestrator.test_resolution_counts() -> list[TestResolutionCounts]` - Return per-test resolved/unresolved placeholder counts (B-097).
- `PlaceholderOrchestrator.test_verification_verdicts` (method of `PlaceholderOrchestrator`): `PlaceholderOrchestrator.test_verification_verdicts() -> list[TestVerificationVerdict]` - Return what each generated test provably checked (B-100).
- `POLARITY_TERMS` (constant): `POLARITY_TERMS = ('closed', 'gone', 'disappeared', 'disappears', 'removed'...`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (34 items). Grouped under the public function that calls them.

### Internal utilities

- `_is_page_level_assert(action: str, description: str) -> bool` (function): True when the emitter checks this ASSERT without element resolution. B-069/B-086/B-088 page-level families (count scans, document/<head> reads, section containment) emit their own tracker call at the single emit choke...
- `_drop_redirect_duplicates(scraped_data: dict[str, list[dict[str, Any]]], redirects: dict[str, str]) -> dict[str, list[dict[str, Any]]]` (method of `PlaceholderOrchestrator`): Remove pages whose scrape redirected to, and duplicated, another page. Some sites answer unknown routes with HTTP 200 and a redirect to the home page (automationexercise /inventory.html, /basket). The bogus key then h...
- `_is_error_page(elements: list[dict[str, Any]]) -> bool` (method of `PlaceholderOrchestrator`): True when scraped elements are an HTTP error page (404/500 body). The stateless/stateful scrapers fetch unknown routes before the resolver sees them (concept-driven candidate URLs). A stdlib 404 page scrapes to ~5 ele...
- `_drop_dead_pages(scraped_data: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]` (method of `PlaceholderOrchestrator`): Remove pages that scraped to a near-empty shell. SPA-hosted sites (saucedemo on GitHub Pages) answer every non-existent path with a 2-element 404/app shell; auth-gated redirects render a login stub. Such dead pages po...
- `_ensure_scraped(url: str | None, scraped_data: dict[str, list[dict[str, str]]], scraped_errors: dict[str, str] | None = None) -> None` (method of `PlaceholderOrchestrator`): Scrape the URL once and cache into scraped_data.
- `_upgrade_stateful_pages(scraped_data: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]` (method of `PlaceholderOrchestrator`): Replace stateless scrapes with session-backed scrapes where needed.
- `_build_scraped_page_records(pages_to_scrape: list[str], scraped_data: dict[str, list[dict[str, str]]], scraped_errors: dict[str, str] | None = None, redirects: dict[str, str] | None = None) -> list[ScrapedPage]` (method of `PlaceholderOrchestrator`): Return typed scraped-page records in journey order.
- `_build_page_object_artifacts(scraped_pages: list[ScrapedPage]) -> list[GeneratedPageObject]` (method of `PlaceholderOrchestrator`): Build page object artifacts; calls `build_page_object_artifacts`; returns list[GeneratedPageObject].
- `_replace_placeholders_sequentially(*, skeleton_code: str, journeys: list[TestJourney], page_requirements: list[PageRequirement], seed_urls: list[str], scraped_data: dict[str, list[dict[str, str]]], scraped_errors: dict[str, str] | None = None, observed_trails: dict[str, ObservedTrail] | None = None) -> str` (method of `PlaceholderOrchestrator`): Resolve placeholders step by step while tracking the active page for each test.
- `_batch_resolve_deferred_asserts(deferred_asserts: list[dict[str, Any]], scraped_data: dict[str, list[dict[str, str]]], scraped_errors: dict[str, str] | None, fallback_url: str | None, line_resolutions: dict[int, list[tuple[str, str, str, str, str, str | None, str | None]]], journey_unresolved: dict[str, list[str]], journey_unresolved_keys: dict[str, set[tuple[int, str]]], journey_name: str, strict_scope: bool = False) -> None` (method of `PlaceholderOrchestrator`): Batch-resolve deferred ASSERT placeholders grouped by page URL. ASSERT placeholders are independent - they don't update sequential state (last_selector, current_url, resolved_steps). By deferring them and batching Pas...
- `_resolve_placeholder_for_page(action: str, description: str, current_url: str | None, scraped_data: dict[str, list[dict[str, str]]], scraped_errors: dict[str, str] | None = None, previous_selector: str | None = None, previous_description: str | None = None, resolved_steps: list[str] | None = None, strict_scope: bool = False, matched_out: dict[str, Any] | None = None) -> tuple[str, str | None, str | None]` (method of `PlaceholderOrchestrator`): Resolve one placeholder using the active page first, then fall back to known pages. Args: previous_selector: The selector resolved by the previous interactive step. previous_description: The description from the previ...
- `_is_navigation_description(description: str) -> bool` (method of `PlaceholderOrchestrator`): True when a description means navigating to a page, not clicking an element. SPA sites render cart/basket links as icon elements with no accessible name, so text matching can't resolve them. Descriptions like "cart ic...
- `_retrieve_golden_patterns(action: str, description: str) -> list | None` (method of `PlaceholderOrchestrator`): Retrieve golden patterns from the RAG store for this placeholder. Returns None when RAG is disabled or no patterns match.
- `_write_rag_diagnostic(action: str, description: str, patterns: list[Any]) -> None` (method of `PlaceholderOrchestrator`): Optionally append retrieval details for an AI-059 lab run. Diagnostics are opt-in and file-backed so production runs retain their existing behavior and cost. The lab runner sets the path per leg.
- `_write_rag_usage_diagnostic(action: str, description: str, usage: list[Any], decisive: bool | None = None, counterfactual_selector: str | None = None) -> None` (method of `PlaceholderOrchestrator`): Optionally append per-pattern usage records for an AI-059 lab run. usage is the list returned by RAGRetriever.pattern_usage - one record per retrieved pattern answering whether it was eligible for this run...
- `_is_page_state_assertion(description: str) -> bool` (method of `PlaceholderOrchestrator`): Check if an ASSERT description refers to a page state rather than an element. B-021: Returns True for descriptions like "home page visible", "dress products page", "cart page loaded" - these should be resolved as URL...
- `_build_scoped_pages(current_url: str | None, scraped_data: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]` (method of `PlaceholderOrchestrator`): Return a page mapping scoped to the current journey URL when available. AI-052 contract: returns {} when current_url is not a verified (scraped) page - callers decide the fallback. Trail-driven callers (stri...
- `_emitted_navigation_target(matched_element: dict[str, str], current_url: str | None) -> str | None` (method of `PlaceholderOrchestrator`): Return the real-href navigation target of an emitted CLICK (AI-052). Evidence only: the element's own href. Returns None for non-navigation elements (plain buttons, fragments, javascript:), and for hrefs that...
- `_trail_step_scope_url(obs: ObservedStep | None, canon: Any, last_verified_url: str | None) -> str | None` (method of `PlaceholderOrchestrator`): Return the page a placeholder should resolve against (AI-052 three states). canon maps a raw URL to its actual scraped_data key (or None) - trail URLs come from page.url and may differ cosmetically (trailing slash...
- `_map_trail_to_placeholders(journey: TestJourney, trail_steps: list[ObservedStep]) -> dict[str, ObservedStep]` (method of `PlaceholderOrchestrator`): Map skeleton placeholder tokens to their observed trail steps (AI-052 S3). The trail was captured from the SAME journey: _scrape_journeys_statefully flattens placeholders in the same order (GOTO->"navigate", CLICK/...
- `_apply_section_scoping(action: str, description: str, pages_data: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]` (method of `PlaceholderOrchestrator`): Filter each page's elements to the section named in the description. Falls back to the full element list when no section hint is found. This is a no-op for multi-page sites (each URL has one section). The benefit is f...
- `_descriptions_reference_same_element(desc_a: str, desc_b: str) -> bool` (method of `PlaceholderOrchestrator`): Return True when two descriptions likely reference the same element.
- `_build_excluded_selectors(action: str, description: str, previous_selector: str | None, previous_description: str | None, pages_data: dict[str, list[dict[str, str]]]) -> set[str]` (method of `PlaceholderOrchestrator`): Build a set of selectors to exclude for this resolution (B-014). For ASSERT: excludes the previous step's selector unless descriptions match. For CLICK/FILL: returns empty set.
- `_verify_page_context(description: str, matched_element: dict[str, str], current_url: str | None, scraped_data: dict[str, list[dict[str, str]]]) -> bool` (method of `PlaceholderOrchestrator`): Verify the resolved locator exists on the current page (B3: page-context validation).
- `_build_candidate_urls(seed_urls: list[str], page_requirements: list[PageRequirement], journeys: list[TestJourney], user_story: str, conditions: str) -> list[str]` (method of `PlaceholderOrchestrator`): Return a tightly-scoped list of URLs needed for the current journeys.
- `_select_initial_page_url(journey: TestJourney, page_requirements: list[PageRequirement], seed_urls: list[str], scraped_data: dict[str, list[dict[str, str]]], skeleton_lines: list[str] | None = None) -> str | None` (method of `PlaceholderOrchestrator`): Choose the starting page for one test journey.
- `_extract_journey_start_url(journey: TestJourney, skeleton_lines: list[str]) -> str | None` (method of `PlaceholderOrchestrator`): Return a per-journey starting URL marker inserted during fragment combine.
- `_page_requirements_to_pages(page_requirements: list[PageRequirement], scraped_data: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]] | None` (method of `PlaceholderOrchestrator`): Return scraped data filtered to pages declared in PAGES_NEEDED keywords.
- `_select_fallback_page_url(page_requirements: list[PageRequirement], seed_urls: list[str], scraped_data: dict[str, list[dict[str, str]]]) -> str | None` (method of `PlaceholderOrchestrator`): Return the default page URL to use when no journey-specific page is known.
- `_extract_fill_text(line: str) -> str | None` (method of `PlaceholderOrchestrator`): Extract the second argument from an evidence_tracker.fill() call.
- `_all_placeholder_uses(code: str) -> list` (method of `PlaceholderOrchestrator`): Parse all placeholder uses from code (delegate to SkeletonParser).
- `_find_journey_for_line(line_number: int, journeys: list[TestJourney]) -> str | None` (method of `PlaceholderOrchestrator`): Return the test_name of the journey that contains the given line number.
- `_get_duplicate_selectors(scraped_data: dict[str, list[dict[str, str]]]) -> set[str]` (method of `PlaceholderOrchestrator`): Return selectors that appear more than once across scraped pages.
- `_get_pom_method_call(action: str, description: str, resolved_selector: str, pom_instance_name: str, fill_value: str = '') -> str | None` (method of `PlaceholderOrchestrator`): Get pom method call; calls `get_pom_method_call`; returns str | None.
