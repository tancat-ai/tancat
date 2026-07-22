# BACKLOG.md
## AI Playwright Test Generator

Last updated: 2026-07-22 (LV Insurance mock site + Ingestion Agent foundation)

---

## 🆕 AI-030 — LV Insurance Mock Site & Ingestion Agent Foundation (2026-07-22)

**Status:** 🟡 ready-for-agent  
**What:** Built a 7-step LV car insurance quote flow mock site (60KB HTML) and assembled real LV product documents for the Phase 1 Ingestion Agent.

**Done:**
- `generated_tests/mock_insurance_site.html` — full quote flow with reg lookup, driver management, premium calc, decline path
- `docs/rag_corpus/lv_docs/` — 7 docs (3 real LV PDFs + 3 redacted personal + 1 synthetic underwriting guide)
- `scripts/eval/dataset/eval-005_lv_insurance_quote.json` — 10 criteria, 33 golden placeholders

**Next:** Wire PDF parsing into `rag_ingest.py`; measure RAG improvement on LV Insurance eval.

---

### ✅ CI-001 — Consolidate CI/CD Pipeline (2026-06-21)
**What:** Merged `ci.yml` and `project-health.yml` into a single gated pipeline.
**Changes:**
- Gate chain: sanitizer → ruff → mypy → pytest (fail fast, no wasted minutes)
- Added `concurrency` block to auto-cancel stale runs on same branch
- Added `setup-uv` caching (`enable-cache: true`) — caches `.venv` between runs
- Added Playwright browser cache via `actions/cache` keyed on `uv.lock` hash
- Added `--frozen` to all `uv sync` calls — fails if lockfile is stale
- Added failure artifact upload (`test-results/`, `screenshots/`) with 7-day retention
- Deleted `project-health.yml`

### ✅ CI-002 — Fix project_sanitizer bugs (2026-06-21)
- Fixed `PROJECT_ROOT` resolution (`.parent.parent` → `.parent.parent.parent`)
- Added `exported_tests/` to `SKIP_DIRS`
- Orphan `.md` files are warning-only (exit 0), not CI-breaking
- Deleted junk `scripts/debug/cli_test_capture.log`

---

## ✅ Shipped (doc audit 2026-05-17)

| ID | Status | Notes |
|----|--------|-------|
| AI-016–AI-022 | **Complete** | Evidence chain: tracker, spec analysis, test plan UI, annotated screenshots, Gantt, coverage + suite heatmaps |
| AI-024 | **Complete** | `AccessibilityEnricher` + CDP `getFullAXTree` in PageScraper (not `page.accessibility.snapshot()`) |
| B-0XX | **Complete** | Journey + stateful scrapers use same visibility + a11y enrichment as PageScraper |
| Prerequisite injection (Stage A) | **Complete** | `PrerequisiteInjector` in orchestrator |
| Keyword URL resolution | **Complete** | `UrlResolver` for GOTO; Phase 3 page scoping wired 2026-05-17 |
| Resolver restructure Phase 0–1 | **Complete** | Dead methods removed from `placeholder_resolver.py` |
| Resolver restructure Phase 2 | **Partial** | Pass 1 (CLICK/FILL + ASSERT text), Pass 2 structural, Pass 3 scoring+LLM; pass logging added |
| AI-019 | **Superseded** | Skeleton uses placeholders; `code_postprocessor` injects `evidence_tracker` — no LLM evidence rules needed |
| Phase 4 Export (core) | **Complete** | `ExportMode` enum, `ExportService.export()`, `strip_evidence_from_test_code()`, `strip_evidence_from_pom()`. 28 tests. **TODO:** Streamlit panel + CLI menu. |

**Still open (high level):** (none at this time)

---

## ✅ AI-027 — Visual Element Enrichment (COMPLETE — All 4 Sessions Done)

**What:** Vision-based element enrichment for improved placeholder resolution on multi-product sites.
**Session 1 complete:** `VisionEnricher` + vision capability detection.
**Session 2 complete:** Screenshot capture during scraping, with interactive element bounding boxes stored in memory.
**Session 3 complete:** Vision enrichment service with element crop, mocked LLM call path, response parsing, and scraper enrichment bridge.
**Session 4 complete:** Vision enrichment wired into orchestrator pipeline + `_vision_enriched_bonus()` in PlaceholderScorer using `product_name`, `price`, `visual_label`, `enrichment_note`, `description` fields.
**Spec:** `docs/specs/FEATURE_SPEC_visual_element_enrichment.md`
**Priority:** High — placeholder resolution quality on multi-product sites

---

## ✅ Closed Bugs

### B-001 — LLM generates async standalone tests instead of pytest sync
**Fixed:** System prompt updated in `src/llm_client.py`.

### B-002 — LLM output occasionally has all imports on one line
**Fixed:** `normalise_code_newlines()` added to `src/file_utils.py`.

### B-003 — Generated tests not saved to `generated_tests/` automatically
**Fixed:** Phase A auto-save implemented.

### B-005 — `launch_ui.sh` starts mock server (not appropriate for general use)
**Fixed:** Mock server startup moved to `launch_dev.sh`.

### B-006 — Parser banner wrong when mix of pass/fail
**Fixed (Session 10):** Current parser implementation correctly uses last summary-line match.
Regression tests added: `test_b006_mixed_pass_fail_banner_correct`, `test_b006_all_fail_banner`.

### B-007 — Error panels duplicated in results view
**Fixed (Session 10):** Removed duplicate error rendering loop from `display_coverage()`. Errors
now render only in `display_run_button()`.

### B-009 — No ast.parse() validation before saving generated test files
**Fixed (Session 11):** `src/code_validator.py` created with `validate_python_syntax()`.
Integrated into `src/file_utils.py` `save_generated_test()` — raises `ValueError` before
writing if code fails syntax check.

### BREAK-1 — `src/pytest_output_parser.py` missing (CI BLOCKER)
**Fixed (Session 9):** `src/pytest_output_parser.py` committed.

### BREAK-2 — Session state wipe blanks run results panel
**Fixed (Session 9):** Reset lines removed from `display_run_button()`.

### B-008 — Run Status column shows ⏳ for all rows (never updates)
**Fixed (Session 13):** Coverage x Run Results now maps run outcomes through shared coverage utilities.

### B-010 — POM AttributeError: 'navigate' vs 'goto'
**Fixed (Session 16):** Standardized all POM-based navigation to `navigate()` in `PageObjectBuilder`. Added `__getattr__` safety net to generated POMs to `pytest.skip` missing methods instead of crashing.

### B-011 — LLM Placeholder Syntax Error
**Fixed (Session 15):** Improved `SkeletonValidator` to reject Python variable syntax in placeholders. Added `_replace_remaining_placeholders()` safety net to ensure final code is syntactically valid by skipping unresolved tokens.

---

## 🔴 Open Bugs

### B-004 — Ambiguous locators when same label exists on multiple forms
**Symptom:** `strict mode violation: get_by_label("Driver Name") resolved to 2 elements`
**Fix (short term):** Use `page.locator("#specificId")` instead of `get_by_label`
**Fix (long term):** Multi-page scraping (AI-009) injects real selectors
**Priority:** Medium — AI-009 should prevent recurrence

### B-012 — Pass 1 false positive: "add to cart" matches cart nav link
**Status:** ✅ FIXED (2026-05-17)
**Symptom:** CLICK:'Add to cart' button resolves to a[href="/view_cart"] (text="Cart")
because "cart" appears in both the description and the nav link text.
**Root cause:** Pass 1 minimum length guard (3 chars) allows short common words
to match across unrelated elements.
**Fix implemented:** Action verb awareness in `_pass1_text_match()` — when the
description contains action verbs (add, remove, place, buy, etc.), the element
text must also contain at least one of those action words. Prevents "View Cart"
from matching "Add to cart button" because "View Cart" lacks the word "add".
**Files changed:** `src/placeholder_orchestrator.py` — `_pass1_text_match()`
**Verification:** UAT automationexercise.com 6/6 tests pass (was 4/6).

### B-015 — Journey discovery selects wrong element for action descriptions
**Status:** ✅ FIXED (2026-06-23) — `dismiss_consent_overlays` rewrite
**Symptom:** Journey discovery clicks wrong elements, causing it to visit wrong pages:
- `"checkout button"` → `#react-burger-menu-btn` (burger menu, score=1) — opens side menu instead of checkout
- `"continue button"` → `#react-burger-menu-btn` (score=1) — same wrong element
- `"finish button"` → `#react-burger-menu-btn` (score=1) — same wrong element
- `"first name:John"` → `.product_sort_container[data-test="product-sort-container"]` (score=1) — `<select>` element, not a fillable input
- `"zip/postal code:12345"` → `.shopping_cart_link[data-test="shopping-cart-link"]` (score=10) — an `<a>` link, not an input

On automationexercise.com: `"Add to cart button"` → `a[href="/view_cart"]` (Cart link).

**Root cause:** `dismiss_consent_overlays()` in `src/browser_utils.py` used aggressive
global text matching (`button:has-text('Continue')`) that matched the `#continue-shopping`
button on saucedemo's cart page. This function is called before every click step in the
journey scraper — so the cart page navigated back to inventory.html before the next
scrape ran. The journey scraper then scraped `inventory.html` (29 elements) instead of
`cart.html` (14 elements), and selected `#react-burger-menu-btn` for "checkout button".

**Impact:** Journey discovery clicks the burger menu instead of checkout, navigating
to inventory.html instead of checkout-step-one.html. This means:
1. Checkout pages (`checkout-step-one.html`, `checkout-step-two.html`) are **never scraped**
2. The placeholder resolver has **zero data** for checkout form fields
3. `test_06_complete_checkout` gets `pytest.skip()` for all checkout FILL fields
4. The downstream placeholder resolver cannot compensate because the data simply doesn't exist

**Confirmed via UAT:** `scripts/uat/uat_automationexercise.py --site saucedemo` (2026-06-22):
- Journey clicks `#react-burger-menu-btn` for "checkout button" on cart page
- Click navigates `cart.html` → `inventory.html` (wrong)
- Pages scraped: only 3 URLs (home, inventory, cart) — checkout pages missing
- Resolver fails on: 'first name', 'last name', 'zip/postal code', 'finish button', 'thank you message'
- Final code: `test_06` has `pytest.skip()` for unresolved placeholders

**Fix:** Rewrote `dismiss_consent_overlays()` in `src/browser_utils.py` with a 3-stage approach:
1. **Google Consent TVM** — specific `.fc-consent-root` selectors (unchanged, safe)
2. **Structural containers** — known consent provider classes (`oneTrust`, `cookie-banner`,
   `Cookiebot`, `[role='dialog']`, etc.) — only click buttons **inside** these containers
3. **Position-based detection** — JS finds fixed/sticky elements near bottom of viewport,
   then looks for dismiss buttons inside them
4. **Ad overlay removal** — specific selectors only (Google Vignette, ASWIFT)

**Removed:** Generic text matching (`button:has-text('Continue')`, `button:has-text('OK')`)
on global page, dangerous `zIndex > 10000` DOM removal, `allElements` iteration over entire DOM.

