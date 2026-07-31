# Session Summary — 2026-07-30 (Phase 1d Eval Validation)

## Goal
Complete Phase 1d of the LangGraph multi-agent pipeline: fix graph self-consistency,
journey URL inference, and mock server stability.

---

## What We Shipped

### 1. Temperature=0 — Graph Skeleton Self-Consistency (55.6% → 100%)

**Root cause:** No LLM call pinned temperature. Planner and Generator produced
different skeletons on every run.

**Fix — 4 files changed:**

| File | Change |
|------|--------|
| `src/llm_providers/__init__.py` | Added `temperature: float \| None` to `LLMProvider.complete()` ABC + all 3 implementations (OpenAI, LMStudio, Ollama). When set, included in JSON payload. |
| `src/llm_client.py` | Threaded `temperature` through `_complete_sync()` → `provider.complete()`, then through `generate()`. Backward compatible — default None preserves existing behavior. |
| `src/agents/planner.py` | `temperature=0` on `self._client.generate()` — deterministic test plans |
| `src/agents/generator.py` | `temperature=0` on `self._client.generate()` — deterministic skeletons |

**Verification:** Two consecutive graph runs produce byte-for-byte identical skeletons
(verified on 3-condition LV Insurance and 3-condition saucedemo).

### 2. Journey URL Inference — Checkout Pages Now Reachable

**Root cause:** The journey scraper could only discover new pages by clicking elements.
When the skeleton said "CLICK: checkout button" on the inventory page (where no such
button exists), the journey got stuck. Cart and checkout pages were never reached.

**Fix — 2 files changed:**

| File | Change |
|------|--------|
| `src/journey_scraper.py` | `_infer_url_from_description()` — when a CLICK can't find its target element, constructs candidate URLs from keyword patterns (cart→`/cart.html`, checkout→`/checkout-step-one.html`, etc.) and probes them via HEAD request. Falls back to direct navigation if HEAD fails. |
| `src/journey_scraper.py` | Auto-scrape after URL-inferred navigation — previously navigate-only steps didn't capture the destination page's elements. |
| `src/placeholder_resolver.py` | `_discover_urls_from_elements()` — extracts anchor hrefs from scraped elements for URL resolution after scraping completes. |

**Verification:** SauceDemo pages scraped went from 2 (home, inventory) → 5 (home,
inventory, checkout-step-one, checkout-step-two, checkout-complete). URL resolver
now maps `checkout` → `checkout-step-one.html`.

### 3. Mock Server Stability

**Root cause:** `python -m http.server` is single-threaded and crashes on
`BrokenPipeError` during long graph runs with concurrent Playwright requests.

**Fix — 2 files:**

| File | Change |
|------|--------|
| `scripts/mock_server.py` | NEW — `MockServer` class using `ThreadingHTTPServer` with daemon threads, `BrokenPipeError` suppression, and context-manager auto-stop. Standalone `--port/--directory` CLI. |
| `scripts/eval/eval_runner.py` | `_ensure_mock_server()` — auto-starts mock server when eval-005 (lv_insurance) is detected. Daemon threads auto-stop on process exit. |

**Verification:** Server starts, serves the 59KB mock insurance site, responds to
HEAD probes, and auto-stops on context exit.

### 4. Architecture Documentation (Phase 1e)

| File | Change |
|------|--------|
| `AGENTS.md` | Added `src/agents/` to protected files list |
| `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` | Updated session tracking + Phase 1 status |
| `docs/specs/FEATURE_SPEC_AI037_lv_insurance_resolution_gap.md` | NEW — spec for the 46% LV Insurance resolution gap |

---

## Graph Pipeline Test Results (SauceDemo)

Post-fix graph pipeline generates correct, resolved selectors for the first 3 tests
(login, add to cart, verify cart). The remaining 3 tests (checkout, complete checkout,
verify thank you) fail on resolver accuracy issues — camelCase→kebab-case mismatches
(`firstName` vs `#first-name`) and vague ASSERT descriptions — not architecture issues.

| Test | Selectors | Status |
|------|-----------|--------|
| test_01 Login | `#user-name`, `#password`, `#login-button` | ✅ All correct |
| test_02 Add to cart | `#add-to-cart-sauce-labs-backpack` | ✅ Correct |
| test_03 Verify cart | `.shopping_cart_link`, `#item_4_title_link` | ✅ Correct |
| test_04 Navigate checkout | `pytest.skip` (ASSERT "Checkout" unresolvable) | ⚠️ Resolver |
| test_05 Complete checkout | 6 skips (camelCase IDs) | ⚠️ Resolver |
| test_06 Verify thank you | 6 skips + wrong element (`#login_credentials`) | ⚠️ Resolver |

---

## Quality Gates

| Gate | Result |
|------|--------|
| ruff | ✅ Clean |
| mypy | ✅ Clean |
| Unit tests | ✅ 1788 passed, 1 skipped |
| Static eval (5 sites) | ✅ 100% (67/67) |
| Linear UAT (saucedemo) | ✅ 10/10 passed |
| Graph self-consistency | ✅ 100% (was 55.6%) |
| SauceDemo pages scraped | ✅ 5 pages (was 2) |

---

## Remaining (Not Phase 1d)

The remaining test failures are **resolver accuracy** issues (description-to-element
matching), not architecture. These are tracked in:

- **AI-037** — LV Insurance resolution gap (46% unresolved — same symptom: camelCase IDs, vague ASSERTs, scoring false positives)
- **B-016** — Synonym-aware matching and ASSERT role filtering (existing backlog)

---

*Session date: 2026-07-30*
*Phase: 1d (complete) + 1e (docs only)*
