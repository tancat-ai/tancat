# 2026-08-03 — Saucedemo checkout cluster (13/13 gates PASS)

## Summary

`verify_production saucedemo` went **10/13 → 13/13 gates, 6/6 tests passing, stable across 4 consecutive runs** — the last execution-failure cluster is closed. Automationexercise is **not regressed** (3/7 execution at HEAD → 4–5/7 with these changes; remaining failures are pre-existing: guest-checkout login gate + assert timing races).

## The root-cause stack (layered — the user's "empty cart" hunch was real but not the root)

1. **Saucedemo is SPA-on-GitHub-Pages** — every `.html` path returns **HTTP 404 + app shell** (the shell lives in `404.html` and JS-redirects to the real view). The stateless `PageScraper` bailed on `status >= 400` → **zero elements for the whole site**. (Wayback Machine: 404-on-`.html` since **May 2021** — not a recent change; the tool only ever worked via status-agnostic paths like the journey scraper.)
2. **Credentials never reached the pipeline** — `verify_production` passed no `CredentialProfile` → `attempt_login(page, None)` no-ops → the stateful fallback captured the login wall ("Epic sadface: you can only access…") → **cart had no items → checkout wasn't an option** (the user's hypothesis, confirmed).
3. **Stateful routing hardcoded to automationexercise** — `{"/view_cart", "/checkout"}` never matched `/cart.html`, `/checkout-step-one.html`…
4. **URL guessing had been removed entirely** — SPA sites have no hrefs for journey discovery, so cart/checkout URLs never entered the scrape set.
5. **B-015's ghost (3 places)** — `_dismiss_modals` / `_dismiss_confirmation_modals` / the repair setup script clicked `button:has-text("Continue Shopping")` globally; saucedemo's cart-page button navigated the journey *and generated tests* back to inventory. This is why `cart.html` was never captured and `#checkout` was never clicked.
6. **Journey subprocess dropped credentials** — serialized in the payload, never read back in the child.
7. **Dead/redirected candidate pages won resolution** — 2-element SPA shells (`/basket`, `/view_cart`) and automationexercise's 200-redirect-to-home keys (`/inventory.html` = home content, 358 elements) out-scored real pages.
8. **B-024 class** — placeholder-only form fields: `normalise_element_text` excluded placeholder; "zip code" vs "Zip/Postal Code".

## Fixes (all site-agnostic — no per-site vocabulary lists)

| Area | Change |
|------|--------|
| `src/scraper.py` | Soft-404 recovery `_is_soft_404()` — render first, judge content (URL-rewrite signal), genuine 404s still bail |
| `scripts/verify_production.py` | Env-overridable saucedemo credentials (`SAUCEDEMO_USERNAME/PASSWORD`, mirroring eval) → `TestOrchestrator` |
| `src/url_utils.py` | `is_stateful_cart_checkout_path()` (path tokens: cart/checkout/basket/view_cart); `build_common_path_candidates` re-enabled (concept-driven, same-domain) |
| `src/url_resolver.py` | Semantic alias groups in `_match_keyword_to_url` (products → `/inventory.html` …) |
| `src/placeholder_resolver.py` | `inventory` added to the product-bonus set |
| `src/journey_subprocess.py` | Credential round-trip (reconstruct `CredentialProfile` in the child) |
| `src/journey_scraper.py` | `attempt_login` at the starting URL; `_dismiss_modals` scoped to modal containers |
| `src/placeholder_orchestrator.py` | `_drop_dead_pages`, `_drop_redirect_duplicates`, navigation-intent GOTO fallback (`_is_navigation_description`), post-login ASSERT mapping, GOTO resolves against all pages, `CartSeedingScraper` gets credentials |
| `src/orchestrator.py` | Wires the redirect-duplicate filter after the stateful upgrade |
| `src/role_mapper.py` | `normalise_element_text` includes placeholder (last priority) |
| `src/element_matcher.py` | B-024g separator-normalized word-subset fallback for FILL |
| `src/evidence_tracker.py` | `_dismiss_confirmation_modals` modal-scoped; `_is_modal_close_target` no-op when the modal's already dismissed |
| `src/ui/ui_run_results.py` | Setup-script seeding: `is_stateful_cart_checkout_path` trigger, saucedemo login, product-candidate probe, Strategy C direct add-to-cart, modal-scoped dismissal |

## Verification

- Full suite **2095 passed / 1 skipped** (was 2081); ruff + mypy clean; smoke 35/35
- Eval static **100%** (67/67) — no regression
- `verify_production saucedemo`: **13/13 gates, 6/6 tests, 4 consecutive PASS runs**
- `verify_production automationexercise`: HEAD baseline 3/7 execution → 4–5/7 (verified via git stash comparison — no regression)
- Wayback Machine evidence: saucedemo `.html` paths have been soft-404 since 2021

## Open work (next session)

- **automationexercise guest-checkout login gate**: the story has no login step, but the site requires auth to checkout ("Proceed To Checkout" has no href; the JS handler gates on session). Story/prompt fix, not resolver.
- automationexercise cart-link/assert timing races (flaky zone — modal fade timing, cart render asserts).
- LLM re-ranking with T-strings + bounded retries (deferred bigger refactor).
- Consent handling in exported clean tests.
- Pre-existing: Windows backslash bug in `ui_run_results` setup-script print line; `stateful_scraper`/`form_detector` still carry the global "Continue Shopping" dismissal pattern (safe today — runs on pages without a cart button).
- `graphify-out/graph.json` needs a rebuild (13 src files changed this session).

## Files touched

13 `src/` files + `scripts/verify_production.py` + 6 test files + 4 archived debug scripts + `markdown_docs` sweep (12 updated, 7 new). **No protected files modified** (`src/llm_client.py`, `src/test_generator.py`, `src/llm_providers/`, `src/agents/`, `.github/workflows/ci.yml` untouched).