**Verification (2026-06-23 saucedemo UAT after fix):**
- `#checkout` selected with score=12 for "checkout button" on `cart.html` ✅
- `#first-name` (score=90), `#last-name` (score=90), `#continue`, `#finish` all resolved ✅
- All 5 checkout pages scraped: `cart.html`, `checkout-step-one.html`, `checkout-step-two.html`,
  `checkout-complete.html` ✅
- `test_06_complete_checkout` has only 1 skip (ASSERT "Thank You page header" — B-014)
  instead of 8+ skips before ✅

**Files changed:**
- `src/browser_utils.py` — complete rewrite of `dismiss_consent_overlays()`
- `tests/test_browser_utils.py` — NEW — 10 tests covering safety (no false clicks),
  structural containers, Google Consent TVM, and zIndex removal regression

**Priority:** High — causes cascading failure (wrong click → wrong page → missing scrape → zero resolution)

### B-013 — Journey discovery stops one page short for checkout-step-two
**Status:** ✅ RESOLVED (2026-06-23) — root cause was B-015, now fixed
**Original claim:** "Journey discovery doesn't scrape the page after the final click"
**Actual finding (saucedemo UAT, 2026-06-22):** Journey discovery never reaches
checkout pages at all — it clicks `#react-burger-menu-btn` (burger menu) for
"checkout button", navigating to inventory.html instead of checkout-step-one.html.

**Impact:** Both `checkout-step-one.html` and `checkout-step-two.html` are missing
from scraped data. This is a B-015 consequence.

**Fix:** B-015 fix (rewrite of `dismiss_consent_overlays`) allows journey to reach
checkout pages. Verified: all 5 checkout pages now scraped correctly.
**Priority:** Medium — superseded by B-015, resolved via same fix

### B-016 — text_matches_description() fails on synonyms
**Status:** 🟡 PARTIALLY FIXED — negation detection + synonym expansion (2026-06-29)
**Symptom:** `PlaceholderResolver.text_matches_description()` produces false negatives
on semantically equivalent text and false positives on semantically contradictory text.

**Test results (from debug_compare.py, 2026-06-22):**
- ❌ `"Login"` vs `"Sign in button"` → False (expected True) — synonym not recognised
- ❌ `"Dress"` vs `"product category link"` → False (expected True) — proper noun vs generic descriptor
- ❌ `"Blue Top"` vs `"a product name"` → False (expected True) — same pattern
- ❌ `"Your cart is empty!"` vs `"cart content with items"` → True (expected False) — "cart" keyword overlap matches despite semantic contradiction (empty ≠ with items)
- ❌ `"Cart is empty"` vs `"cart page with selected items"` → True (expected False) — same false positive

**Root cause:** Text matching uses keyword/token overlap without semantic understanding.
No synonym dictionary or negation detection. "cart" + "content" in description matches
"cart is empty" because both contain "cart". Negation words ("empty", "no", "not") are
not treated as exclusion signals.

**Impact:** Placeholder resolution passes/fails incorrectly for login-related elements,
product names, and cart state assertions. This is a 33% failure rate on text validation
(5/15 checks fail consistently across both automationexercise and saucedemo).

**Priority:** High — foundational matching logic affects all resolution paths

**Fix implemented (2026-06-29):**
1. **Negation gate** — `_is_negated()` rejects matches when element text contains
   negation words ("empty", "none", "no items", "out of stock", etc.) but the
   description signals positive content ("with items", "selected", "visible",
   "loaded", etc.). Domain-agnostic — works on any site.
2. **Synonym-aware Jaccard** — After the original matching logic (containment,
   word-overlap, action-verbs), a fallback computes Jaccard similarity on
   *expanded* token sets from `SemanticMatcher.get_words(expand_aliases=True)`.
   The TOKEN_EXPANSIONS map is the single source of synonym truth — no duplicate
   dictionaries. Threshold 0.30 requires meaningful overlap.
3. **TOKEN_EXPANSIONS additions** — Added authentication/identity group:
   `login ↔ sign ↔ signin ↔ authenticate`, `logout ↔ sign-out ↔ signout`,
   `signup ↔ register ↔ sign-up`, `sign-out ↔ logout`.

**UAT results (2026-06-29):**
| Element text | Description | Before | After | Method |
|-------------|-------------|--------|-------|--------|
| "Login" | "Sign in button" | False ❌ | True ✅ | synonym Jaccard |
| "Your cart is empty!" | "cart content with items" | True ❌ | False ✅ | negation gate |
| "Cart is empty" | "cart page with selected items" | True ❌ | False ✅ | negation gate |
| "Items in your cart" | "cart content with items" | True ✅ | True ✅ | unchanged |
| "Dress" | "product category link" | False ❌ | False ❌ | needs LLM (B-020) |
| "Blue Top" | "a product name" | False ❌ | False ❌ | needs LLM (B-020) |

**Remaining cases (2/6):** "Dress"/"product category link" and "Blue Top"/"a product name"
are proper nouns vs. generic descriptors — zero token overlap with no synonym bridge.
These require LLM-assisted semantic matching (B-020) and are out of scope for keyword-based
resolution. This is by design: keyword matching handles the common cases; LLM handles
the semantically ambiguous ones.

**Files changed:**
- `src/placeholder_resolver.py` — `_NEGATION_WORDS`, `_POSITIVE_INDICATORS`,
  `_is_negated()`, updated `text_matches_description()` with negation gate + Jaccard
- `src/semantic_matcher.py` — added authentication/identity TOKEN_EXPANSIONS

**Tests:** `tests/test_placeholder_resolver_text_validation.py` — new B-016 test class

**Follow-up:** B-020 LLM wiring will handle the remaining 2/6 cases when complete.

---

### B-017 — FILL placeholders on unreachable pages fail to resolve
**Status:** ✅ CORRECTED — B-015 fix resolves checkout FILL failures (2026-06-23)
**Original claim:** "All FILL-type placeholders return zero ranked candidates" — 100% FILL failure.
**Actual finding:** FILL on **login pages** resolves correctly. FILL on **unreachable pages** fails.

**Evidence (saucedemo UAT, 2026-06-22):**
- Login FILL placeholders (`'username'`, `'password'`) → resolved to `#user-name`, `#password` ✅
  - Note: resolver logs say `Failed to find 'username'` but final code has correct selectors
  - This is because **prerequisite injection** reuses the resolved selectors from test_01
  - The resolver itself may still be failing — it's masked by prerequisite injection
- Checkout FILL placeholders (`'first name'`, `'last name'`, `'zip/postal code'`) → `pytest.skip()` ❌
  - Root cause: journey discovery clicked wrong element (`#react-burger-menu-btn` instead of `#checkout`)
  - Checkout pages were never scraped — resolver has zero data for those elements
  - This is a **B-015 consequence**, not a standalone resolver bug

**Impact:** FILL failures on checkout are caused by B-015 (journey discovery clicking wrong elements).
Fixing journey discovery's element selection should allow checkout pages to be scraped,
which would give the resolver data for checkout FILL fields.

**Open question:** Does the resolver itself fail on login FILL fields even when data is available?
The `Failed to find 'username'` debug messages suggest yes, but prerequisite injection masks it.
Needs isolated test: resolve `'username'` placeholder against saucedemo.com login page data WITHOUT prerequisite injection.

**Priority:** Medium — partially masked by prerequisite injection, partially caused by B-015

**Fix:**
1. ✅ B-015 fixed (2026-06-23) — checkout FILL placeholders now resolve: `#first-name`,
   `#last-name`, `#postal-code` all resolved correctly
2. Open: Isolate whether resolver itself fails on login FILL fields without prerequisite injection

---

### B-018 — Resolver gap: login elements fail in resolver but succeed in journey
**Status:** ✅ CORRECTED via saucedemo UAT (2026-06-22)
**Original claim:** "Journey discovery and resolver use different matching logic"
**Actual finding:** The gap is real but the primary impact is different than originally diagnosed.

**Evidence (saucedemo UAT, 2026-06-22):**
- Journey discovery: `#user-name` score=95, `#password` score=3, `#login-button` score=2 ✅
- Placeholder resolver logs: `Failed to find 'username'`, `Failed to find 'password'`, `Failed to find 'login button'` ❌
- Final code: `#user-name`, `#password`, `#login-button` ✅ (via prerequisite injection masking)

The resolver says it failed, but the final code is correct because prerequisite
injection reuses previously-resolved selectors. This masks the resolver bug.

**What ISN'T a gap:** Post-login page elements (inventory, cart) resolve fine
because those pages are scraped and the resolver finds matches.

**What IS a gap:** Login page elements — the resolver cannot match `'username'`
against `#user-name` even though journey discovery scores it 95/100. The resolver
is returning zero candidates for elements that exist in the scraped data.

**Root cause:** The resolver's matching pipeline (Pass 1 text, Pass 2 structural,
Pass 3 scoring+LLM) is not finding matches for input elements with no visible text.
Journey discovery uses a different scorer that considers `id`, `name`, `placeholder`
attributes directly.

**Priority:** Medium — masked by prerequisite injection in most cases, but real bug exists
**Fix:** See B-017. Needs isolated test without prerequisite injection to confirm.

---

### B-014 — ASSERT tokens resolve to wrong elements silently
**Status:** 🟡 PARTIALLY FIXED — step-context exclusion implemented (2026-06-25)
**Symptom:** ASSERT placeholders resolve to completely wrong elements:

**Evidence (saucedemo UAT, 2026-06-22 — BEFORE fix):**
- `"product inventory page"` → `#login-button` ❌
- `"cart badge shows 1"` → `.shopping_cart_link` ❌
- `"shopping cart page title"` → `.shopping_cart_link` ❌
- `"sauce labs backpack in cart"` → `#remove-sauce-labs-backpack` ❌
- `"checkout information page"` → `#checkout` ❌
- `"thank you message"` → `#user-name` ❌

**Root cause:** ASSERT resolution has no awareness of the preceding interactive step.
When a CLICK or FILL resolved to element X, the subsequent ASSERT could also resolve
to X because the scorer finds structural overlap. Additionally, the scorer doesn't
filter by element type for ASSERT actions.

**Fix implemented (2026-06-25):** Step-context exclusion in `src/placeholder_orchestrator.py`:
- CLICK/FILL steps track `last_selector` / `last_description` through the journey loop
- ASSERT resolution excludes the previous selector unless descriptions reference the
  same element (strict containment: `norm_a in norm_b or norm_b in norm_a`)
- Exclusion applied across all resolution passes (text, ASSERT-text, structural, scoring)
- Same-element assertions allowed (e.g. "login button" → "login button is disabled")
- Spec: `docs/specs/FEATURE_SPEC_B014_step_context_resolution.md`
- Tests: `tests/test_b014_assert_resolution.py` (53 tests, 100% pass)

**UAT results (2026-06-25 — AFTER fix):**
| ASSERT | Before | After | Improvement |
|--------|--------|-------|-------------|
| `"inventory page title"` | `#login-button` (PASSED — false green) | `#login-button` (FAILED — correct) | ✅ False green → real failure |
| `"cart badge with count 1"` | `.shopping_cart_link` | `.shopping_cart_link` | ❌ Unchanged — see B-016 |
| `"Sauce Labs Backpack item in cart"` | `#remove-sauce-labs-backpack` | `#remove-sauce-labs-backpack` | ❌ Unchanged — see B-016 |
| `"checkout information form"` | `#checkout` (PASSED — false green) | **SKIP** (unresolved) | ✅ False green → skip |
| `"Thank You page message"` | `#user-name` (SKIP) | **SKIP** | Same — see B-016 |

