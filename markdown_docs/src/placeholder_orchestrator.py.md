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
- `_ensure_scraped(url, scraped_data, scraped_errors=None)`: Scrape URL once and cache into scraped_data
- `_upgrade_stateful_pages(scraped_data) -> dict`: Replace stateless scrapes with session-backed scrapes for cart/checkout pages
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
- **Cart/checkout pages**: Uses `CartSeedingScraper` for session-backed scraping
- **Stateful re-scrape**: Re-scrapes pages that returned 0 elements
- **Journey execution**: Supports authenticated flows via `execute_journey()`
- **URL matching**: Matches on both domain and path to avoid mixing data from different sites

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

- Largest module in the project (1828 lines)
- Extracted from `TestOrchestrator` to separate concerns
- Supports both legacy flat mode and modern POM mode
- Handles complex stateful scraping scenarios (cart, checkout, authentication)
- B-014/B-016/B-020 improvements for ASSERT resolution quality
- **B-021 (2026-07-20):** `_is_page_state_assertion()` + URL assertion routing → `expect(page).to_have_url(...)`
- **B-022 (2026-07-20):** Cart-seeding upgrade now always prefers seeded data for `/view_cart` and `/checkout`; product URL detection from scraped data
- **B-023 (2026-07-20):** Modal dismissal integrated via `JourneyScraper._dismiss_modals()`
- **Phase 3 RAG (2026-07-21):** `rag_retriever` kwarg + `_retrieve_golden_patterns()` → golden patterns flow into `ElementMatcher.find_best_element_for_current_page()` → `PlaceholderScorer.compute_element_score()` for +GOLDEN_PATTERN_BONUS
- Consolidated skip logic reduces noise in generated tests