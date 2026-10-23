# Session - delete every guessed-URL path (2026-10-23, t-0877)

**The owner's rule, his words:** *"if its not something a real user would have then its not
accurate testing behaviour."*

**Answer: every path that invented a web address is deleted, not disabled.** A navigation may
now reach only a URL the human gave us, a page the pipeline really scraped, the real `href` of a
link on the current page, or that link's browser-computed accessible name. Anything else is an
honest unresolved. 4002 tests + 2 new ones pass, smoke 39/39, ruff + mypy clean, static eval
unchanged.

## 1. What was deleted, and where

| # | What | Where | Why it was a guess |
|---|---|---|---|
| 1 | `build_common_path_candidates()` and its fixed route table (`/cart.html`, `/cart`, `/view_cart`, `/basket`, `/checkout-step-one.html`, `/checkout`, `/products`, `/inventory.html`) | `src/url_utils.py` (was 94-124) | turned the story's *concepts* into addresses on the seed domain; the pages were never named by a human and never reached by the browser |
| 2 | both scrape-candidate call sites | `src/orchestrator.py` (was 1195), `src/placeholder_orchestrator.py` (was 2147) | the invented addresses were put on the *scrape* list, so a guessed page that happened to load became "known" - which is how `/basket` and `/inventory.html` won arrival assertions in the re-measure (t-0871/0872/0873) |
| 3 | `heuristic_url_from_description()` | `src/url_utils.py` (was 127-145) | mapped words to `/products`, `/view_cart`, `/checkout`; it had already lost its last caller, but it was the same class of guess |
| 4 | `CartSeedingScraper._derive_products_url()` and the `/products` fallback | `src/cart_seeding_scraper.py`, `src/placeholder_orchestrator.py` `_upgrade_stateful_pages` | appended `/products` to the home URL to aim the cart seeder at a page nobody had seen |
| 5 | `PlaceholderResolver.resolve_url`'s "return whichever page is first" fallback **and the `strict` flag** | `src/placeholder_resolver.py` | an unmatched description was answered with an arbitrary scraped page - a guess dressed as a resolution. With the flag gone there is no non-strict mode left to reach from anywhere, including `_select_initial_page_url` (the call site the owner named) |

## 2. What was kept, and why

- **`UrlResolver`'s keyword → URL matching** (path segments, aliases, substrings): it maps a
  keyword onto a page that **was really scraped**. Reading something that exists is discovery.
- **`resolve_url`'s direct-URL validation, `known_urls` matching, and scoring against scraped
  page text**: same reason.
- **`infer_next_page_url`** (`src/url_inference.py`): already evidence-only - the clicked
  element's own `href`, nothing else.
- **`extract_route_concepts`**: a concept is a word ("cart"), never an address. Journey
  discovery still uses the word to look for routes; it can no longer create one.
- **`extract_seed_domain` / `filter_urls_to_allowed_domain`**: guards on real URLs.
- **`UrlResolver`'s `login` → seed-URL fallback**: it maps a keyword to the URL the **human**
  gave us, which source 1 of the rule allows. Kept, and flagged here so the decision is visible.
- **`is_stateful_cart_checkout_path`**: recognises real paths; creates none.

## 3. Tests changed (and what still guarantees each area)

| Test | Change | Why | What still guarantees it |
|---|---|---|---|
| `tests/test_url_utils.py::test_build_common_path_candidates_concept_driven_and_same_domain`, `::test_build_common_path_candidates_empty_inputs` | replaced by `::test_no_fixed_route_table_survives_in_url_utils` and `::test_concept_extraction_remains_but_creates_no_urls` | they pinned the deleted helpers | the new tests assert the helpers do not exist (so a re-introduction fails) and that concepts stay words |
| `tests/test_journey_scraper.py::test_init_basic` | asserts `products_url is None` instead of a derived `/products` | the derivation is gone | same test |
| `tests/test_journey_scraper.py::test_derive_products_url` | replaced by `::test_no_products_url_invents_nothing_and_skips_seeding` | the helper is deleted | the new test asserts `scrape_cart_pages` returns `{}` rather than navigating to a guess |
| `tests/test_placeholder_resolver.py::test_resolve_url_validates_against_scraped_data` (was :901), `::test_resolve_url_validates_relative_urls_against_scraped_data` (was :918) | "should fall back to a known URL" → `assert result is None` | they pinned the non-strict fallback | the same tests now pin the honest unresolved; `tests/test_t0855_resolver_cuts.py::test_resolve_url_has_no_non_strict_fallback_left` asserts the flag itself is gone |
| `tests/resolver_test_helpers.py::resolve_placeholders` | documented; still calls `resolve_url` plainly | it called without `strict`, so every GOTO it wrote used the guess path - it measured a road production had already closed | there is no non-strict mode left, so the helper is strict by construction |
| `tests/test_orchestrator_trail_plumbing.py::test_scrape_journeys_statefully_returns_trail` | stub resolver returns `None` (was `"http://b"` for every call) and the fixture sets `_starting_url` | the old stub could not tell a trail URL from an invented one - the assertion passed either way, and the fixture only worked *because* a guess answered first | the assertion on `"http://b"` now proves the trail carried it |
| `tests/test_orchestrator.py::test_build_candidate_urls_stays_scoped_to_expected_journey_pages` | asserts `discovered == [seed]` (was: `/cart` present) | it pinned the invented candidate | the same test now pins the opposite |
| `tests/test_t0855_resolver_cuts.py` | +2 tests: a first-step GOTO records a skip; `resolve_url` has no non-strict mode | the brief's "a story that used a guessed page now records an honest skip" | the new tests |

## 4. Grep proof (no test expects an invented URL)

`grep -rn "/basket\|/inventory.html\|/cart.html" tests/` returns only: fixture pages that were
**scraped** (a `scraped_data` key, a real `href`, a golden `expected_page`), route *normalisation*
(`normalize_route("…/basket") == "cart"`), flow-memory route matching, and evidence/URL-format
tests. `build_common_path_candidates`, `_derive_products_url` and
`heuristic_url_from_description` appear in no test except the two that assert they are **gone**.

## 5. Gates

| Gate | Result |
|---|---|
| pytest (full) | see the commit message: whole suite green |
| smoke | 39/39 |
| ruff + mypy | clean |
| eval static | unchanged (frozen captures; no GOTO goldens) |

The four-leg held-out re-measure is a separate go and was **not** run here. Its expected effect:
the `/basket` and `/inventory.html` arrivals that moved eval-002 in the last re-measure can no
longer be produced at all, because those addresses are no longer in any list.