**Impact of fix:** 2 assertions went from false-green PASS to either real failure
or skip. Tests no longer silently pass for the wrong reason in the cross-step
preceding-interactive case.

**Limitations (tracked separately as B-016):**
1. ASSERTs whose wrong element is NOT the preceding interactive step — resolver
   quality issue, not step-context (see B-016)
2. Within-step ASSERTs on the same skeleton line as CLICK
3. Prerequisite-injected steps bypass step-context tracking

**Priority:** High — silent wrong assertions are worse than skips
**Tests:** `tests/test_b014_assert_resolution.py` (19 tests) — see B-016 for remaining cases.
---

### B-016 — ASSERT resolution quality for non-step-context cases
**Status:** ✅ VALIDATED (2026-06-30) — implementation complete, UAT confirms role filtering + fallback working
**Related:** B-014 (step-context exclusion handles the preceding-interactive case)
**Symptom:** ASSERT placeholders resolve to wrong interactive elements (buttons,
links) instead of display elements.

**Evidence (saucedemo UAT, 2026-06-25, post B-014 fix):**
- `"cart badge with count 1"` → `.shopping_cart_link[data-test="shopping-cart-link"]`
  — the cart navigation link, not a badge. Resolver picks the link because its
  `data-test` attribute contains "cart".
- `"Sauce Labs Backpack item in cart"` → `#remove-sauce-labs-backpack`
  — the REMOVE button. Wins because its `id` contains "backpack".

**Root cause:** The scoring pipeline scores elements by keyword overlap in
`id`, `data-test`, and structural attributes. Any element containing those
keywords wins — even if it's a button, link, or delete control rather than
the intended display element.

**Design decisions (grilling session, 2026-06-25):**
- Role filtering uses `computed_role` from CDP AX tree (AI-024), falling back to
  raw `role` field. The enricher already writes `computed_role` but the resolver
  currently ignores it.
- Display roles defined as a positive constant (`DISPLAY_ROLES`) in the orchestrator.
  No import from `AccessibilityEnricher` needed — resolver stays self-contained.
- `link` and `textbox` excluded from display roles (even though they are leaf
  ARIA roles) — ASSERT descriptions like "cart badge" should not match cart links.
- Soft filtering: prefer display elements first; fall back to all elements if no
  display candidates score above threshold (logged as low-confidence, never skip
  solely due to filtering).
- No description scope awareness — the skeleton doesn't encode element-level vs
  page-level intent. Role filtering + existing scoring pipeline covers the problem.
- Scraper gap (`"Thank You page message"` → SKIP) spun off as B-019.

**Approach:**
1. **ASSERT role filtering (soft)** — for ASSERT actions, score display-role elements
   first using ARIA roles (`heading`, `paragraph`, `text`, `status`, `region`,
   `listitem`, `cell`, `generic`). If no display elements score above threshold,
   fall back to all elements (logged as low-confidence).
2. Implementation lives in `src/placeholder_orchestrator.py`, alongside step-context
   exclusion (B-014). Runs as a pre-filter before scoring passes.

**UAT results (2026-06-25, saucedemo, openai-local/Qwen3.6-27B):**
| ASSERT | Before B-016 | After B-016 | Status |
|--------|-------------|-------------|--------|
| `"cart badge with count 1"` | `.shopping_cart_link` (wrong link) | **SKIP** | ✅ Fixed |
| `"Sauce Labs Backpack item in cart"` | `#remove-sauce-labs-backpack` (wrong button) | **SKIP** | ✅ Fixed |
| `"inventory page visible"` | `#login-button` | `#user-name` | ❌ Still wrong — page-scoping issue, not role |

**Priority:** Medium — role filtering working, low-confidence fallback paths logged correctly

**UAT validation (2026-06-30, saucedemo):**
- `"cart badge with count 1"` → B-016 fallback: best display score=5 is 85 below global top=90 — correctly falls back to non-display element
- `"Sauce Labs Backpack item details in cart"` → B-016 fallback: best display score=90 is 5 below global top=95 — correctly falls back
- Both cases logged with `[RESOLVE]` prefix for diagnostics — filtering is working as designed

---

### B-019 — Scraper misses heading text on JS-rendered pages
**Status:** 🆕 new — spun off from B-016
**Related:** B-016 (ASSERT role filtering)
**Symptom:** BeautifulSoup-based scraper doesn't capture heading text from
pages where content is rendered inside SVG elements or via complex ARIA
relationships (e.g., `aria-labelledby` references).

**Evidence (saucedemo UAT, 2026-06-25):**
- `"Thank You page message"` → **SKIP** (unresolved)
  — `checkout-complete.html` has a checkmark SVG and heading, but the scraper
  captures no meaningful text in `text`, `aria_label`, or `accessible_name`.

**Root cause:** Scraper uses BeautifulSoup on post-`networkidle` HTML. SVG
internal text, `aria-labelledby` cross-references, and dynamically composed
accessible names are not resolved by static HTML parsing. CDP `getFullAXTree`
(AI-024) could resolve these but is not yet wired into the main scraper's
element extraction.

**Approach:** Evaluate whether to enhance the existing scraper with CDP AX tree
resolution, or consider replacing BeautifulSoup with a Playwright-native DOM
walk that captures computed accessible names.

**Priority:** Low — affects completion pages and similar edge cases
**Note:** Separate from B-016 — B-016 is about wrong matches, this is about
missing data.
---

### B-020 — LLM-Assisted ASSERT Resolution
**Status:** ✅ COMPLETE + VALIDATED (2026-06-30)
**Related:** B-014 (step-context exclusion), B-016 (ASSERT role filtering)
**Symptom:** ASSERT placeholders always resolve via mechanical fallback to `assert_visible`. The LLM semantic pass (designed to select appropriate `assertion_type` like `toHaveText`, `toContainText`, `toHaveCount`, etc.) never fires because `SemanticCandidateRanker.generator` is `None`.

**Implementation done (2026-06-28):**
- `src/evidence_tracker.py` — added `assert_text`, `assert_text_contains`, `assert_disabled`, `assert_enabled`, `assert_checked`, `assert_count`, `assert_value`, `assert_empty`
- `src/semantic_candidate_ranker.py` — rewritten to accept step context and return `assertion_type`/`expected_value`
- `src/placeholder_orchestrator.py` — `_resolve_assert_semantically()` method; ASSERT routing through semantic path; `line_resolutions` extended to 7-tuple
- `src/code_postprocessor.py` — `_ASSERTION_TO_ET_METHOD` mapping; routes to correct evidence_tracker method
- `src/orchestrator.py` — `_resolve_placeholder_for_page()` returns 3-tuple `(resolved_value, next_url, assertion_type)`
- Tests updated: `test_semantic_candidate_ranker.py`, `test_orchestrator.py`, `test_orchestrator_dynamic_scrape.py`

**Session 2 (2026-06-30) — LLM wiring complete:**
- **Root cause:** `PlaceholderOrchestrator.__init__` hardcoded `SemanticCandidateRanker(None)` at line 91. The `AsyncGeneratorLike` protocol was never instantiated with a real LLM client.
- **Fix:**
  1. Added `generator: AsyncGeneratorLike | None` parameter to `PlaceholderOrchestrator.__init__`
  2. Changed `SemanticCandidateRanker(None)` → `SemanticCandidateRanker(generator)`
  3. `TestOrchestrator.__init__` now passes `generator=test_generator.client` to `PlaceholderOrchestrator()`
- **Files changed:** `src/placeholder_orchestrator.py` (import + `__init__`), `src/orchestrator.py` (1 line in `PlaceholderOrchestrator()` call)
- **Verification:** `ruff`/`mypy` clean, `1342/1343` tests pass, wiring confirmed via Python check
- **Remaining (optional):** `src/prompt_utils.py` — add `ASSERT:"exact text"` examples for skeleton generation

**UAT results (2026-06-28, openai-local/Qwen3.6-27B, debug_compare.py) — pre-fix baseline:**
| Site | Tests | SKIPs | ASSERT quality | Notes |
|------|-------|-------|---------------|-------|
| AutomationExercise | 6/6 | 1 (home banner) | All `assert_visible` (fallback) | Full pipeline 11-12/12 |
| SauceDemo | 3 tests | 2 unresolved (username/password input) | All `assert_visible` (fallback) | Full pipeline 11/12 |

**Key finding (pre-fix):** Results identical to pre-B-020 baseline because LLM semantic pass always falls back. Mechanical fallback produces the same locators as before.

**Post-fix expected improvement:** The LLM semantic pass now fires, selecting appropriate assertion types (`toHaveText`, `toContainText`, `toHaveCount`, etc.) rather than defaulting to `toBeVisible`.

**UAT validation (2026-06-30, openai-local/Qwen3.6-27B):**
| Site | Tests | SKIPs | Assertion diversity |
|------|-------|-------|--------------------|
| SauceDemo | 12/12 | 0 | `assert_visible`×4, `assert_text`×1, `assert_text_contains`×1 |
| AutomationExercise | 12/12 | 0 | LLM semantic pass active |

**Result:** Pre-fix all ASSERTs defaulted to `assert_visible` (fallback). Post-fix the LLM selects `toHaveText` and `toContainText` where appropriate — 3 unique assertion types vs 1 before.

**Priority:** Medium — unlocked assertion-type diversity (Text, Count, State, Value) for commercial viability
---

### B-021 — Page-state assertions fail to resolve (e.g., "home page visible")
**Status:** ✅ FIXED (2026-07-20)
**Spec:** `docs/specs/FEATURE_SPEC_URL_ASSERT.md`
**Roadmap ref:** Tier 2 — URL-Based Assertions for Page-State Verification
**Symptom:** Page-level ASSERT placeholders like "home page visible" and "dress products page visible"
can never resolve to any DOM element, producing `pytest.skip()` with:
```
Skipping: unresolved placeholders for: 'home page visible'; 'dress products page'
```

**Root cause:** `PageStateAssertStrategy` in `src/intent_matcher.py` correctly detects these as
page-state descriptions but returns `False` for all elements. The resolver has no URL-based
assertion path — `ASSERT` always maps to DOM elements. A heading like "AutomationExercise"
appears on multiple pages, so DOM-element assertions are not reliable page-identity checks.

**Proposed fix:** Extend the resolver to detect page-state ASSERT descriptions and resolve them
to URL assertions (`expect(page).to_have_url(...)`) via the existing `resolve_url()` method.
No new placeholder action needed — the description already carries sufficient signal.

**Why not a DOM element:** On automationexercise.com, the heading "AutomationExercise" appears
on both `/` and `/products`. The only reliable page-identity check is the URL itself.

**Priority:** Medium — skipped tests degrade user trust; URL assertions are more precise than
element-level proxies for page identity.
---

### B-023 — Cart modal intercepts clicks during journey discovery
**Status:** ✅ FIXED (2026-07-20)
**Symptom:** After adding a product to cart on automationexercise.com, the "Added to cart"
confirmation modal (`#cartModal`) blocks pointer events on the "Cart" header link.
The journey scraper retries clicking `a[href="/view_cart"]` but the modal intercepts:
```
<div id="cartModal" class="modal show">…</div> from <section>…</section> subtree intercepts pointer events
```
The journey eventually scrapes the cart page anyway (it navigates directly after retries),
but the retry loop adds noise and delay (~10s per affected test).

**Root cause:** The journey scraper's click step doesn't dismiss overlays before clicking
target elements. `dismiss_consent_overlays()` handles cookie banners but not confirmation
modals that appear after interactions.

**Proposed fix:** Before each click step in journey discovery, check for and dismiss any
visible confirmation/modals/popups. The `CartSeedingScraper` already has a "Continue Shopping"
dismiss step — this same logic should run before clicking cart/checkout navigation links.

**Priority:** Low — tests pass despite the retry noise. Fixing reduces UAT runtime by ~20s.
---

### B-022 — Scraper visits state-dependent pages with no prior session state
**Status:** ✅ FIXED (2026-07-20)
**Spec:** `docs/specs/FEATURE_SPEC_URL_ASSERT.md` (B-021 — related, same user story)
**Symptom:** Tests that navigate to state-dependent pages (e.g., `/view_cart`) resolve
placeholders to elements from an empty-state page. "Proceed to checkout" can't resolve
because the scraper visited `/view_cart` in a fresh browser context with no items added.
Even tests WITH prerequisite add-to-cart steps (TC01.05) resolve cart assertions to
`#empty_cart` — the scraper's data is from an empty cart.

**Concrete failure (automationexercise.com, 2026-07-20):**
```python
def test_tc01_07(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/view_cart')
    pytest.skip("Skipping: unresolved placeholders for: 'Proceed to checkout'")
    evidence_tracker.assert_visible('#empty_cart', label='order summary')
```
The test jumps straight to `/view_cart`. The scraper visited that URL in a fresh session,
found an empty cart, and only `#empty_cart` elements were captured. "Proceed to checkout"
never existed in the scraped DOM → placeholder can't resolve → test skipped.

**Secondary symptom — POM duplication:** Every test in the generated file has duplicate
POM instantiations:
```python
home_page = HomePage(page, evidence_tracker)
home_page = HomePage(page, evidence_tracker)        # duplicate!
generated_page = GeneratedPage(page, evidence_tracker)
generated_page = GeneratedPage(page, evidence_tracker)  # duplicate!
```

**Root cause:** `PageScraper` opens a fresh browser context per URL. State-dependent pages
(view_cart, checkout, order confirmation) show different DOM depending on session state.
Elements only present with items in cart ("Proceed to checkout", cart table rows, quantity
columns) are absent from the scraped data.

**Proposed fix:**
1. When the pipeline detects placeholder descriptions referencing state-dependent pages
   ("Proceed to checkout", "cart table", "order summary"), trigger a **stateful journey scrape**
   that replays prerequisite steps (add to cart → view cart) before scraping
2. Or: the orchestrator should detect that TC01.07's first step is a direct navigation to
   `/view_cart` and inject add-to-cart prerequisites from TC01.03/TC01.04 before scraping
3. Fix POM duplication: investigate `src/page_object_builder.py` instantiation logic

**Priority:** High — this silently corrupts all cart/checkout/order assertions. Tests either
skip (worst case) or resolve to empty-cart selectors (false green).
---

### REF-001 — Rename `src/ui_pipeline.py` / rethink `src/ui/` naming
**What:** `src/ui_pipeline.py` is shared pipeline orchestration used by both
`streamlit_app.py` (Streamlit UI) and `src/cli/pipeline_runner.py` (CLI UI).
The `ui_` prefix implies it's Streamlit-only, but it's infrastructure.
Similarly, `src/ui/` holds Streamlit components while the CLI lives in `src/cli/` —
both are user interfaces, so the naming is inconsistent.

**Proposed rename:**
- `src/ui_pipeline.py` → `src/pipeline.py` (or `src/pipeline_orchestration.py`)
- `src/ui/` → keep as-is for now (Streamlit-specific rendering) or rename to `src/streamlit/`
- Consider whether `src/cli/` and `src/ui/` should share a parent like `src/interface/`

**Impact:** Medium — affects imports in ~10 files. No logic changes.
**Priority:** Low — cosmetic, but prevents future confusion.

---

## 🟡 Active Improvements (Prioritised)

### AI-009 — Multi-Page Scraping ✅ Phase A COMPLETE, ✅ Phase B COMPLETE (2026-05-13)
**Phase A:** Static multi-page scraping with placeholder resolution — COMPLETE.
**Phase B (completed 2026-05-13):** Authenticated journey scraping — single browser
session follows user-defined steps (goto, click, fill, capture, wait), credential profiles
in session state, auth redirect detection, SSO/MFA/CAPTCHA explicit errors.

**Phase B deliverables:**
- `src/journey_scraper.py` — `execute_journey()`, `JourneyScraper`, `CartSeedingScraper`, auth redirect/SSO/MFA/CAPTCHA detection
- `src/orchestrator.py` — journey execution integrated via `journey_steps` parameter in `run_pipeline()`; journey results merge with static scrape data
- `src/ui_pipeline.py` — bridges Streamlit UI data to `TestOrchestrator` with `credential_profile` and `journey_steps`
- Live verification: successful saucedemo.com journey (Login → Products → Cart) via Playwright MCP
- Test fix: `tests/test_stateful_scrape_switch.py` FakeStateful mocks updated to accept `credential_profile`
**Spec:** `docs/FEATURE_SPEC_AI009_phase_b.md`
**Priority:** Highest — core value driver

---

### ✅ AI-026 — Persist Generated Tests Across Sessions (COMPLETE — 2026-06-30)
**What:** CLI + Streamlit support to reload and rerun previously generated test packages from disk.

**Implementation:**
- ✅ Streamlit sidebar panel — `src/ui/ui_saved_packages.py` (264 lines) — list, select, re-run saved suites
- ✅ CLI menu — "Load Existing Generated Tests", "View Package Diagnostics" in `src/cli/main.py`
- ✅ Reuses `src/pipeline_writer.py`/`PipelineArtifactWriter` for save/load consistency
- ✅ `package_manifest.json` per saved package
- ✅ Re-run saved suite + re-run failed only
- ✅ Failure diagnostics viewer

**Priority:** Medium — improves workflow and debugging without changing core generation logic

---

## ✅ Completed: Refactor 2026-05-10 (Parts 1-7)

**Status:** Complete — May 2026. REFACTOR_PLAN_2026-05-10.md delivered.

**Summary:** Extracted 11 modules from 5 parent files, reducing `streamlit_app.py` from 918 → 362 lines (60% reduction). All quality gates passing: ruff clean, mypy clean, 541/541 tests passing, 68% coverage.

**Modules extracted:**
- `src/ui_pipeline.py` — Pipeline execution from `streamlit_app.py`
- `src/ui_renderers.py` — UI rendering from `streamlit_app.py`
- `src/evidence_serializer.py` — JSON serialization from `evidence_tracker.py`
- `src/screenshot_capture.py` — Screenshot utilities from `evidence_tracker.py`
- `src/state_tracker.py` — DOM state tracking from `journey_scraper.py`
- `src/form_detector.py` — Form detection constants from `journey_scraper.py`
- `src/semantic_matcher.py` — Token semantic similarity from `placeholder_resolver.py`
- `src/intent_matcher.py` — Intent filtering from `placeholder_resolver.py`
- `src/code_normalizer.py` — Code normalization from `code_postprocessor.py`
- `src/llm_reasoning_filter.py` — Reasoning text detection from `code_postprocessor.py`
- `src/url_inference.py` — URL transition inference from `placeholder_orchestrator.py`

---

## ✅ Completed: Evidence Tracker Feature Chain (AI-016 through AI-022)

**Status:** Complete — April 2026. All seven items delivered.

### Tier 1: Self-Diagnosing Failure Evidence
- `src/failure_reporter.py` — `FailureReporter` class with `diagnose_failure()`, `generate_failure_note()`, `categorize_elements()`, `suggest_locators()`, `snapshot_to_text()`
- `src/evidence_tracker.py` — captures failure_note in result dict, records page URL and screenshot at failure point
- `src/evidence_report.py` — renders failure_note in annotated evidence viewer
- Test: `tests/test_failure_reporter.py` — 10 tests covering all methods
- Behavior: When a test step fails, evidence captures URL, screenshot, available locators, and human-readable failure note. Test still fails — no auto-recovery.

### Tier 2: Locator Scoring + Controlled Fallback
- `src/locator_scorer.py` — `LocatorScorer` class with confidence scoring per locator type (specific ID > aria-label > CSS selector > get_by_label)
- `src/evidence_tracker.py` — `record_step()` checks `fallback_used` flag, sets `partial_pass` status when fallback was used, logs full fallback chain with scores
- `src/failure_reporter.py` — `suggest_locators()` uses scorer to recommend higher-confidence alternatives
- Test: `tests/test_locator_scorer.py` — 10 tests covering all scorer methods
- Behavior: When primary locator fails, tries 1-2 higher-scoring alternatives. Every fallback logged in evidence with scores. Tests using fallbacks marked `partial_pass` — flagged for review.

### Tier 3: Suite Heatmap — Per-URL, Not Per-Test (Redesigned)
- `src/evidence_report.py` — `generate_suite_heatmap()` redesigned from requirements-to-tests table to per-URL element coverage
- Per-URL aggregation: all evidence points for a given URL across ALL tests, grouped together
- Color-coded by test status: green (passed), yellow (partial_pass/fallback), red (failed)
- Circle size proportional to test count (coverage validation)
- Tooltip shows locator, element info, and test results
- Filterable by test status: "All", "Passed", "Partial", "Failed" buttons
- Element details table below heatmap with position, element, locator, and per-status counts
- Legend shows status colors and circle size meaning
- `tests/test_heatmap_utils.py` — 8 tests (2 original + 6 new for Tier 3 features)
- Behavior: Product owner sees "Look at all the elements we covered across the test suite — and here's which ones were hit by every test (possible data-input bias)."

**Files modified/created:**
- `src/failure_reporter.py` (new)
- `src/locator_scorer.py` (new)
- `src/evidence_tracker.py` (modified — fallback chain, status tracking)
- `src/evidence_report.py` (modified — suite heatmap redesign, failure_note rendering)
- `tests/test_failure_reporter.py` (new)
- `tests/test_locator_scorer.py` (new)
- `tests/test_heatmap_utils.py` (modified — 6 new tests)

---

## Feature Context — Evidence Tracker (AI-016 through AI-022)

The evidence tracker feature transforms test outputs from raw pass/fail results
into a fully traceable stakeholder artefact. The chain runs:

  Spec analysis → Tester review → Condition sign-off
  → Annotated screenshot evidence → Gantt timeline
  → Heat map → Evidence bundle export

This was designed to answer the question a tester needs to answer in a sprint
review: "here is what I tested, why I tested it, and proof that it passed."

Three new outputs are produced per test run:

1. `.evidence.json` sidecar — structured interaction record with bounding boxes
2. Annotated screenshot — page screenshot with numbered interaction circles
3. Evidence bundle — per-story document combining all three sources (AI, manual,
   automation) with Gantt timeline and sign-off section

---

### ✅ AI-016 — Spec Analysis Stage (COMPLETE)

**What:** A new pipeline stage that runs before test generation. Reads the
user's input (spec, user story, or acceptance criteria), extracts business rules,
maps boundary values, surfaces assumptions and ambiguities, and derives explicit
test conditions. Produces a structured list of conditions the tester must review
and confirm before generation begins.

**Why:** Documents like functional specs (e.g. Appius baggage calculator format)
contain business rules in prose, not acceptance criteria bullets. The boundary
values, assumptions, and ambiguities must be derived by analysis, not just parsed.
A tester who has confirmed ten conditions has a very different accountability
position than one who ran a tool.

**New file:** `src/spec_analyzer.py`
**New file:** `tests/test_spec_analyzer.py`
**Touches:** `streamlit_app.py` — new stage before "Generate Tests" button
**Touches:** `src/prompt_utils.py` — system prompt updated to receive derived
conditions rather than raw acceptance criteria text

**Design session completed:** 2026-04-04
**Spec:** See docs/PROJECT_KNOWLEDGE.md — Spec Analysis Stage section

**Condition types derived:**
- `happy_path` — valid input within all rules
- `boundary` — value at exactly the rule limit (and ±1 unit either side)
- `negative` — invalid input, error path
- `exploratory` — tester-added, not derivable from spec alone
- `regression` — parameterised automation, cross-boundary combinations
- `ambiguity` — spec gap requiring product owner clarification before sign-off

**Priority:** High — prerequisite for AI-017 and AI-018

---

### ✅ AI-017 — Living Test Plan UI (COMPLETE)

**What:** After spec analysis, the tester sees a full editable test plan showing
all derived conditions. They can edit any condition's text, expected result, or
source reference. They can remove conditions they consider out of scope. They can
add manual tests (with step lists) and automation tests (with locator intent).
They can flag conditions that need product owner clarification. Only when all
conditions are confirmed does the sign-off button unlock, triggering generation.

**Why:** The tester must be the author of the test plan. AI-derived conditions
are a starting point, not a final product. The edit, remove, and add capabilities
make the tester's judgement visible and documented, not invisible.

**New file:** None — UI only, lives in `streamlit_app.py` as a new display
function `display_test_plan()`
**Note:** All testable helpers must be extracted to `src/` per AGENTS.md §3.
Any filtering, sorting, or condition-manipulation logic goes in
`src/test_plan.py`, not directly in `streamlit_app.py`.

**New file:** `src/test_plan.py` — TestPlan dataclass, condition CRUD, flag logic
**New file:** `tests/test_test_plan.py`

**Session state keys added:**
- `test_plan` — list of TestCondition objects (see docs/PROJECT_KNOWLEDGE.md)
- `plan_confirmed` — bool, True when all conditions checked off

**Priority:** High — depends on AI-016

---

### ✅ AI-018 — Evidence Tracker Module (COMPLETE)

**What:** `src/evidence_tracker.py` — wraps Playwright Page interactions to
record element bounding boxes, interaction types, step sequence, and run history.
Writes a `.evidence.json` sidecar file alongside screenshots after each test run.
Accumulates run counts across multiple runs without overwriting history.

**Why:** The annotated screenshot overlay (AI-020) and the Gantt timeline
(AI-021) both read from the sidecar. Without structured interaction data, the
overlay cannot know where to draw circles or how large to make them.

**New file:** `src/evidence_tracker.py`
**New file:** `tests/test_evidence_tracker.py`
**New file:** `generated_tests/conftest.py` — pytest fixture wiring tracker
into every generated test automatically

**Key design decisions (do not change without design session):**

- Tracker wraps the Page object, it does not patch it. Existing tests continue
  to work unchanged.
- Coordinates stored as both absolute pixels (`bbox`) AND viewport percentage
  (`viewport_pct`). The overlay renderer uses percentages so it is
  resolution-independent.
- `run_count` is per-step, not per-test. Elements exercised by multiple test
  paths accumulate independently.
- `write()` is called in pytest teardown via the conftest fixture, not inside
  the test function. This ensures sidecar is written even when a test fails.
- `pytest_runtest_makereport` hook in conftest makes pass/fail status available
  to the teardown fixture.

**Sidecar schema version:** `1.0` (see docs/PROJECT_KNOWLEDGE.md for full schema)

**Priority:** High — blocks AI-019, AI-020, AI-021

---

### ~~AI-019 — Prompt Update: EvidenceTracker Methods~~ (SUPERSEDED — skeleton-first + postprocessor)

**What:** Update `src/prompt_utils.py` to add a new rule block
`_EVIDENCE_TRACKER_RULES` instructing the LLM to use `evidence_tracker.*`
wrapper methods instead of `page.*` directly. Add the `@pytest.mark.evidence`
decorator to the generated test template. Update
`get_streamlit_system_prompt_template()` to include the new rule block.

**Why:** If the LLM generates `page.goto()` instead of
`evidence_tracker.navigate()`, no sidecar is produced and the annotated
screenshot feature produces nothing. The rule must be in the system prompt,
not just documentation.

**Touches:** `src/prompt_utils.py` only
**New constant:** `_EVIDENCE_TRACKER_RULES`

**Six mandatory rules for the LLM (see docs/PROJECT_KNOWLEDGE.md for full text):**
1. Use `evidence_tracker.navigate()` not `page.goto()`
2. Use `evidence_tracker.fill()` not `page.locator().fill()`
3. Use `evidence_tracker.click()` not `page.locator().click()`
4. Use `evidence_tracker.assert_visible()` not `expect().to_be_visible()`
5. Always add `@pytest.mark.evidence(condition_ref=..., story_ref=...)`
6. Never call `page.screenshot()` directly

**Note:** `src/llm_client.py` is PROTECTED — do not modify it.
The rule block goes in `prompt_utils.py` and is injected via the existing
template system.

**Priority:** High — depends on AI-018, blocks usable generated tests

---

### ✅ AI-020 — Annotated Screenshot Evidence View (COMPLETE)

**What:** Extend `src/report_utils.py` to read `.evidence.json` sidecars when
building the HTML evidence bundle. Render an SVG overlay on top of each
screenshot showing: numbered circles at interaction coordinates, circle size
encoding cumulative run count, colour encoding interaction type
(navigate/fill/click/assertion), sequence numbers in execution order.

**Three view modes:**
- `annotated` — numbered circles with type colours (default, for product owner)
- `heatmap` — density rings showing interaction frequency across all runs
  (for QA lead)
- `clean` — raw screenshot with no overlay (baseline for comparison)

**Hover interaction:** Hovering a circle highlights the corresponding step in
the step timeline below the screenshot. Hovering a timeline row highlights the
circle on the screenshot.

**Why:** A screenshot is a frozen moment. An annotated screenshot is a test map
a product owner can read without understanding any code.

**Colour encoding (do not change without updating legend):**
- Navigate: `#993556` (pink-red)
- Fill: `#0F6E56` (teal)
- Click: `#185FA5` (blue)
- Assertion: `#854F0B` (amber)

**Circle size formula:** `base_radius = 14 + min(run_count * 0.7, 20)`

**Coordinate rendering:** Uses `viewport_pct` not absolute `bbox` pixels.
Multiply by container dimensions at render time.

**Touches:** `src/report_utils.py` — new function `generate_annotated_screenshot()`
**Touches:** `streamlit_app.py` — evidence bundle tab shows annotated screenshots

**Priority:** Medium — depends on AI-018

---

### ✅ AI-021 — Gantt Timeline in Evidence Bundle (COMPLETE)

**What:** A per-story, per-sprint test execution timeline showing each condition
as a horizontal bar sized by duration. Bars labelled with the condition ref
(BC01.02) and plain-English description, not the test function name. Dashed bars
for conditions not yet run (pending/open question). Colour encodes status.

**Three grouping modes:**
- By condition type (tester view)
- By sprint (scrum master view)
- By source — AI/manual/automation (product owner view)

**Stakeholder summary row** below the chart: fastest test, slowest test,
automation coverage percentage as plain English sentences.

**Clicking a bar** expands a detail card showing the spec reference, expected
result, evidence note, and step sequence. The card sits below the chart, not
as a modal overlay.

**Why:** Duration differences between tests are meaningful — a boundary rejection
taking 4× longer than a happy path is a conversation starter with developers. The
Gantt makes this visible without the tester having to articulate it.

**New file:** `src/gantt_utils.py` — data preparation, grouping logic
**New file:** `tests/test_gantt_utils.py`
**Touches:** `streamlit_app.py` — new tab in evidence bundle section
**Reads from:** `.evidence.json` sidecar `test.duration_s` and `test.status`

**Priority:** Medium — depends on AI-018

---

### ✅ AI-022 — Coverage Heat Map (COMPLETE)

**What:** A cross-story, cross-sprint grid showing coverage confidence for each
story × condition type combination (or story × sprint, or story × source,
switchable). Each cell coloured by confidence level. Clicking a cell expands
condition detail. Sprint-over-sprint trend bars below the grid.

**Four confidence levels (colours are fixed — do not change):**
- Tester confirmed: `#1D9E75` (dark teal) — tests passed AND tester signed off
- AI covered, unreviewed: `#9FE1CB` (light teal) — tests passed, no tester review
- Partial / pending: `#FAC775` (amber) — some conditions still pending
- Gap / open question: `#F09595` (red) — ambiguity or missing coverage
- Not in scope: `var(--color-background-secondary)` — deliberate exclusion

**The tonal distinction between confirmed and unreviewed is the most important
design decision in the heat map.** Both mean tests passed. Only confirmed means
a human reviewed the conditions and agreed they are the right tests. This is
the visual answer to the question "how much of this did a human actually verify."

**Persistence:** Heat map data aggregated from all `.evidence.json` sidecars in
the evidence directory, plus manual test plan records from session state. No
external database — local file aggregation only.

**New file:** `src/heatmap_utils.py` — aggregation across sidecars
**New file:** `tests/test_heatmap_utils.py`
**Touches:** `streamlit_app.py` — new top-level analytics tab

**Priority:** Medium — depends on AI-016, AI-018, AI-021

---

## Implementation Sequence (AI-016 through AI-022)

Do these in order. Each item is a single Cline session.

| Order | ID | Session scope |
|-------|----|---------------|
| 1 | AI-018 | `src/evidence_tracker.py` + tests + conftest only |
| 2 | AI-019 | `src/prompt_utils.py` rule block only |
| 3 | AI-016 | `src/spec_analyzer.py` + tests — no UI yet |
| 4 | AI-017 | `src/test_plan.py` + tests + `display_test_plan()` in UI |
| 5 | AI-020 | `generate_annotated_screenshot()` in report_utils + UI tab |
| 6 | AI-021 | `src/gantt_utils.py` + tests + UI tab |
| 7 | AI-022 | `src/heatmap_utils.py` + tests + UI tab |

**Rule:** Each session must end with `bash fix.sh` → `pytest tests/ -v` → green
before committing. Do not combine sessions.

---

### ✅ AI-002 — User Story Parser Module (COMPLETE)
**What:** Move criteria extraction into `src/user_story_parser.py` with proper
format support: Gherkin, Jira AC bullets, numbered, free-form
**Status:** Complete — Session 11 (2026-03-29)

### ✅ AI-005 — Move coverage helpers to `src/coverage_utils.py` (COMPLETE)
**What:** Extract remaining coverage helpers out of `streamlit_app.py`
**Status:** Complete — Session 13/April 2026. All display-mapping logic moved explicitly to `src/coverage_utils.py` and stubs fixed.

### ✅ AI-004 — Phase C Run Now gaps (COMPLETE)
**What:** Three gaps in the Run Now workflow:
1. Environment URL dropdown (staging / prod / local) — added to Streamlit sidebar
2. Re-run failed tests only — already implemented
3. Screenshot viewer inline after run — added inline evidence viewer in `src/ui/ui_run_results.py`
**Priority:** Medium

### AI-006 — Test fixture library
**What:** `tests/fixtures/user_stories/` with 10-15 examples in each format
**Why:** Parser regression suite
**Priority:** Medium

### AI-007 — Remove `_generate_test_content()` from CLI orchestrator
**What:** CLI orchestrator has its own generation function duplicating
`src/test_generator.py` logic
**Priority:** Low

---

## 🌟 Future Enhancements

> Note: Each of these needs a detailed design session before handing to Cline.
> They are listed here to capture intent — not ready for implementation yet.

### ✅ AI-023 — Interactive Locator Repair Loop (COMPLETE)
**What:** When a generated test fails with a locator error (TimeoutError or strict
mode violation), the tool offers an interactive repair mode. A headed browser opens
at exactly the page where the test got stuck. The tester clicks the element they
want. The tool captures the locator Playwright reports for that click and patches
it directly into the test file. The tester then re-runs to verify.

**Why:** This closes the loop between "test generated" and "test working." Currently
locator failures require the tester to debug the DOM manually and edit the file
themselves — work the tool should handle. This feature maps directly to what an
automation tester would do: open the page, find the element, copy the locator.

**Implementation:**
- `src/failure_classifier.py` — classify pytest failure type from error message
- `tests/test_failure_classifier.py`
- `src/locator_repair.py` — patch locator in test file + codegen browser session
- `tests/test_locator_repair.py`
- `src/ui/ui_run_results.py` — repair panel, repair buttons on locator failures, browser session state


**Implementation sequence (4 Cline sessions, strict order):**
1. `src/failure_classifier.py` + tests
2. `src/locator_repair.py` patch logic + tests (no browser)
3. `streamlit_app.py` UI — repair button and state transitions (no browser)

**Constraints:**
- Locator failures only — assertion failures get explanation note, no repair button
- Streamlit UI only — not available in CI or headless runs
- One locator repair per invocation — not batch
- Never guesses a replacement — only records what the tester clicks

### ✅ AI-024 — Accessibility Tree Enrichment (COMPLETE — 2026-05-17)
**Implemented:** `src/accessibility_enricher.py`, `tests/test_accessibility_enricher.py`, CDP snapshot in `src/scraper.py` (+ journey/stateful scrapers per B-0XX).
**Spec:** `docs/specs/FEATURE_SPEC_AI024_accessibility_tree_enrichment.md`

### AI-025 — Visual Regression Detection (Planning Required)
**What:** Post-run screenshot comparison against baselines...

### ✅ AI-010 — Page Object Model Generation Mode (COMPLETE — 2026-06-30)
**What:** POM toggle in both Streamlit UI and CLI — generates `class HomePage:` etc. with locators and interaction methods, tests import from `pages/`.

**Implementation vs original spec:**
- ✅ UI toggle — `st.sidebar.toggle("Page Object Model (POM)")` in `src/ui/ui_sidebar.py`
- ✅ CLI toggle — "POM Mode" menu item in `src/cli/main.py`
- ✅ One class per scraped page URL — `src/page_object_builder.py` (292 lines)
- ✅ Evidence-aware POM methods — delegates to `EvidenceTracker` not raw `page.locator()`
- ✅ `ExportMode.POM` / `ExportMode.FLAT` — `src/export_service.py`, `src/pipeline_models.py`
- ✅ POM injection phase — `src/placeholder_orchestrator.py`, `src/orchestrator.py`
- ✅ Separate files in `generated_tests/pages/`
- ✅ 1400+ tests across 8 test files
- ✅ UAT validated — saucedemo: 6 POM classes (HomePage, InventoryPage, CartPage, CheckoutStepOnePage, CheckoutStepTwoPage, CheckoutCompletePage)

---

### ✅ AI-011 — Test Run History Chart (COMPLETE — 2026-07-01)
**What:** A pass/fail trend chart showing test results over time.

**Why it matters:** A single run result tells you pass/fail now. A history chart
tells you whether things are getting better or worse, and when a regression was
introduced.

**Implementation:** 
- Uses existing `src/run_history_chart.py` which aggregates from SQLite database
- Added to `streamlit_app.py` as "📊 Test Run History" section after Evidence Viewer
- Uses `st.plotly_chart` for interactive visualization
- All run results persisted to `evidence/run_results.sqlite` via `src/run_result_persistence.py`
- Modified `src/ui/shared.py` to automatically persist runs
**Priority:** Medium

---

### AI-012 — Selector Confidence Scores
**What:** Score each locator the scraper found by how likely it is to break,
and surface that score in the UI alongside the generated test.

**Why it matters:** Not all selectors are equally reliable. A test built on
`data-testid` attributes will survive UI redesigns. A test built on button
visible text will break the moment someone rewrites the copy. Users should
know which parts of their generated test are fragile before they find out
the hard way in CI.

**How scoring works — based on locator type, not usage frequency:**

| Locator type | Confidence | Reason |
|---|---|---|
| `data-testid` | High | Explicitly added for testing — won't change accidentally |
| `id` attribute | Medium-High | Stable but sometimes auto-generated |
| `name` attribute | Medium | Reliable for forms |
| `aria-label` / role | Medium | Good but changes with UI copy |
| `visible_text` | Low | Breaks when button label changes |
| Bare tag (`input`) | Very Low | Almost always fragile |

The scraper already builds `recommended_locator` for every element — scoring
is a classification step on top of what already exists.

**What the UI shows:** A confidence indicator per test function, and a summary
panel showing how many locators in the generated test are high/medium/low
confidence. Flags tests that are likely to be brittle before they're even run.

**Design session needed:** Yes — scoring thresholds, UI presentation, whether
low-confidence selectors should trigger a warning at generation time
**Priority:** Medium

---

### AI-013 — Coverage Gap Report with Gap Explanations
**What:** A report showing which acceptance criteria have no linked test, with
an explanation of why the gap exists.

**Why it matters:** Knowing a gap exists is useful. Knowing *why* it exists
tells the user what to fix — is it the user story, the scraper, or the LLM?

**Gap explanations the tool can provide:**

| Gap reason | How detected | What user should do |
|---|---|---|
| No matching elements found on page | Scraper found nothing relevant to this criterion | Add the page to the URL list or check the page loads correctly |
| Criterion too ambiguous | No specific keywords the LLM could act on | Rewrite the criterion to be more specific |
| Page not scraped | Relevant page wasn't in the URL list | Add the URL to the additional pages list |
| LLM skipped this criterion | Criterion in the list but no test function references it | Re-run with Always LLM mode or rewrite the criterion |

**Design session needed:** Yes — how to detect each gap type reliably, how to
present the report in the UI, whether this replaces or extends the current
coverage tab
**Priority:** Medium

---

### AI-014 — Test Execution Time Gantt Chart
**What:** A Gantt-style chart showing each test as a horizontal bar, sized by
execution time, so users can understand total suite duration and identify slow tests.

**Why it matters:** QA leads need to know how long a full regression run takes.
If it takes 45 minutes, that affects how often it can run in CI. Identifying
the slowest tests lets users decide which ones to optimise or run separately.

**How it would work:**
- `pytest_output_parser.py` currently stores duration as `0.0` — individual
  test times are in the pytest output but not yet parsed
- Parsing them is a small regex addition to the parser
- The Gantt chart stacks tests horizontally, total width = total suite time
- Colour coded by status (green = passed, red = failed)
- Clicking a bar could expand the error message for failed tests

**Design session needed:** Yes — parsing individual test durations from pytest
output, chart library choice, whether this lives in the run results tab or a
separate analytics tab
**Priority:** Low-Medium

---

### AI-015 — Test Coverage Heat Map
**What:** A visual grid showing which parts of the application have been tested
and how thoroughly, colour coded from red (untested) to green (fully covered).

**Why it matters:** At a glance a QA lead can see where the coverage gaps are
across the whole application — not just for one user story but across all
generated tests. A standard tool in mature QA workflows.

**How it would work:**
- Each cell in the grid represents a page or feature area
- Colour is determined by: number of tests covering that area, confidence
  scores of those tests, pass/fail rate from run history
- Requires run history (AI-011) and selector confidence (AI-012) to be
  meaningful — depends on those features
- Would live in a dedicated "Coverage" or "Analytics" tab

**Design session needed:** Yes — this is the most complex visualisation on
the list. Depends on AI-011 and AI-012 being in place first.
**Priority:** Low — long term goal, needs other features as prerequisites

---

### Cloud LLM Providers
**Goal:** Support OpenRouter, OpenAI, Anthropic alongside Ollama
**Spec:** `LLM_PROVIDER` env var, provider-specific API keys in sidebar, fallback to Ollama
**Status:** Complete — Added multi-provider LLM support architecture.

### n8n Integration
**Goal:** Trigger generation from Jira webhooks, report to Slack
**Status:** Low priority — Phase 4+

---

## 📋 Fix Log

### Session 3 (2026-03-06)
- B-001, B-002, B-003, B-005 closed
- Phase A (auto-save), B (coverage), C (run now core) complete

### Session 4 (2026-03-07)
- AI-001 (page context scraper) complete
- Coverage number-based matching fixed
- Run output persistence fixed
- Jira report download added
- `pytest.ini` — removed `generated_tests` from testpaths

### Session 5 (2026-03-10)
- R-003 complete — `src/report_utils.py` extracted and tested

### Session 8 (2026-03-13)
- R-001 through R-006 complete
- Cline loop recovery applied
- load_dotenv fix, URL normalisation, content persistence, download crash fixed

### Session 9 (2026-03-16)
- BREAK-1 identified — `src/pytest_output_parser.py` missing (CI blocker)
- BREAK-2 identified — session state wipe in `display_run_button()`
- B-006 identified — parser banner wrong on mixed pass/fail
- B-007 identified — error panels duplicated
- B-008 identified — Run Status column never populates
- AI-009 (multi-page scraping) added as critical priority
- `docs/FEATURE_SPEC_multi_page_scraping.md` created

### Session 10 (2026-03-21)
- B-007 fixed — removed duplicate error rendering from `display_coverage()`
- B-006 verified working, 2 regression tests added to `test_pytest_output_parser.py`
- AI-003 closed — `OLLAMA_TIMEOUT=300` added to `.env.example`
- AI-009 Phase A complete — multi-page scraper wired into `streamlit_app.py`
- 121 tests passing, ruff clean, mypy clean

### Session 11 (2026-03-29)
- AI-002 complete — `src/user_story_parser.py`, 23 tests, 100% pass rate
- B-009 fixed — `src/code_validator.py` created, integrated into `file_utils.py`
- AI-003 confirmed complete
- AI-009 Phase B spec written — `docs/FEATURE_SPEC_AI009_phase_b.md`
- BACKLOG.md updated — AI-010 through AI-015 added
- LEARNING_PLAN.md created
- docs/PROJECT_KNOWLEDGE.md refreshed

### Session 12 (2026-03-31)
- Streamlit input mode persistence fixed: "Paste story" selection now survives reruns and login-toggle changes.
- Requirement model consistency improved for no-AC inputs: parsing, criteria count, coverage, and reports now use one derived model.
- Report semantics corrected: pre-run states remain pending/unknown and are no longer counted as failed.
- Run output UX cleaned: noisy/duplicate pytest lines reduced and misleading pytest-cov module coverage removed from UI run flow.
- Prompt/context hardening for generated selectors and URLs: stronger use of scraped locators and context URLs with stricter generation guidance.
- Generation guardrails expanded in `src/code_validator.py` for known flaky SauceDemo patterns:
  - invalid `/checkout.html`
  - invalid checkout title assertions
  - brittle exact base URL assertions pre-login
  - weak negative-only checkout URL assertions
- Multi-page restart-from-base scraping improved:
  - captured page now accepted only when URL matches the requested target
  - mismatch now retries (bounded) and surfaces explicit failure details.
- Credential profile active-selection regressions fixed in Streamlit state handling.

### Session 13 (2026-03-31)
- AI-005 complete: moved remaining coverage display-mapping logic from `streamlit_app.py` into `src/coverage_utils.py` with typed helpers and tests.
- B-008 effectively addressed: Coverage x Run Results now maps run outcomes through shared coverage utilities and no longer defaults to pending when matches exist.
- AI-004 (Phase C) progress: added "Re-run Failed Only" in the Run Now flow.
  - Failed test nodeids are extracted from prior run results and executed directly via pytest.
  - Command construction extracted to `src/run_utils.py` with unit tests.
- Multi-page scraper failure tracking improved to typed structured failures (`failed_pages`) with backward compatibility for legacy `failed_urls` consumers.
- Runtime logic further generalized to site-agnostic behavior (removed site-specific validator/prompt/scraper assumptions).

### April 2026 Updates (Sessions 14+)
- Add anchor link extraction to page context scraper (2026-04-04).
- Add multi-provider LLM support, fix coverage_utils stub, clean up Cline artefacts (2026-04-05).
- Remove Cline scratch files, tighten gitignore for tmp files and PNGs (2026-04-05).
- Refactor: implement pipeline architecture and update dependencies (2026-04-08).
- Utils fix and pip to uv migrations resolved (2026-04-10).
- Stabilized AI test generation pipeline: fixed POM method mismatches, resolved placeholder syntax errors, and implemented structural safety nets (2026-04-19).

### B-015 Fix — dismiss_consent_overlays Rewrite (2026-06-23)
**What:** Rewrote `dismiss_consent_overlays()` in `src/browser_utils.py` to fix B-015
(journey discovery selecting wrong elements due to aggressive consent banner dismissal).

**Root cause:** Old implementation used global text matching (`button:has-text('Continue')`)
that matched `#continue-shopping` on saucedemo's cart page. Called before every click
step, this navigated cart.html → inventory.html, preventing checkout pages from being
scraped. This caused a cascade: wrong click → wrong page → missing scrape → zero
resolution for all checkout FILL fields.

**Fix:** 3-stage replacement:
1. Google Consent TVM — specific `.fc-consent-root` selectors (unchanged)
2. Structural containers — known consent provider classes (`oneTrust`, `cookie-banner`,
   `[role='dialog']`, etc.) — buttons only matched **inside** these containers
3. Position-based detection — JS finds fixed/sticky overlays near bottom of viewport,
   then looks for dismiss buttons inside them
4. Ad overlay removal — specific selectors only (Google Vignette, ASWIFT)

**Removed:** Global text matching, `zIndex > 10000` DOM removal, `allElements` DOM iteration.

**Verification:** saucedemo UAT after fix:
- `#checkout` selected (score=12) for "checkout button" on cart.html ✅
- All checkout pages scraped (`checkout-step-one.html`, `checkout-step-two.html`, `checkout-complete.html`) ✅
- `test_06_complete_checkout` reduced from 8+ skips to 1 skip (ASSERT — B-014) ✅
- 1266 tests pass, 0 regressions ✅
- 10 new unit tests in `tests/test_browser_utils.py` ✅

**Files changed:**
- `src/browser_utils.py` — complete rewrite
- `tests/test_browser_utils.py` — new test file (10 tests)

### Saucedemo UAT Investigation (2026-06-22)
**What:** Full pipeline run against saucedemo.com using `scripts/uat/uat_automationexercise.py --site saucedemo` to validate placeholder resolution findings.

**Key findings:**
1. **B-015 CONFIRMED** — Journey discovery clicks wrong elements:
   - "checkout button" → `#react-burger-menu-btn` (burger menu, score=1)
   - "first name:John" → `<select>` element (not fillable)
   - "zip/postal code:12345" → `<a>` link (not fillable)
   - This prevents checkout pages from ever being scraped

2. **B-014 CONFIRMED** — ASSERT resolves to wrong elements:
   - "product inventory page" → `#login-button`
   - "cart badge shows 1" → `.shopping_cart_link` (cart nav link)
   - "sauce labs backpack in cart" → `#remove-sauce-labs-backpack`
   - Every ASSERT resolves to something, but never the right element

3. **B-017 CORRECTED** — FILL on login works (masked by prerequisite injection):
   - `#user-name`, `#password`, `#login-button` all resolve correctly in final code
   - Resolver logs say `Failed to find` but prerequisite injection provides selectors
   - Checkout FILL fails because checkout pages were never scraped (B-015 consequence)

4. **B-018 CORRECTED** — The resolver gap is real but secondary:
   - Resolver fails on login elements but prerequisite injection masks it
   - The primary failure mode is B-015 (journey wrong clicks → missing pages)

**Cascade chain:** B-015 (journey clicks wrong) → checkout pages not scraped → B-017 (checkout FILL fails) → test_06 pytest.skip()

**No code changes** — investigation only, backlog items corrected to reflect actual root causes.

### Mypy Stubs Fix (2026-04-21)
**What:** Resolved 11 mypy `import-untyped` and type compatibility errors across 4 files.

**Fixes:**
- Installed `pandas-stubs` via `uv add --dev pandas-stubs` — resolves 6 import errors in `gantt_utils.py` and `heatmap_utils.py`
- Added per-module `ignore_missing_imports = true` for `plotly.*` in `pyproject.toml` — resolves 3 import errors (plotly has no official stubs)
- Fixed `src/scraper.py:164` — extracted `tag.get("class")` to walrus operator to resolve type narrowing issue
- Fixed `streamlit_app.py:743` — added `# type: ignore[arg-type]` for `grouping_mode` Literal mismatch (st.selectbox returns str, values are correct at runtime)

**New dev dependency:** `pandas-stubs>=3.0.0.260204` in `pyproject.toml`

### April 2026 — Evidence Tracker Feature Chain (Sessions 17-20)
**What:** Delivered all seven items (AI-016 through AI-022) plus Tier 2 locator scoring and Tier 3 heatmap redesign.

**Deliverables:**
- Tier 1: `src/failure_reporter.py`, `src/evidence_tracker.py` failure_note capture, `src/evidence_report.py` failure rendering
- Tier 2: `src/locator_scorer.py`, fallback chain in evidence_tracker, partial_pass status
- Tier 3: Redesigned `generate_suite_heatmap()` — per-URL aggregation, status overlay, locator info, filter buttons
- Tests: `tests/test_failure_reporter.py` (10 tests), `tests/test_locator_scorer.py` (10 tests), `tests/test_heatmap_utils.py` (8 tests, 6 new)

**All checks passed:** ruff clean, mypy clean, pytest green.

### Session (2026-05-08) — Global Best Resolution Fix
**What:** Placeholder resolution in `src/placeholder_orchestrator.py` was returning the first
per-page match instead of the global best match across all scraped pages. On multi-page sites
like saucedemo.com, this caused login page elements (e.g., `#user-name`, `#password`,
`#login-button`) to be skipped entirely because a low-quality match existed on an earlier page
in dict iteration order (e.g., cart page).

**Root Cause:** `_find_best_element_for_current_page()` iterated through pages sequentially and
returned the first match found per-page, never reaching pages with better matches.

**Fix:** Changed the method to collect ALL ranked candidates from ALL pages into a single list,
sort by score descending, then select the global best match. Threshold-based shortlisting and
semantic ranking operate on the global ranking.

**Files Modified:**
- `src/placeholder_orchestrator.py` — `_find_best_element_for_current_page()` now collects
  candidates globally before selecting the best match
- `tests/test_global_best_resolution.py` — 5 new regression tests covering cross-page resolution,
  password field, login button, checkout button, and no-match scenarios

**Quality Checks:** ruff clean, mypy clean, 45 placeholder-related tests pass.

**Impact:** Fixes all placeholder resolution failures on saucedemo.com and similar multi-page
sites where elements on the login page were being skipped because cart/checkout pages appeared
first in the scraped data dict.

---

### Session 22 (2026-05-01) — CLI entry point cleanup
**What:** Clarified supported CLI ownership after the argparse CLI module superseded
the original root `main.py` menu flow.

**Fix:**
- Root `main.py` is now a deprecated compatibility wrapper that forwards to `cli.main`.
- `AGENTS.md`, `docs/PROJECT_KNOWLEDGE.md`, `README.md`, and `docs/ARCHITECTURE.md`
  now identify `cli/main.py` as the supported CLI entry point.
- Removed stale protection guidance that treated root `main.py` as the active CLI.

**Why:** Avoids two competing terminal workflows and keeps CLI fixes focused on
`cli/main.py`, which is what `launch_cli.sh` runs.


### Session 21 (2026-04-26) — conftest path fix + Tier 1/2 verification
**What:** Generated test evidence sidecars were being written to the wrong directory.
The conftest fixture used `Path(__file__).parent` (conftest location) instead of the
test file's own directory, so evidence from `generated_tests/test_x/` tests was written
to `generated_tests/evidence/` instead of `generated_tests/test_x/evidence/`.

**Fix:** Changed `_get_evidence_refs()` to use `request.fspath` (path to the test file
being executed) and derive `test_package_dir = Path(request.fspath).parent`.

**Verification:** Ran `test_02_go_to_cart` — evidence sidecar correctly written to
`generated_tests/test_20260426_164944_as_a_customer_i_want_to_add_items_to_cart/evidence/test_02_go_to_cart[chromium].evidence.json` (13 KB, contains full failure evidence).

**Tier 1 evidence verified:** The sidecar contains:
- `test.status` = "failed"
- `page.url` = "https://automationexercise.com/view_cart"
- `steps[3].result.failure_note` = human-readable diagnosis with suggested locators
- `steps[3].result.diagnosis.available_elements` = 19 elements found at failure time
- `steps[3].result.diagnosis.suggested_locators` = 15 scored alternatives
- Screenshot captured at failure point

**Tier 2 verified (already complete):** Locator scoring + controlled fallback was
already fully implemented during Session 20. Confirmed working:
- `src/locator_scorer.py` — `LocatorScorer.score_locator()`, `score_candidates()`,
  `get_fallback_candidates()` with 9 locator types scored 0-100
- `src/evidence_tracker.py` — `_try_locator_fallback()` builds DOM candidates,
  scores them, tries up to 2 higher-scoring alternatives, logs full chain
- `partial_pass` status set when fallback succeeds
- Full fallback chain in evidence: locator, type, score, confidence, result, error
- 39 tests pass (15 locator_scorer + 11 evidence_tracker + 13 other evidence)

**Pre-existing bug discovered:** `test_generate_annotated_journey_cleans_placeholder_labels`
fails with `label: "<built-in method title of str object at 0x...>: view cart link"`.
The `clean_placeholder_labels()` function in `evidence_report.py` is calling `.title()`
on a method reference instead of the string value. NOT related to the conftest fix.
Requires separate investigation.

**Test results:** 455/456 tool tests pass. 1 pre-existing failure unrelated to this fix.

---

## Historical Issues (from ISSUES_FOUND_AND_FIXES.md — merged 2026-04-21)

> **Architecture note:** Issues 3 and 4 below were fixed in the pre-session-2 codebase
> and reflect the original standalone async format. The project architecture was
> subsequently decided (2026-03-03) to use **pytest sync format** exclusively.
> Any references to async/await tests or "no pytest" as a fix are superseded.
> See docs/PROJECT_KNOWLEDGE.md — Architecture Decisions for the current standard.

### Session 1-2 Issues (2026-03-01 to 2026-03-04)

#### 1. GitHub Actions CI/CD Pipeline ⚠️
**Problem:** CI/CD badge not properly configured for renamed project.
**Fix:** Updated badge URL to reflect renamed repository.
**Impact:** CI/CD status badge now displays correctly.

#### 2. Path Calculation Problem ⚠️
**Problem:** Paths calculated incorrectly when running from different directories.
**Fix:** Changed to `Path.cwd()` for consistent path resolution.
**Impact:** Script runs correctly from any directory.

#### 4. LLM Prompt Structure ⚠️
**Problem:** Prompt too verbose, used XML tags LLM didn't respect.
**Fix:** Restructured with clear numbered requirements and explicit DO NOT instructions.
**Impact:** More consistent LLM output.

#### 6. CLI Output Formatting ⚠️
**Problem:** CLI output minimal with no visual hierarchy.
**Fix:** Added separator lines, emoji icons, clearer option menus.
**Impact:** Improved developer UX.

#### 7. CLI Module Architecture 🆕
**Problem:** No proper CLI interface with argument parsing.
**Fix:** Implemented complete CLI module with argparse, subcommands, config enums,
modular components (InputParser, UserStoryAnalyzer, TestCaseOrchestrator, etc.)
**Impact:** Tool supports both interactive and programmatic/CI usage.

#### 12. Pre-commit Configuration 🆕
**Problem:** No `.pre-commit-config.yaml` — no automated quality checks before commits.
**Fix:** Created `.pre-commit-config.yaml` with ruff linting and ruff-format.
**Impact:** Automated code quality checks run before every commit.

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-01 | Initial release with interactive CLI |
| 1.1.0 | 2026-03-03 | CLI overhaul with argparse, report generation, multi-format support |
| 1.2.0 | 2026-03-04 | Pre-commit configuration with ruff, automated code quality checks |
| 1.3.0 | 2026-03-06 | Streamlit UI, Phase A/B/C (save/coverage/run), B-001/002/003/005 fixed |
| 1.4.0 | 2026-03-07 | Page context scraper (AI-001), coverage mapping fix, Jira download, git hygiene |
| 1.5.0 | 2026-03-21 | B-006/007 fixed, AI-003 closed, AI-009 Phase A complete (multi-page scraper UI) |
| 1.6.0 | 2026-04-10 | Pipeline architecture added, multi-provider LLM support, anchor link extraction, transitioned pip to uv |
| 1.7.0 | 2026-04-26 | Evidence Tracker Feature Chain complete (AI-016 through AI-022), Tier 2 locator scoring, Tier 3 heatmap redesign |

### Lessons Learned (from Gemini AI session)
- Always run ruff, mypy, pytest before accepting AI-generated code
- Review `git diff --staged --stat` before every commit
- Never let an AI commit directly without human review
- Give implementation AIs the full project rules, not just the spec doc
- One feature per AI session — mixing tools mid-feature creates inconsistency

---

## 🐛 Test Generation Quality Fixes (May 2026)

> Root cause analysis from `generated_tests/test_20260502_123121_as_a_customer_i_want_to_browse_products_add_them/report_local.md`:
> 7 of 8 tests failed because the "Dress" link (`a[href="/category_products/1"]`) exists in DOM but is hidden behind a slider/menu. Test_02 also navigated to `/category_details/1` (404) instead of `/category_products/1`.

### Session 1 — LLM Disambiguation for Placeholder Resolution ✅ DONE (2026-05-13)

**Problem addressed:**
- Rule-based scoring in `PlaceholderResolver.rank_candidates()` produces near-ties (e.g., "Products link" resolves to brand product link instead of navigation link)
- Adding more scoring rules creates layering debt
- LLM understands context that rule-based scoring cannot encode

**Solution implemented:**
- `_disambiguate_with_llm()` method added to `PlaceholderResolver`
- Triggered when top-2 candidate scores differ by ≤ `DISAMBIGUATION_THRESHOLD` (default: 5)
- Sends up to 3 candidates to LLM with structured prompt (action, description, candidate details, optional Aria snapshot)
- Falls back to rule-based scoring when LLM unavailable or response unparsable
- Configuration via `USE_LLM_DISAMBIGUATION` (default: true) and `DISAMBIGUATION_THRESHOLD` (default: 5) env vars
- Aria snapshot context stored as `__meta__` element in `page_elements` (Option A)

**Files modified:**
- `src/placeholder_resolver.py` — `_disambiguate_with_llm()`, `_extract_aria_snapshot()`, `_filter_aria_snapshot()`, config params, integration in `find_best_element()`
- `tests/test_placeholder_resolver_disambiguation.py` — NEW — 17 tests (4 trigger, 6 LLM call, 2 scenario, 2 config, 3 integration)

**Quality gates:**
- `ruff check src/placeholder_resolver.py` — clean
- `mypy src/placeholder_resolver.py` — clean
- `pytest tests/test_placeholder_resolver_disambiguation.py -v` — 17/17 passed
- `pytest tests/ -x -q` — 610 passed (1 pre-existing failure in `test_vision_enricher.py` unrelated)

**Original tasks from Session 1 backlog (Visibility Filtering + Generic Selectors + URL Guessing):**
- Task 1A (visibility filtering): Partially addressed — text-content validation + confidence threshold already implemented
- Task 1B (ASSERT generic selectors): Addressed via LLM disambiguation — generic selectors are deprioritized when LLM picks specific elements
- Task 1C (URL guessing): Deferred to future session — out of scope for LLM disambiguation

**Expected outcome:** When rule-based scoring produces near-ties, the LLM makes the final decision with context — one targeted call replaces dozens of scoring rules.

---

### Session 2 — Visibility Capture in Scraper ✅ COMPLETE (2026-05-15)

**Problem:** Even with improved resolver scoring, we can't perfectly distinguish visible from hidden elements without runtime browser data. The scraper extracts elements from HTML via BeautifulSoup but has no visibility information.

**Solution implemented:**
1. `_capture_element_visibility()` in `src/scraper.py` — calls `page.locator(selector).is_visible()` for each element after networkidle
2. `is_visible` field added to all scraped element dicts (default `True` in `_extract_elements_from_html()`, overwritten with live DOM check)
3. `PlaceholderResolver.rank_candidates()` filters out `is_visible=False` candidates for CLICK/FILL actions; applies -40 score penalty for ASSERT actions

**Files modified:**
- `src/scraper.py` — `_capture_element_visibility()` method (lines 135-160), integrated into `_scrape_url_sync()`
- `src/placeholder_resolver.py` — visibility filtering in `rank_candidates()` (lines 560-581, 723-725), removed unused `score_penalty` variable
- `tests/test_scraper.py` — 4 new tests: default visibility, field presence, empty selector handling, element preservation

**Quality gates:** ruff clean, mypy clean, 651/651 tests pass

**Expected outcome:** Resolver never selects elements that are genuinely hidden at runtime.

---

### Session 3 — Skeleton Prompt: Specific Assertions (Priority: Lower)

**Problem:** Generated ASSERT placeholders are too generic (e.g., `ASSERT:button visible`) leading to assertions that match wrong elements even after resolution.

**Task:** Update the skeleton prompt to generate descriptive ASSERT placeholders.

**Approach:**
1. In `get_skeleton_prompt_template()`, add explicit guidance for ASSERT specificity:
   - "For ASSERT actions, describe WHAT element should be visible (e.g., 'ASSERT:product added confirmation message' not 'ASSERT:button visible')"
   - Show before/after examples of good vs bad ASSERT descriptions
2. In `rank_candidates()`, when resolving ASSERT placeholders, give bonus to elements where text content has high word-overlap with description

**Files to modify:**
- `src/prompt_utils.py` — add ASSERT specificity guidance
- `tests/test_prompt_utils.py` — verify prompt includes new guidance

**Expected outcome:** ASSERT placeholders carry enough context for the resolver to pick specific, meaningful elements instead of generic `.btn` matches.

---

## 🚀 CI/CD Tier 3 — Future Pipeline Enhancements

> Planned additions to the consolidated CI pipeline. Implement when the underlying features exist.

### CI-003 — SQLite Migration Validation
**When:** During AI-012 (SQLite Persistence) implementation
**What:** Add a static-analysis step that creates a fresh in-memory/temp SQLite database
and runs `PRAGMA integrity_check` against any DDL migrations. Catches schema syntax
errors before they hit `main`.
**How:** Small pytest fixture or standalone script that applies migrations to a temp DB
and asserts `integrity_check` returns `ok`.

### CI-004 — Graph-Store Compiler Check
**When:** When `nodes.csv`/`links.csv` are consumed by CI
**What:** After `project_sanitizer.py` audits links.csv, add an explicit SQLite query
assertion that compiles the graph-store and verifies no orphaned relational paths
exist in the static codebase mapping.
**How:** Extend sanitizer Step 3 to compile into an in-memory SQLite DB and run
`SELECT COUNT(*) FROM edges WHERE source_id NOT IN (SELECT id FROM nodes)` —
must return 0.

### CI-005 — Eval Harness Freeze Gate (Phase 5)
**When:** When Phase 5 multi-agent evaluation harness exists
**What:** Secondary `workflow_dispatch` workflow that runs evaluation metrics over
a dataset of generated test slices. Saves expensive token consumption on standard
commits while keeping a clean ledger of score regressions.
**How:** New `.github/workflows/eval-harness.yml` triggered manually. Produces
a markdown summary of pass-rate regressions vs the previous eval run.

### CI-006 — Performance Regression Gate
**When:** When test suite exceeds 5 minutes in CI
**What:** Track test suite duration over time and alert if a single commit adds
>30% to total runtime.
**How:** Store `pytest` summary duration in an artifact, compare against last
10 runs using `gh run view` JSON output.


