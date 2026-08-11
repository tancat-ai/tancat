# BACKLOG.md
## AI Playwright Test Generator

Last updated: 2026-08-07 (B-042 locator-repair indent fix + B-043 real run-history dropdown counts)

---

## ✅ Shipped 2026-08-06 — Run & Fix restructure, report fixes, self-heal fixes, evidence improvements

**Session highlights** — the app went from 2 pages to a 3-page workflow (Test Generator / Run & Fix / Evidence & Reports), and a cluster of run-results, report, and self-healing bugs were fixed. Full suite 2288 passed; ruff + mypy clean; eval static 95.2%.

**Page restructure:**
- **Run & Fix page** — results/repair/evidence/export moved out of Test Generator; empty-state with handoff; sidebar-loaded packages surface immediately (hydration).
- **Export panel** moved to Run & Fix; `build_report_bundle` now dir-aware (`saved_path` may be a package directory — reports were landing in `generated_tests/`).
- **Last-package auto-restore** (`SETTING_LAST_PACKAGE`) — the loaded suite survives page reloads / session resets instead of blanking to "No current suite loaded".
- **Package dropdown labels** — readable date/site/story instead of raw `test_YYYYMMDD_<slug>` names.

**Run results / reports:**
- **B-044 (reload-safe RunResult)** — Streamlit's module watcher reloads `src` modules mid-session, creating a new `RunResult` class; stored instances then failed `isinstance` and the results/evidence silently vanished ("results disappeared" bugs). New `is_run_result()` duck-type check (`TypeGuard`) replaces all 12 `isinstance` gates.
- **Real per-test durations in reports** — sidecars now write `duration_s` (was hardcoded 0.00).
- **Report titles** — "6. 6. [T06]" double-index removed (criterion enumeration stripped; report formats add their own index).
- **HTML report embeds failed-step screenshots** (base64) — passing galleries stay on the Evidence page (full-page PNGs ~3.4MB each would bloat the report).
- **Re-run Failed merge** — `merge_rerun_results()` keeps passing tests in the table; a failed-only rerun no longer drops them.

**Evidence:**
- **Click-success screenshots** — every passing click step now captures evidence (was failures-only); verified T07 evidence 4/9 → 9/9 steps.
- **Evidence UI** — screenshots render inline per step (📸 marker + image), not an unlabeled strip.
- **Image-wait before screenshots** — product grids no longer captured mid-load (blank images read as spurious defects); verified stddev 10.9 → 31.0 on the dress-category shot.
- **This-run evidence gating** — stale sidecars from previous sessions no longer show as "this run" (gated on a real session run).

**Self-healing:**
- **Timeout 300s → 600s** (`PIPELINE_TEST_TIMEOUT`) — suites longer than 300s silently timed out and reported "0 failures / nothing to heal" while real failures sat in the table.
- **Package-directory resolution** — `heal()` crashed (`PermissionError`) when `saved_path` is a package directory; resolves to the test file.
- **Empty-results ≠ all-pass** — a no-results run surfaces `run_error` instead of "✅ All tests pass".
- **LLM-unavailability surfaced** — if the LLM reviewer fails (provider not configured), the report names the tests instead of silently marking unfixable.

**Pipeline / generation:**
- **POM dedup** — `deduplicate_pom_lines()` in `pom_helpers.py` (wired into the orchestrator) removes the LLM skeleton's duplicated POM imports/instantiations (was `home_page` ×3 per test).
- **Living Test Plan UX** — `Reviewed` moved far from the headerless delete checkboxes, delete-row caption added, flagged-condition warning + tooltip.
- **`SETTING_MODEL_NAME`** wired into `streamlit_app.py` (persistence existed via literal key; constant now used).

**Open bugs added:** B-042 (locator-repair patch dedents to module scope — collection crash) and B-043 (dropdown run counts report 0 despite real history) — both still open.

---

## ✅ Shipped 2026-08-03 — Export gate: exports are now runnable + validated (B-031, B-032)

**Session doc:** `docs/sessions/2026-08-03_export_gate_and_broken_exports.md`

**What shipped** — exports went from 34/35 stubs + 1 non-importable to a gated, verified artifact:
- **B-031 fixed**: POM glob `po_*.py` → `*.py` (generated pages are `home_page.py`/`cart_page.py`); true POM-mode export (`preserve_pom_calls=True`); `@pytest.mark.evidence(...)` decorators stripped in all forms; B-020 assert family (`assert_hidden` etc.) converted in tests + POMs; stub guard raises on all-stub/all-skip/no-test sources; same-second export collision guard.
- **B-032 fixed**: export copies `run_results.sqlite` (was the never-created `playwright_tests.db`), legacy fallback; `_count_run_results` fixed too.
- **`scripts/export_gate.py`**: 9-gate end-to-end export validation against a deterministic golden localhost fixture (`fixtures/golden_package/` + `fixtures/golden_site/`): stub guard → export flat+POM → flat/POM artifact checks → run-history DB copy → collect → both suites execute and pass. Golden 9/9 PASS; real 20260803 package 8/8 PASS (26 tests collect clean).

**Verification:** full suite 2122 passed / 1 skipped (+20 tests); ruff + format + mypy clean; smoke 35/35; export gate 9/9 (golden) + 8/8 (real package).

---

## ✅ Shipped 2026-08-03 — Saucedemo checkout cluster (13/13 gates PASS)

**Session doc:** `docs/sessions/2026-08-03_saucedemo_checkout_cluster.md`

**What shipped** — saucedemo `verify_production` went 10/13 → **13/13 gates, 6/6 tests, stable**; automationexercise 3/7 (HEAD) → 4–5/7:
- **Soft-404 SPA recovery** (`src/scraper.py`): saucedemo (SPA-on-GitHub-Pages) serves every `.html` path as HTTP 404 + app shell; the stateless scraper bailed on `status >= 400`. Now renders first and judges content via a URL-rewrite signal (`_is_soft_404`).
- **Credentials reach the pipeline** (`scripts/verify_production.py`): saucedemo demo credentials (env-overridable, mirroring eval) passed to `TestOrchestrator` — without a session the stateful scrape captured the login wall, so the cart had no items and checkout wasn't an option.
- **Site-agnostic stateful routing** (`src/url_utils.py`): `is_stateful_cart_checkout_path()` replaces the automationexercise-hardcoded `{/view_cart, /checkout}` set; covers `/cart.html`, `/checkout-step-one.html`…
- **URL candidates re-enabled** (`build_common_path_candidates`): concept-driven, same-domain candidates from the shared route vocabulary — SPA sites have no hrefs for journey discovery, so cart/checkout URLs never existed.
- **Journey subprocess credential round-trip** (`src/journey_subprocess.py`): the payload serialized `credential_profile` but the child never read it back; plus `JourneyScraper` logs in at the starting URL when a profile is present.
- **B-015 ghost exorcised (3 places)**: `_dismiss_modals` / `_dismiss_confirmation_modals` / setup script clicked `button:has-text("Continue Shopping")` globally — saucedemo's cart-page button navigated journeys *and tests* back to inventory. Dismissal is now scoped to modal containers; the tracker no-ops modal-close clicks when the modal is already gone.
- **Dead/redirected page filters**: `_drop_dead_pages` (<3-element SPA shells) + `_drop_redirect_duplicates` (200-redirect-to-home keys, e.g. automationexercise `/inventory.html`) — these polluted keyword/ASSERT resolution.
- **B-024 class fields**: `normalise_element_text` includes placeholder (saucedemo checkout `#last-name` etc.); B-024g separator-normalized word-subset matching ("zip code" → "Zip/Postal Code").
- **Navigation-intent fallback**: SPA cart/basket icons have no accessible name — failing cart-navigation descriptions resolve as GOTO to the verified page URL, keeping page context advancing through cart → checkout.
- **Post-login ASSERT mapping**: "logged in" resolves to inventory/products, not the login page.

**Verification:** full suite 2095 passed / 1 skipped; ruff + mypy clean; smoke 35/35; eval static 100%; `verify_production saucedemo` 13/13 (4 consecutive runs), automationexercise 12/13 (improved from HEAD 12/13 with 3/7 execution).

**Open items (documented in session doc):** automationexercise guest-checkout login gate (story lacks login; the site requires auth to checkout); automationexercise cart-link/assert timing races; `scripts/3d/map` + pre-existing archived debug scripts lack markdown_docs; Windows backslash bug in `ui_run_results` setup-script print line (pre-existing).

---

## ✅ Shipped 2026-08-02 — CLI walkthrough driver + zero-pass pipeline fixes

**Session doc:** `docs/sessions/2026-08-02_cli_walkthrough_and_zero_pass_pipeline_fixes.md`

**What shipped:**
- **CLI walkthrough driver** (`scripts/cli_walkthrough.py`, new) — marker-driven subprocess driver; NAV pass 41/41, FULL pass 59/59 (real LLM + live automationexercise.com). Documents Windows pipe gotchas (read1 vs read, one-write-per-input, no-blank-lines paste).
- **CLI crash fixed — "Load Existing Generated Tests"** (`PermissionError`): `load_package_manifest()` called with a package dir instead of the manifest file; now directory-aware + both CLI callers pass `reconstruct=True`. 4 regression tests.
- **CLI POM/Consent invisible feedback**: State block shows `Consent`/`POM Mode`; toggle handlers pause with confirmation (also fixes stray-Enter msvcrt re-select bug).
- **POM mode discarded resolved selectors** → tests skipped at runtime (`home_page.click('product name link')` instead of the resolved `a[href="/product_details/1"]`). Now emits `click(label, selector=...)`; generated POMs use it directly; generic `fill()` added. `src/pom_helpers.py`, `src/page_object_builder.py`.
- **Consent-overlay pollution**: 1,448/2,328 scraped elements were OneTrust `.fc-*` markup (hidden in DOM); consent removal only matched ID-based selectors. Added class-based selectors to `src/scraper.py` — POMs 1806 → ~520 lines.
- **URL trailing-slash mismatch** in assertions/navigation (`normalize_url()` in `src/url_resolver.py`, applied at all emission points in `src/placeholder_orchestrator.py`).
- **FILL resolved to container div** (saucedemo `[data-test="login-container"]` accessible_name collision) — fillability gate added to `pass1_text_match`.
- **Evidence-tracker hang**: `_record_step` re-captured metadata for a locator that no longer exists after a click navigated — each un-timed Playwright call waited 30s (×4 ≈ 120s/test). `_record_step` now accepts pre-captured `element_metadata=`; suites complete in ~140-175s (were 600s timeouts).
- **verify_production timeout message bug**: printed literal `{max(60, min(180, len(test_funcs) * 25))}s`; now real value + salvages partial pytest output/evidence count on timeout. Suite cap raised to `min(300, tests*30)`.

**Verification:** full suite 2042 passed / 1 skipped; ruff + mypy clean; eval static 100%; `verify_production` 20/26 → 22/26 gates. Verdict still FAIL — remaining failures are the **semantic layer** (see session doc §Open work: dialog-role scoping, assertion-state polarity, heading-role asserts, upstream skeleton phrasing, LLM re-ranking with T-strings + bounded retries; **do not add site-specific lists** — match playwright.dev's ARIA-role vocabulary).

---

## ✅ Shipped 2026-08-02 (continued) — Semantic layer (page-load, dialog scoping, polarity) + CLI quality + eval harness gap

**Session doc:** `docs/sessions/2026-08-02_semantic_layer_and_cli_quality.md`

**What shipped:**
- **Page-load assertions resolve correctly**: "title" no longer vetoes page-state routing (`<page> page title` → `to_have_url`, matching the golden encoding); `resolve_url` root-path substring bug fixed (multi-word descriptions no longer resolve to the home URL); golden validator compares `to_have_url` trailing-slash-insensitively; skeleton prompts steer load-style conditions to `{{ASSERT:<page> loaded}}`. Production: `test_01_home_page_loads` → `to_have_url("https://automationexercise.com/")`.
- **Dialog-action scoping (Pass D)**: `{{CLICK:OK}}` no longer resolves to a hidden CSRF input ("ok" substring inside "csrfmiddleware**TOKen**" short-circuited the fast path at a flat 100). CLICK fast-path + pass-2 hygiene (hidden penalties, ≥3-char substring), plus a structural Pass D: dialog-intent descriptions resolve against in-modal interactive elements, preferring close-modal controls. Production: `click('OK button', selector='button.btn.close-modal')`; automationexercise execution 2/7 → 5/7.
- **Assertion-state polarity**: "popup closed"/"item removed" now emit `assert_hidden(...)` (`wait_for(state="hidden")`) instead of `assert_visible`. `polarity_assertion_type()` hooked at both resolution paths. Production: `assert_visible(...confirmation popup)` → `click('OK', selector='button.btn.close-modal')` → `assert_hidden('p.text-center', label='popup closed')`.
- **CLI fixes (found by running the real CLI — `scripts/cli_walkthrough.py --pass full` — not by unit tests)**: table truncation (Living Test Plan / Test Table wrap to terminal width), `[llm_client]`/`[pipeline]` debug moved to stderr (was interleaving with menus under `PIPELINE_DEBUG=1`), export `story_slug` AttributeError (Session property), export "Tests: 0" (file→dir path normalization), flat export POM→Playwright conversion + idempotent `expect` import (exported tests now runnable).
- **CLI walkthrough hardened**: new `reject:` capability (export step now FAILS if "Export failed" appears — previously passed while erroring because it only checked the "Press Enter" marker); heal-flow markers updated for the "2 test(s) still failing. → Choice:" outcome.
- **Eval harness gap closed**: `--mode full --regenerate` persisted no test files, so "Tests executed: 0" was reported every run. `EvalRunner._persist_regenerated_tests()` writes `generated_tests/test_<site>.py`; full run now executes **33 tests, 17 passed (51.5%)**.

**Verification:** 2081 passed / 1 skipped; ruff check + format clean; mypy `src/ cli/` clean; smoke 35/35; eval static 100% all sites; full-regenerate resolution 65.7-67.2% (best in DB history); CLI walkthrough NAV 41/41 + FULL 60/60; verify_production 22/26 (semantic ceiling unchanged).

**Note:** `src/llm_client.py` is a protected file — changed only for a 3-line stderr-routing fix (CLI log interleaving), flagged per AGENTS.md.

---

## ✅ AI-032 — Semantic Scraper Transition (COMPLETE)

**Status:** ✅ Complete  
**Branch:** `feat/semantic-scraper` (merged)  
**Spec:** `docs/specs/FEATURE_SPEC_semantic_scraper.md`

**What:** Three-layer hybrid extraction — BS4 (structure) + CDP AX tree (accessible_name) + `page.aria_snapshot(boxes=True)` (placeholder, value, bbox, groups). Enabled by default; `SCRAPER_BACKEND=bs4` for old behavior.

**Delivered:**
- ✅ **Phase 1** — `src/aria_parser.py` (328 lines, 33 tests)
- ✅ **Phase 2** — Hybrid extraction wired into `PageScraper._scrape_url_sync_result()`
- ✅ **Phase 3** — Resolver alignment (B-024/B-025/B-026 scorers, eval = 52.2%, no regression)
- ⚠️ **Phase 4 cleanup DEFERRED** — Hybrid architecture kept intentionally (each layer provides unique data: ARIA misses hidden elements, BS4 lacks semantic names)

**Results:**
- ✅ Resolver accuracy: **46.3% → 55.2%** (+8.9pp, RAG off)
- ✅ Resolver accuracy: **53.7% → 64.2%** (+10.5pp, RAG on)
- ✅ lv_insurance eval-005: **54.2% → 79.2%** (+25.0pp)
- ✅ Static eval harness: **79.1% → 88.1%** (+9.0pp vs baseline)
- ✅ Ruff clean, mypy clean, 125+ tests pass

**Actual sessions:** 3 (estimated 2-3)

---

## ✅ B-024 — `<select>` elements use placeholder text instead of label for accessible_name (✅ FIXED 2026-07-23)
**Related:** B-016 (synonym-aware matching), eval harness resolver accuracy
**Impact:** 3/67 placeholders fail (4.5pp) — `scheme`, `occupation`, `overnightLocation` on LV Insurance
**Eval context:** `eval-005_lv_insurance_quote.json` resolver mode

**Symptom:** `<select>` elements are scraped with `accessible_name: "Select..."` (the default
`<option value="">Select...</option>` placeholder) instead of the actual label text
(e.g., "Scheme", "Occupation", "Parking Location"). The resolver's Pass 1 text match
cannot find "scheme" or "occupation" in any element text, so these placeholders return
`None` and the generated test emits `pytest.skip()`.

**Root cause:** The scraper's `_extract_elements_from_html()` or CDP AX tree enrichment
reads the `<select>`'s accessible name from the first `<option>` (default placeholder)
rather than from the associated `<label for="...">` or the `<select>`'s `aria-label`
attribute. This is a standard ARIA pattern — the label wraps or references the select,
but the placeholder option is the visible text.

**Proposed fix:**
1. In `src/scraper.py` or `src/accessibility_enricher.py`: when extracting `<select>`
   elements, prefer the `<label for="...">` text or `aria-label` over the first
   `<option>` text for `accessible_name`.
2. Fallback: if no label exists, use the `<select>`'s `id` as the accessible name
   (e.g., `scheme` → "scheme").
3. Update eval harness golden keys to verify the fix.

**Expected improvement:** +4.5pp resolver accuracy on LV Insurance (from 54.2% → 58.7%)

**Estimated sessions:** 0.5

---

## ✅ B-025 — Parent div click targets lose to child heading elements in scoring (FIXED)

**Status:** ✅ Fixed (shipped as part of AI-032 Phases 2-3)
**Related:** B-014 (ASSERT scoring), B-016 (role filtering), AI-024 (a11y enrichment)
**Impact:** 9/67 placeholders fail across LV Insurance and saucedemo (13.4pp)
**Eval context:** `eval-005` (6 failures), `eval-001` (2 failures)

**Symptom:** When a clickable `<div>` (e.g., `#productCar`, `#paymentFull`, `#quoteSuccess`)
contains a child heading (`<h4>`, `<h2>`, `<h1>`) with the same text, the child heading
wins the resolver's Pass 3 scoring because it has exact text match in `accessible_name`.
The parent div (the actual click target) loses because it has no text of its own — the
text lives in the child.

**Fix shipped:**
1. **Heading penalty in `_click_role_bonus()`** — `src/placeholder_scorers.py`:
   - Heading without ID: -20 penalty (likely child of clickable parent)
   - Heading with ID: -8 penalty (unusual, but still penalised)
   - Container roles (generic, group, region, article) with ID: +10 bonus
2. **Pass1 heading skip in `element_matcher.py`** — Headings are skipped for CLICK
actions (headings are display elements, not click targets)

**Verification:**
- ✅ Code shipped: `_click_role_bonus()` lines 355-381
- ✅ CHANGELOG updated as part of AI-032
- ✅ Part of eval accuracy improvement from 46.3% → 55.2% (RAG off)
- ✅ No regressions checked via eval harness

**Actual sessions:** 0 (shipped as part of AI-032)

---

## ✅ B-026 — Resolver locator format mismatch — correct element, wrong selector syntax (FIXED)

**Status:** ✅ Fixed (shipped as part of AI-032 Phase 3)
**Impact:** 2/67 placeholders fail (3.0pp) — golden key comparison is too strict
**Eval context:** `eval-001` (saucedemo), `eval-002` (automationexercise)

**Symptom:** The resolver finds the correct DOM element but the locator string format
differs from the golden key's expected format, causing a comparison failure.

**Fix shipped:** Locator normalization in `scripts/eval/golden_validator.py`:
- `#foo` matches `[id="foo"]`
- `[data-test="bar"]` matches `.class[data-test="bar"]` (subset match)
- `input[name="x"]` matches `[name="x"]` (attribute-only vs tag+attribute)

**Estimated sessions:** 0 (shipped as part of AI-032)

---

## ✅ AI-031 — Eval Harness: Resolver Accuracy Improvement Sprint (PARTIALLY COMPLETE 2026-07-26)

**Status:** ✅ Resolver accuracy improved from 53.7% → 58.2% (+4.5pp, RAG off). LV Insurance 83.3% → 95.8% (+12.5pp).
**Related:** B-024, B-025, B-026 (all shipped as part of AI-032)

**Fixes shipped 2026-07-26:**
- `_build_haystack`: added `id`, `accessible_name` + camelCase splitting so element IDs contribute to matching
- `_structural_bonus`: fixed camelCase ordering, added single-word ID match bonus (+15), `ref`→`reference` expansion
- `_split_camel_case()`: splits `quoteRef`→"quote Ref", `usageType`→"usage Type"

**Actual sessions:** 0.5

---

## ✅ AI-030 — LV Insurance Mock Site & Ingestion Agent Foundation (COMPLETE 2026-07-26)

**Status:** ✅ Complete  
**Commit:** (pending ship-it)

**What:** Built a 7-step LV car insurance quote flow mock site (60KB HTML) and assembled real LV product documents for the Phase 1 Ingestion Agent. PDF parsing wired into `rag_ingest.py` via `src/pdf_ingest.py` (PyMuPDF-based: heading detection, table extraction, chunking).

**Delivered:**
- ✅ `generated_tests/mock_insurance_site.html` — full quote flow with reg lookup, driver management, premium calc, decline path
- ✅ `docs/rag_corpus/lv_docs/` — 7 docs (3 real LV PDFs + 3 redacted personal + 1 synthetic underwriting guide)
- ✅ `scripts/eval/dataset/eval-005_lv_insurance_quote.json` — 10 criteria, 33 golden placeholders
- ✅ `src/pdf_ingest.py` — PyMuPDF extraction pipeline (headings, tables, chunking)
- ✅ `rag_ingest.py --pdfs` — CLI flag ingests PDFs into vector store
- ✅ RAG store: 160 entries (67 golden + 27 Playwright docs + 66 PDF chunks from 3 LV policy PDFs)
- ✅ RAG accuracy: **53.7% → 64.2%** (+10.5pp), LV Insurance: **83.3% → 91.7%** (+8.4pp)

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

## 🎯 Test Pack Restructure + Mock-Site Strategy (2026-08-03 CLI review)

**Status:** ✅ COMPLETE 2026-08-07 — all 5 work items shipped (mock catalog, test-pack split, gate_full, enshrined-bug rewrites)

**Work item 2 (test-pack split, 2026-08-07):** new `tests/contract/` (6 tests — mock artifact/schema/import/route/behaviour contracts against the banking+ecommerce mocks), `tests/adversarial/` (7 tests — 404-page pollution B-045, overlay injection B-029, broken-locator B-033, modal scoping B-015), `tests/resilience/` (6 tests — corrupt DB B-034, reload-safe RunResult B-044, sidecar-without-teardown B-035, concurrent opens, corrupt settings). Default pytest already routes to the offline layer via `-m "not slow and not integration"`; the new layers run in CI (Gate 3 `test` job). Also fixed the long-noted B-039 `MockServer._start()` `os.chdir` bug — the server now serves via the handler's `directory` kwarg and never mutates the caller's cwd (relative-path callers / second server starts no longer break).

**Work item 3 (gate_full.py, 2026-08-07):** `scripts/gate_full.py` — one-command chain smoke → unit pytest → eval-static → verify_production → export_gate, exit non-zero on first failure; `--offline` (gates 1-3, CI-able), `--skip N`, `--pytest-args`. Verified: offline mode 3/3 gates pass.

**Work item 5 (enshrined-bug rewrites, 2026-08-07):** audit confirmed both named examples were already rewritten as their fixes landed — B-033 (`screenshot is None` → asserts `is not None` + `failure_note`) and B-029 (asserts post-click navigation verification + failure amendment, `test_b029_*` ×3); grep for `screenshot is None` across `tests/` is empty. No further rewrites needed.

**Why:** 2,095 green unit tests coexisted with 7 real bugs (B-029→B-035). The suite asserts internal invariants against MagicMocks; the product fails on external contracts (navigation happened?, evidence exists?, export runs?, DB survives?, overlays handled?). The layers that catch real bugs (eval harness, verify_production) are manual-only.

**Structural problems found:**
1. Unit pyramid on a mock foundation — 101 module files test "what the function returns", not "does the product work".
2. Bugs enshrined as contracts — `test_click_fast_fails_when_locator_missing_on_page` *asserts* `screenshot is None` (B-033 is tested behaviour).
3. ~~Network tests mislabeled~~ **REVISED 2026-08-03 (export gate session): the audit claim was verified FALSE.** `tests/integration/test_pom_mode_end_to_end.py` is pure offline string/JSON-schema checks (the automationexercise.com URLs live in a module-level sample constant, never executed); the genuinely network-touching tests (LLM pipeline runs in `test_pipeline_end_to_end.py`, real embedding-model downloads in `test_rag_store.py`) already carry `slow`+`integration` markers, and CI applies `-m "not slow and not integration"` via pytest.ini addopts. Corrective action shipped: `tests/test_no_live_network_in_default_suite.py` — a static guard that FAILS if any unmarked test executes a navigation call (goto/navigate/scrape_url/run_pipeline/attempt_login) with a live-site URL literal, so the "default suite is offline" property is durable.
4. ~~Real gates outside CI~~ **eval static wired into CI (2026-08-03, export gate session)**: new `eval-static` job runs `eval_harness.py run --mode static --min-accuracy 79` (offline, ~0.5s, exit 2 below floor) in parallel with lint/type-check. `verify_production` + `export_gate` remain manual gates (browser+network; the golden export gate is CI-ready once the mock layer exists).
5. No adversarial/resilience/contract layers.

**Mock-site strategy (investigated 2026-08-03):**
- ✅ Strong case to make the mock site the primary test target: deterministic, local, no Google consent/ad stack — closer to a real user's own site (nobody tests their own site against prod ad networks). The overlay race (B-029) can ONLY be tested deterministically with a mock that can inject an overlay on command.
- ⚠️ Current mock (`generated_tests/mock_insurance_site.html`) is too thin: single-page JS-step form, **0 modals, 0 nav links, 0 multi-page journeys**. Covers form-fill only; none of the navigation/modal/overlay classes that produced B-029/B-030.
- 🎯 Extend it: multi-page e-commerce mock (home → category → product → cart → checkout) + add-to-cart modal + **optional injectable consent/ad overlay** (query param / server toggle) so tests exercise clean path AND overlay race deterministically.
- Golden keys against the mock never decay (real-site keys decay — AGENTS.md warns). Mock + static eval could run in CI (localhost, no external network).

**Mock-site catalog — product-range research (2026-08-03, tavily + GitHub verified):**

| Product type | Reference repo(s) | Stack / setup | Exercises | Priority to build |
|---|---|---|---|---|
| E-commerce (multi-page) | automationexercise (live, already used); Potion Shop; Practice Software Testing | static / low | nav, add-to-cart modal, cart, checkout — **the B-029/B-030 class** | **1 — build first** |
| Banking / fintech | `cypress-io/cypress-realworld-app` (5.9k★, TS, active) | React+Express+SQLite / med | auth, transfers, payments, multi-user | 2 |
| Insurance (multi-step form) | ✅ **already have** (`mock_insurance_site.html`) | static / done | multi-step form, validation | done |
| Booking / travel | Restful-Booker (React+API); Sunny Meadows B&B | React+API / med | search, date pickers, booking lifecycle | 3 |
| Healthcare | Spring PetClinic (Java, heavy); lighter patient/appointment form | Java / high → prefer own static | forms, CRUD, appointments | 4 |
| Enterprise / HR | OrangeHRM (open-source demo) | PHP+MySQL / high → prefer own | org hierarchy, multi-role, admin | 5 |
| Element / widgets | The Internet (saucelabs/the-internet, static, GH-Pages); LetCode; DemoQA (have) | static / low | auth, alerts, frames, drag-drop, shadow DOM | 6 |
| Robustness / security | OWASP Juice Shop | Node+docker / med | auth, admin, search, tricky forms | 7 |

**Build rule:** for each row, make OUR OWN minimal self-contained version in a `mock_sites/` catalog (single-file HTML/JS or tiny server, same pattern as the insurance mock) — deterministic, localhost, versioned in-repo (never decays), each covering one distinct product shape. Each mock ships with a user story + golden-key eval dataset so the harness runs across ALL product types. Do NOT depend on third-party demo sites (they decay, go down, or are covered in ads).

**Proposed work items:**
1. Fix mislabels first: mark all network-touching tests `slow+integration` (default run becomes deterministic).
2. Split by intent: default `pytest` = mock layer; `-m integration` = network; add `tests/contract/`, `tests/adversarial/`, `tests/resilience/`.
3. `gate_full.py`: smoke → unit → eval-static (offline, CI-able) → verify_production → export gate. Wire `eval --mode static` into CI Gate 3 today (free offline regression protection).
4. Expand the mock site per above; move eval golden keys onto it.
5. Rewrite enshrined-bug tests (B-033/B-029 contract) as fixes land.

---

## 🔴 Open Bugs

### B-045 — Banking mock surfaces: 404-page pollution, ecommerce-only login/success transitions, role-worded nav fast-matches, fill-on-select
**Status:** ✅ Fixed (2026-08-07, banking mock session)
**Priority:** High — 5 site-agnostic pipeline gaps the banking mock made deterministic

The banking mock (priority 2 in the mock catalog, eval-007) surfaced a cluster of pipeline gaps that live sites only show as flaky noise:
1. **HTTP-404 pages survived `_drop_dead_pages`** — the stdlib server's 404 body scrapes to ~5 elements (above the 3-element threshold), so concept-candidate URLs (`/products`, `/cart.html`, `/checkout` — ecommerce vocabulary generated for any story mentioning payment/order) stayed in the scrape and their "Error code: 404" text won keyword/ASSERT matching. Fixed: `_is_error_page()` content-based drop (2+ markers) in `src/placeholder_orchestrator.py`.
2. **Login-transition vocabulary was ecommerce-only** — `_infer_click_transition_url` mapped a login click to `inventory`/`products`, so a banking journey never advanced past the sign-in page and every downstream placeholder stayed scoped to it. Fixed: site-agnostic landing vocabulary (`inventory/products/dashboard/accounts/home/overview`) in `src/url_inference.py`.
3. **No submit-success page transitions** — transfer/payment forms submit without hrefs, so the resolver stayed on the form page and success-message asserts resolved against the form's own elements (submit button / error paragraph). Fixed: `transfer`→`transfer_success`, `pay/payment/submit`→`payment_success` transitions. Also fixed a branch-order bug where "submit payment" hit the transfer branch first.
4. **Role-worded descriptions fast-matched nav links** — "pay bill button" matched the header nav link "Pay Bills" (earlier in DOM) in Pass 1/2 text matching before scoring could prefer the real `#pay-bill` submit button. Fixed: `_named_role_in_description()` gates Pass 1/2 to the named role; exact-text pre-sweep so "Pay Bills" (nav) vs "Pay Bill" (button) disambiguate by exact equality; submit-intent verb bonus + fillable-element CLICK penalty in `src/placeholder_scorers.py`.
5. **`fill()` on native `<select>` crashed at runtime** — Playwright rejects `.fill()` on `<select>` ("Element is not an <input>, <textarea> or [contenteditable]"); the LLM's fill value ("Electric Company") also rarely equals the option `value` ("electric"). Fixed: `EvidenceTracker.fill()` probes the tag and routes to `select_option()`, with exact-value → exact-label → substring-of-option-label fallbacks.

**Also fixed (golden validator):** `_normalize_locator()` now strips a leading tag from class selectors (`p.account_balance` ≡ `.account_balance`) — lifted eval-006 from 12/16 to 14/16 and eval-007 to 13/13 (100%).

**Verified:** eval static overall 95.2% → **97.9%**; eval-007 13/13 static + **8/8 execution** against the mock (login → dashboard → transfer → success → pay bill → payment success, session gate verified); full suite 2309 passed (1 environmental flake in test_llm_client under parallel workers — passes in isolation); ruff + mypy clean.

---

### B-042 — Locator-repair patch dedents the replacement line to module scope (collection crash)
**Status:** ✅ Fixed (2026-08-07, `0951ec0`, CI pending)
**Priority:** High — every "🔧 Fix Locator" patch can silently break the whole suite at COLLECTION time

`apply_patch` in `src/locator_repair.py` rebuilds the patched line from regex groups (`before_quote` + locator + `after_quote`) that **exclude the line's leading indentation**, then writes it back at column 0. When the patched line is inside a test function, the replacement lands at module scope → `NameError: name 'evidence_tracker' is not defined` → the module fails to import → 1 error, 0 tests. Reproduction (live, 2026-08-06): a Fix-Locator repair of T11 in `test_20260805_181339...` wrote `evidence_tracker.assert_visible(...)` dedented to column 0; pytest then collected 0/14 tests.

**Fix shipped:** the reconstruction now explicitly re-applies the original line's leading whitespace (`indent` + `before_quote.lstrip()`) in the regex path, so a patched line inside a function body can never land at module scope. Also hardened: an **empty `original_locator`** (previously matched *every* line in the search window, then `.replace("", …)` mangled the whole file) now raises `LocatorRepairError`. Regression tests: patch inside a function body (regex path + evidence-tracker fallback path) still compiles via `ast.parse`; empty-original raises.

---

### B-043 — Sidebar package dropdown reports 0 runs when real run history exists
**Status:** ✅ Fixed (2026-08-07, `0951ec0`, CI pending)
**Priority:** Medium — the dropdown's run count actively misleads

`find_existing_packages` refreshes `run_results_count`/`last_run_at` from `package_manifest.json`, but those fields count a different artifact than actual test runs: the dropdown showed `(1 test, 0 runs)` for a package whose real history (`run_result_persistence`) held **13 runs / 85 passed / 28 failed** (verified via the loaded-package sidebar summary). Manifest fields are only updated when a run persists results in the way the manifest expects; evidence-bearing runs (sidecars + screenshots) don't bump them.

**Fix shipped (option a):** `find_existing_packages`/`_reconstruct_manifest` now reconcile run fields through `_refresh_run_stats()`: workspace SQLite run-history DB first (`run_stats_by_package()` — one `GROUP BY test_package` pass, exposed via `run_result_persistence`; matches the package dir and any path beneath it, Windows-case-normalised) → legacy per-package JSON/SQLite counting → the manifest's own values (CLI bumps via `update_last_run_at`). Regression tests: DB-persisted runs appear in the dropdown count + last-run; test-file-path recording matches the package; manifest-only counts survive when the DB has no rows.

---

### B-039 — Self-healing blind to its own most common failure mode
**Status:** ✅ Fixed (2026-08-04, AI-035 write-back Tier-1 verification, CI green)
**Priority:** High — discovered while live-testing the AI-035 self-healing loop against the e-commerce mock; without this fix the loop can never fix anything.

Two compounding parser/classifier gaps made the self-healing loop pre-screen **every** real generated-test failure as unfixable (it only ever worked against synthetic error strings):

1. **`pytest_output_parser._FAILURE_NAME_RE` rejected `[chromium]`-suffixed failures-block headers** (`^_+ (\w+) _+` stops at `[`) — ALL generated tests run parameterized, so `error_message` was **always empty** → `classify_failure("")` → OTHER → pre-screen skip. Fixed: `^_+ (\S+?) _+` + strip the param suffix before the `results_by_name` lookup (matching `_ERROR_RE`'s existing `split("[")[0]`).
2. **`failure_classifier` didn't recognize the evidence-tracker fast-fail** — `_LocatorNotFoundError: Locator '...' not found on current page (...)` matched no regex (only Playwright-native "TimeoutError waiting for" did) → classified OTHER → pre-screen skip. Fixed: new `LOCATOR_NOT_FOUND` regexes → `LOCATOR_TIMEOUT` (LLM-reviewable) with locator extraction.

**Verified live:** broken locator → heal → `fixed: 1, learned: 1, remaining: 0`; store gained `CLICK 'Cart link' → a[href="/cart.html"]` with `source=self_healing, confidence=1.0`; re-heal dedups (hit_count 2, one row). +7 tests (2263 total); eval static 95.2%.

**Also noted (not fixed):** `MockServer._start()` does `os.chdir(directory)` on the whole process — any relative path in the calling process breaks after auto-start (eval harness works because its dataset/captures defaults are absolute; `--dataset <relative>` silently yields 0 stories). Fixing = save/restore cwd around the server thread, or resolve paths before chdir.

---

### B-037 — E-commerce mock surfaces: empty-cart element resolution + the cvc/skip family
**Status:** ✅ Fixed (2026-08-03, B-037 session, CI green)
**Priority:** Medium — the mock made both failures deterministic; fixes lift eval-006 execution to 8/8

**Context:** first measured baseline on `mock_sites/ecommerce/` (eval-006, capture `ecommerce_mock_code.py`): static resolution 12/16 (75%), execution **6 passed / 1 failed / 1 skipped**. The mock reproduced deterministically what the live site only showed as flaky noise.

**Fixes shipped (3 code + 4 mock):**
1. **Empty-state gate** (`src/placeholder_scorers.py`, `_assert_empty_state_rejects`): elements whose text signals emptiness ("Cart is empty!", "no items") are EXCLUDED from content-presence ASSERTs — the B-016 negation gate only ran in pass-1 text matching; the scoring path let `#empty_cart` win "product name and price" by default.
2. **Payment-card synonyms** (`src/semantic_matcher.py`): `cvc ↔ cvv ↔ cvv2` — the LLM skeleton's "cvc" FILL was unresolvable against the "CVV" field, skipping the entire checkout+payment test (the skip family eval-002 never saw).
3. **CSS classes in structural matching** (`_structural_bonus`): `p.cart_total_price` now matches "price" in "product name and price" (+15) — table cells carry the words text alone lacks.
4. **Mock fixes** (`mock_sites/ecommerce/`): classed cells in `cart.js` (`h4.cart_description`, `p.cart_price`, `p.cart_total_price`) because the scraper's tag lists exclude `table`/`td`; `name="cardholder_name"` on the Cardholder Name input (was `card_name` — shared word "card" won the pass-1 tie over `#card-number`); **route aliases** (`mock_routes.json` + `scripts/mock_server.py` 302-redirects): `/view_cart`, `/products`, `/checkout`, `/basket`… map to canonical files so journey discovery and cart-seeding reach cart/checkout with items, and page URLs stay canonical for `to_have_url`.

**Measured after:** eval-006 execution **8/8 passed** (full checkout + payment leg executes: `#cvv` filled, order placed, success asserted). Static 12/16 — the 4 remaining misses are LLM skeleton/ranking nondeterminism (ASSERTs skeletonized as URL checks; one LLM-picked card field), the AI-037 class now isolated from site variance. +9 regression tests (empty-state gate ×3, class structural ×3, card synonyms ×2, card-number≠cardholder-name ×1).

---
### B-036 — Consumer config architecture: env-var feature gates don't fit the product
**Status:** ✅ Shipped (2026-08-03, Phases 1–4, CI green)
**Priority:** Medium — blocks RAG-resolution fix (B-030 family) from reaching consumers
**Spec:** `docs/specs/FEATURE_SPEC_B036_consumer_config.md` (2026-08-03) — 4 changes: always-on RAG, bundled golden pack auto-seed, evidence auto-learn (builds on AI-035), settings store + export-time fields. ~3 sessions.

**Principle:** this is a consumer product (Streamlit/CLI). Feature toggles must not require `.env` edits. The product already has the right pattern for API keys (`secure_config.py` — Fernet-encrypted, persisted); the env vars are dev-era leftovers.

**Shipped (Phases 1–4):**
1. ✅ Always-on RAG with graceful degradation — `_build_rag_retriever()` builds by default; `RAG_ENABLED=0` transitional opt-out; empty store ⇒ no bonus ⇒ identical behavior; store/embedder failure degrades to no-RAG (never blocks generation). `RAGRetriever.retrieve()` hardened with once-only warning.
2. ✅ Bundled golden pack + auto-seed — `src/rag_bundled.py` ships eval-001..006 golden keys (83 patterns) + curated Playwright docs (27 chunks); first generation run auto-seeds with idempotent marker `evidence/.rag_bundled_seeded.json`; `rag_ingest.py --bundled/--force/--stats/--prune-learned`.
3. ✅ Evidence auto-learn (AI-035 core + B-036 Phase 3) — `src/rag_learn.py` (`site_hash`, `domain_from_url`, `learn_from_evidence`); `RAGStore.upsert_pattern()` dedup on `(action_type, description, site_hash)` with `hit_count` bump; teardown hook in `generated_tests/conftest.py` learns from passing runs (guarded, batched); site-scoped scoring `SAME_SITE_LEARNED_BONUS=5` (same-site only, cross-site 0) threaded orchestrator → matcher → resolver → scorer. Plan: `docs/plans/AI-035_B036_P3_plan.md`. Live-verified against the e-commerce mock (3 learned patterns, dedup'd); eval static 95.2% unchanged.

4. ✅ Settings store + field migration — `src/settings_store.py` (`SettingsStore`, Fernet-encrypted `~/.ai-test-gen/settings.enc` on the secure_config pattern; corruption-tolerant; `load_setting/save_setting/save_settings/get_all_settings/reset_settings`). Migrated sidebar state consumers actually set: `pom_mode`, `consent_mode`, `provider`/`model_name`, `workspace` (Streamlit sidebar + CLI `Session` seeding — settings win, env is fallback). `JIRA_PROJECT_KEY` env read removed from `src/config.py` (constant default `TEST`); export-time UI field in the Streamlit export panel + CLI menu (`Session.jira_project_key`), feeds `JiraReportGenerator` test-case IDs and a `Project:` header line in the Jira report (`PipelineReportService.build_reports(jira_project_key=...)`). `OCR_BACKEND` → persisted setting (default `pymupdf`); env read is now a fallback only. `LANGGRAPH_ENABLED` removed outright (dead flag — `--use-graph` is the supported path; `generate_skeleton(use_graph=...)` parameter replaces the env read). Streamlit "Learned Patterns" section folded in (`SidebarConfig.render_settings()` — RAG store stats via `store_stats()` + prune button). +30 tests (2229 total); eval static 95.2% unchanged.

**Remaining deferrals:** none — AI-035's self-healing patch write-back (``_learn_from_patch``, ``source="self_healing"``, ``confidence=1.0``) shipped 2026-08-04 in ``src/rag_learn.py`` (``pattern_from_patch``/``learn_from_patch``) + ``SelfHealingRunner`` (guarded hook after each successful ``replace_locator`` patch; description recovered from the evidence sidecar's placeholder label; ``HealingReport.learned`` surfaces the count in CLI + UI). The self-healing lever and the learning loop are now fully wired.

**Also noted:** sidebar config now persists via the SettingsStore (B-036 Phase 4) — the `st.session_state`-only gap is closed. Tier-2 walkthrough (2026-08-04) closed the last gap: the Streamlit UI now also persists `provider_base_url` + `model_name` (save-on-change + seed-on-load) — verified live across app restarts (provider/POM/consent/OCR/workspace/model all round-trip via `~/.ai-test-gen/settings.enc`).

---

### B-035 — Evidence sidecar written only at test END; killed/timed-out tests leave orphaned screenshots with no record
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** Medium — evidence silently vanishes for the exact runs that need it (failures)

`tracker.write()` runs once in `generated_tests/conftest.py` teardown; `_record_step` never persists incrementally. If a test process dies mid-run (pytest `--timeout` kill — already the standard in UI/UAT/verify runs — crash, playwright failure), **no `.evidence.json` is written** while intermediate screenshots survive as orphans. The evidence index (`build_or_refresh`) only sees sidecars, so the run is invisible.

**Also in the same layer:**
- 10 silent `except Exception: pass` blocks in `evidence_tracker.py` — screenshot, diagnosis, and dismissal failures are invisible (no warning recorded anywhere).
- `report.html` (PipelineReportService) embeds **zero screenshots** (verified: 0 png refs in an Aug 1 report) — evidence exists but reports can't show it.
- Evidence files accumulate across reruns (old screenshots from prior runs stay in the dir, unreferenced by the current sidecar).

**Proposed fix:** persist sidecar incrementally per step (or at minimum on step failure); warn (not swallow) when screenshots fail; embed screenshots in reports; clean stale evidence on rerun.

---

### B-034 — `evidence/run_results.sqlite` is corrupted — UI evidence page will crash
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** High — live in the working environment right now

`PRAGMA integrity_check` → **"database disk image is malformed" (Tree 10 page 26)**. WAL mode with a 0-byte WAL + 32KB shm; some queries return rows, others throw. DB mtime Aug 3 03:26 (during the overnight verify runs). Likely concurrent writers (Streamlit UI `build_or_refresh(force=True)` + run-result saves) or a killed process mid-write; the corrupted DB has no self-healing — `_upsert_sidecar` has no try/except, so the UI evidence search/refresh raises `DatabaseError` instead of rebuilding.

**Also found:** `except OSError, json.JSONDecodeError:` (×2 in `evidence_index.py`) — Python-2 syntax that Python 3 parses as a tuple-except, so it *works by accident*; lint-level 2to3 leftover.

**Proposed fix:** on `DatabaseError` during build/search, rebuild the DB (drop + recreate + re-index) instead of propagating; add a preflight `integrity_check` with a recovery path; ensure single-writer discipline (WAL checkpointing) or lock around writes.

---

### B-033 — Evidence gaps: failures leave no diagnostic artifacts; clicks never screenshot
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** Medium — evidence is the product's audit trail; a failed step currently records *nothing* visible

**Confirmed from `test_20260803_101815_...` evidence sidecars:**
- **Failed fast-fail steps have NO screenshot, NO failure_note, NO diagnosis** (`_record_step` skips all three when `fast_fail=True` — contradicts the click() comment "Always screenshot on click failure"). t10 step 6: `screenshot=None, failure_note=None, diagnosis=None`.
- **Click steps NEVER screenshot** (only navigate + assert do) — the exact step that fails (or burns 30s in the fallback marathon) leaves zero visual trace. 23 PNGs for 13 tests, all navs+asserts.
- **No per-step URL** — steps don't record `page.url`; only the final URL at `write()`. Reconstructing where a flow diverged requires the error strings.
- **Storage bloat:** full-page screenshots average **2.4MB each** (54MB evidence dir for one 13-test package).
- **Misleading fast-fail message**: "The element exists on a different page than the one this step runs on" blames the locator when the real cause is an earlier step's silent non-navigation (t10 step 5 → step 6). No cross-step state check.

**Proposed fix:** screenshot + diagnosis on failed steps (fast-fail included); capture per-step URL; flag clicks whose elapsed >10s or that follow a link without a URL change; consider viewport-size (not full-page) screenshots.

---

### B-032 — Export run-history DB copy orphaned since AI-012 (`playwright_tests.db` never created)
**Status:** ✅ Fixed (2026-08-03, export gate session, CI green)
**Priority:** Low — silent no-op, no crash

`src/export_service.py` copies `evidence/playwright_tests.db` — **nothing in the repo creates that file**. The SQLite layer writes `evidence/run_results.sqlite` (`sqlite_persistence.py`, `storage.py`). Same orphan name in `src/pipeline_artifact_manager.py:270`. Dead since AI-012 (2026-06-15) swapped JSON-dir export for the SQLite copy but globbed the wrong filename.

**Fix shipped:** copy `run_results.sqlite` (primary) with legacy `playwright_tests.db` fallback; WAL/SHM files follow the found DB name; README note + `has_sqlite` check updated; `pipeline_artifact_manager._count_run_results` checks `run_results.sqlite` first (and its Python-2 `except A, B:` fixed). Verified by `test_export_copies_run_results_sqlite` + `test_export_legacy_db_fallback` + export gate gate 6.

---

### B-031 — Export feature produces non-runnable/broken suites; never validated end-to-end
**Status:** ✅ Fixed (2026-08-03, export gate session, CI green)
**Priority:** High — claimed shipped (UI button + CLI step), but no export has ever been verified by running the exported suite

**Confirmed:**
- **34 of 35 exports in `exported_tests/` are stubs** (`def test_x(page): pass`) — export ran against empty/stub source packages, no guard.
- **The one real export (`20260802_181655_...`) is non-importable**: `from pages.home_page import HomePage` with **no `pages/` dir shipped** (POM export globs `pages/po_*.py` but generated pages are `home_page.py`/`cart_page.py` — **glob matches nothing**), plus `HomePage(page, evidence_tracker)` NameError and dead `@pytest.mark.evidence(...)` decorators.
- Current strip (`eda9809`) fixes the POM→flat conversion (verified on a live package), but `@pytest.mark.evidence(...)` decorators still survive (regex only matches the bare form) → `PytestUnknownMarkWarning`.
- No end-to-end gate: unlike `verify_production.py` for the main pipeline, nothing exports → runs the exported suite → asserts pass.

**Fix shipped:**
- **POM glob**: `pages/*.py` minus `__init__.py` — matches generated `home_page.py`/`cart_page.py` (exported real package now ships all 5 pages).
- **True POM-mode export**: `strip_evidence_from_test_code(..., preserve_pom_calls=True)` keeps POM imports/instantiations/method calls (only the `evidence_tracker` arg drops from instantiations) — previously POM-mode silently emitted flat output with a dead `pages/` dir.
- **Evidence decorators stripped in all forms** (`_strip_evidence_decorators`): bare, arg-carrying, multi-line, whitespace variants.
- **B-020 assert family converted** (`_strip_tracker_asserts`, tests + POMs): `assert_hidden` → `to_be_hidden()` (the live gap — it survived exports and NameError'd at runtime), plus disabled/enabled/checked/empty/text/text_contains/value/count.
- **Stub guard**: exporting an all-stub / all-skip / no-test source raises `ValueError` with a clear message.
- **Export collision guard**: same-second same-slug exports get `_1`, `_2`… suffixes instead of silent overwrite.
- **Export gate** (`scripts/export_gate.py`): 9 gates — stub guard, flat+POM export, flat/POM artifact validation, run-history DB copy (B-032), collect (importability), and execution of both suites against a deterministic golden localhost fixture (`fixtures/golden_package/` + `fixtures/golden_site/`, port 8123). `--source <pkg>` for real packages (offline), `--run-remote` for live execution.

**Verification:** golden gate 9/9 PASS (flat + POM suites execute and pass), real package 8/8 PASS (26 tests collect clean); exported flat suite of the 20260803 package converts all evidence calls + decorators correctly.

---

### B-030 — "Check Out" resolves to wrapper div `#do_action` instead of the real button `.btn.btn-default.check_out`
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** Medium

`{{CLICK:Check Out}}` emitted `#do_action` (a wrapper `<div>`, no href) even though the scraper captured `('proceed to checkout', '.btn.btn-default.check_out')` and `PlaceholderScorer` rates the button **5 vs 0** for "Check Out" (verified directly). Survives into exports. Root cause is in the resolution path feeding element data to the scorer (tag/role/href likely stripped) — investigate why the anchor lost before the wrapper.

---

### B-029 — Tracker records "passed" for clicks that never navigated (ad-overlay swallow) — no post-click URL verification
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** High — caused all 4 checkout-cluster failures (t10-t13) in `test_20260803_101815_...`

**Symptom:** cart header-link click records `passed` after a **30.5s fallback marathon** with **no navigation**; the next step fast-fails with the misleading "element exists on a different page" error. All 4 failures share the identical signature (step 5 elapsed=30,516ms, status=passed, page still on `category_products/1`).

**Root cause chain (reproduced live, 3×):**
1. FreeCmp consent dialog (`.fc-consent-root`) + Google `#google_vignette` ad overlay intermittently cover the header and intercept link clicks.
2. The primary click (5s timeout) always fails → full fallback marathon (~30s: hover → mouseenter → ancestors → force-show JS `el.click()`).
3. `el.click()` "succeeds" even when Google's click-interceptor swallows the navigation → recorded `passed`, zero URL verification.
4. Contributing factor: the "Continue Shopping" step no-ops (2-6ms, "modal already dismissed") because the add-to-cart modal is mid-fade — the no-op path returns **before** the dismissal calls, leaving the modal to be handled by the next step's dismissal.

**Also latent:** `_dismiss_confirmation_modals` selector `button.btn-success.close-modal` is the **only unscoped** dismiss selector (B-015 scoped the rest) — hazard on pages with a visible close-modal button that is a real action.

**Proposed fix:** post-click navigation verification in `EvidenceTracker.click` — if the target is an `<a>` with a different-path `href` and the URL hasn't changed ~2s after a "successful" click, re-dismiss overlays and retry once (or `page.goto(href)`); scope `button.btn-success.close-modal` to modal containers.

---

### B-028 — Journey discovery selects cart nav link for product / add-to-cart actions
**Status:** ✅ Fixed (2026-08-01, ship-it) — full fix + follow-ups landed
**Priority:** High — cascades: wrong click → missing pages → unresolved placeholders → skips/fails

**Fixed (2026-08-01):**
- **Root cause #1 — action case mismatch:** `_discover_selector()` passed lowercase
  `"click"/"fill"` to `PlaceholderScorer.compute_element_score()` which branches on
  uppercase — every action bonus/gate was silently disabled, so discovery scores
  collapsed to raw word overlap ("View Cart" beat real product buttons at score=1).
  Fixed by normalising the action to uppercase + skipping invisible elements for
  CLICK/FILL + modal penalty only when a modal is actually visible.
- **Root cause #2 — context hints:** product-intent descriptions now prefer
  product-card selectors over nav chrome; category descriptions ("Product Category")
  prefer listing pages over detail pages; modal-dismiss descriptions only click real
  dismiss controls.
- **Root cause #3 — hallucinated locators:** generated POMs now embed a DOM-existence
  index (`_ELEMENTS`) — the click() fallback only targets scraped selectors or
  pytest.skip (never `text=<description>`). Hidden elements (CSRF inputs) excluded
  from POM method generation entirely.
- **Root cause #4 — fillability:** `PlaceholderScorer._is_fillable` aligned with
  `IntentMatcher` (role=number/email/password/...) so quantity inputs resolve;
  FILL-quantity falls back to +/- stepper clicks when no input exists.
- **Root cause #5 — `tag` field missing** from `_build_element_dict` (killed ASSERT
  display scoring in discovery).

**Follow-ups landed with the fix:**
- Batch placeholder fallback now searches ALL scraped pages (was scoped to the seed
  URL — left `Proceed To Checkout` unresolved despite scraped data).
- EvidenceTracker click fast-fails on missing/hidden locators (148s fallback marathon
  → 0.0s) and proactively dismisses consent/ad/modals (~2s vs 30s per blocked click).
- Per-test pytest `--timeout=120` in UI/UAT/verify runs — a stuck test can't hang the suite.
- LLM generation capped at 4096 tokens (`LLM_MAX_TOKENS`) — a runaway no longer burns
  the full 600s request timeout.
- Structural assembler (`src/test_structure_assembler.py`) rebuilds the generated file
  from the parsed journey model — module-level LLM statement leaks are structurally
  impossible (previously crashed pytest at COLLECTION time).

**Verified:** journey home → product page → fill quantity → add to cart → view cart
(with items). verify_production automationexercise: 12/13 gates, execution completes
in ~65-75s (was 600s timeout). Full eval (live regenerate): 53.7% → 65.7% resolution
accuracy vs prior run; static mode unchanged at 100%.

**Symptom:** During journey discovery, generic descriptions resolve to the cart nav link
instead of product cards / add-to-cart buttons:
```
'click on a product to view it'  → a[href="/view_cart"]  (score=1)   ❌
'add product to cart'           → a[href="/view_cart"]  (score=11)  ❌
'dismiss confirmation modal'    → a[href="/view_cart"]  (score=1)   ❌
```
The journey navigates products → view_cart instead of a product page, so checkout pages
are never scraped and cart-dependent placeholders never resolve.

**Live evidence (2026-08-01, automationexercise.com, generated package
test_20260801_120204_...):** T02 add-to-cart FAILED — resolver emitted a hallucinated
locator `text=First product link` (not in DOM; failure reporter suggested `#Men`,
`#gda`, `#Kids`) → `Locator.click: Timeout 5000ms` at ~249s per test. T06 (max cart
items) same root cause. T03/T04/T05 (cart/checkout/purchase) and T08/T09 (quantity)
skip — checkout pages never scraped + site uses +/- quantity buttons (no fillable input).

**Root cause:** `_discover_selector()` in `src/journey_scraper.py` scores generic
descriptions poorly and falls back to weak matches (B-012/B-015 family — those fixes
covered the resolver Pass 1, not journey discovery's element selection). Also: resolver
emits non-existent locators ("First product link") instead of skipping — needs a
DOM-existence guard.

**Proposed fix (next session):**
1. Structural hint in journey discovery: "product" descriptions should prefer
   product-card selectors (img/a/div inside `.product` containers) over nav links.
2. DOM-existence guard: resolver candidates must exist in scraped data before
   emitting a locator (prevents `text=First product link`).
3. Quantity: add a fallback mapping FILL-quantity → +/- button clicks when no
   fillable input exists.

**Mitigations available now:** explicit journey steps ("click on product name 'Blue Top'"),
credential profile for checkout, cart-seeding for state-dependent pages.


### B-004 — Ambiguous locators when same label exists on multiple forms (✅ FIXED by architecture evolution)
**Status:** ✅ Fixed — skeleton-first resolver pipeline emits ID/data-test/href selectors via `build_robust_locator()`, not `get_by_label()`. Multi-page scraping (AI-009) also shipped. No code change needed.

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

### B-019 — Scraper misses heading text on JS-rendered pages (✅ FIXED by AI-032 Semantic Scraper)
**Status:** ✅ Fixed — three-layer hybrid extraction (BS4 + CDP AX tree + aria_snapshot) resolves aria-labelledby cross-references and dynamically composed accessible names that BS4 alone couldn't.
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
    evidence_tracker.navigate("https://automationexercise.com/view_cart")
    pytest.skip("Skipping: unresolved placeholders for: 'Proceed to checkout'")
    evidence_tracker.assert_visible("#empty_cart", label="order summary")
```
The test jumps straight to `/view_cart`. The scraper visited that URL in a fresh session,
found an empty cart, and only `#empty_cart` elements were captured. "Proceed to checkout"
never existed in the scraped DOM → placeholder can't resolve → test skipped.

**Secondary symptom — POM duplication:** Every test in the generated file has duplicate
POM instantiations:
```python
home_page = HomePage(page, evidence_tracker)
home_page = HomePage(page, evidence_tracker)  # duplicate!
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

## 🆕 AI-037 — LV Insurance Resolution Gap Optimization

**Status:** 🟢 PHASE 3 COMPLETE 2026-07-31 — LV regeneration 62.5% → 79.2% (19/24), static eval 100%, 1928 tests pass
**Priority:** Medium (Tier 2 — Resolver Accuracy)
**Spec:** `docs/specs/FEATURE_SPEC_AI037_lv_insurance_resolution_gap.md`
**Handover:** `docs/sessions/2026-07-31_ai037_resolver_fixes.md` + `docs/sessions/2026-07-31_ai037_phase3_journey_guidance.md`
**Impact:** LV Insurance resolution 54% → 62.5% → 79.2% regeneration (resolver 100%)
**Estimated sessions:** 1-2 (2 done)

**📊 Diagnostic update 2026-07-31 (Phase 3):** Resolver-only eval shows LV Insurance at
**24/24 (100%)** — not 54%. The regeneration metric is dominated by LLM
skeleton-generation nondeterminism.

**Phase 3 findings (2026-07-31):**
1. **Ideal-skeleton experiment**: feeding the golden keys as a perfectly-structured
   skeleton through the LIVE pipeline hit 21/24 BEFORE the fix — proving the
   remaining gap was NOT the resolver's vocabulary but the LLM's step placement +
   a scraper visibility bug.
2. **Scraper visibility bug (fixed)**: `JourneyScraper._scrape_current_page` never
   revealed SPA hidden sections before capturing, so every element on a non-active
   SPA section was marked `is_visible=False` and Pass 3 hard-skipped hidden
   CLICK/FILL targets. The frozen eval data (`refresh_lv_capture.py`) applied
   `_reveal_hidden_sections` — the live journey capture didn't. Fix: mirror the
   frozen methodology inside `_scrape_current_page`.
3. **Golden validator has-text gap (fixed)**: the resolver correctly returned
   `h2:has-text("✅ Quote Generated Successfully!")` (the real heading inside
   `#quoteSuccess`) but the golden tolerance `h2:has-text('Quote Generated')`
   didn't match — Playwright `has-text` is substring semantics, the validator was
   doing exact string compare. Fix: substring equivalence in `_locators_match`.

**Phase 3 shipped (2026-07-31):**
- ✅ **Skeleton prompt journey-structure guidance** (`src/prompt_builder.py` +
  `src/prompt_utils.py`, kept byte-identical): "fill ALL fields on the current
  page BEFORE navigating (Next) to the next page; never place a step after the
  navigation that leaves its page; do NOT emit pytest.skip; use the exact labels
  from the story" — in both `build_skeleton_prompt` and
  `build_single_condition_prompt`
- ✅ **SPA reveal on capture** (`src/journey_scraper.py` `_scrape_current_page`)
  — live captures now match the frozen-capture methodology (24/24 resolver
  parity on the ideal skeleton)
- ✅ **has-text substring equivalence** (`scripts/eval/golden_validator.py`)
  + 2 regression tests (`scripts/eval/golden_validator_test.py`)

**Results (2026-07-31 Phase 3):**
- Ideal-skeleton live pipeline: 21/24 → **24/24**
- A/B UAT (`uat_tstring_prototype.py`): LEGACY **20/24**, TSTRING 16/24
  (LLM nondeterminism dominates — both prompts byte-identical)
- Official regeneration (`eval_harness.py run --regenerate`): LV **19/24 (79.2%)**
  (was 15/24 = 62.5%), theinternet 7/7, overall 56.7% → 59.7%
- Static eval: 100% all sites · 1928 tests · ruff/mypy clean
- Remaining LV misses (5/24): CLICKs resolved to `#quoteSubmit` when the LLM
  emits generic descriptions ("Submit", "Next") instead of page-specific ones
  — pure skeleton sampling noise, resolver handles identical descriptions 24/24

**Anti-goal (confirmed):** do NOT add an insurance vocabulary list to
`TOKEN_EXPANSIONS` — it duplicates the DOM's own label text and doesn't scale
across domains. Phase 3 verified the pipeline itself resolves 24/24 when the
skeleton is correctly structured.

**Follow-up options (future):**
- If regeneration stability matters for CI: run skeleton generation with
  `temperature=0` (Phase 1d already does this) or add a deterministic
  skeleton→golden-alignment post-pass
- saucedemo/automationexercise regeneration scores fluctuate with LLM sampling
  — static gate stays 100%

### ✅ Shipped 2026-07-31 (Phase 1-2) — all structural, NO vocabulary list

- **Radio/checkbox label capture** (`src/scraper.py`) — radios wrapped in `<label>`
  get accessible_name ("Social, Domestic & Pleasure" was previously lost)
- **Clickable div capture** (`src/scraper.py`) — divs with explicit id kept even
  without direct text (`#productCar`, `#paymentFull`) — B-025 click-target premise
- **`<strong>` in display_tags** (`src/scraper.py`) — `#quoteRef` was never captured
- **Synthetic ARIA marker** (`src/scraper.py`) — Pass-2 containers flagged `synthetic_id`
- **Radio locator format** (`src/locator_builder.py`, `scripts/eval/eval_resolver.py`)
  — `input[name][value]` disambiguates radio groups
- **Quote-agnostic locator normalization** (`scripts/eval/golden_validator.py`)
- **camelCase in `get_words()`** (`src/semantic_matcher.py`) — `#vehicleReg` → "vehicle Reg"
- **Pass 1 synthetic skip** (`src/element_matcher.py`) — synthetic groups no longer
  win fast-text over real radios
- **Radio CLICK bonus + synthetic exclusion** (`src/placeholder_scorers.py`)
- **Proportional text bonus + punctuation normalisation** (`src/placeholder_scorers.py`)
- **`scripts/eval/refresh_lv_capture.py`** (new) — journey-state capture for frozen eval data
- 15 new tests (`tests/test_scraper_ai037.py`, `tests/test_ai037_resolver_fixes.py`)

**Results (2026-07-31):**
- Resolver eval (frozen data): LV **24/24 (100%)**, overall **59.7%** (was 58.2%), no regression elsewhere
- Full regeneration UAT: LV **15/24 (62.5%)** (spec baseline 54%), overall 56.7%
- Static eval 100% · 1928 tests · ruff/mypy clean

### ✅ Phase 3 (COMPLETE 2026-07-31): skeleton journey-structure guidance

Shipped: prompt journey guidance (both skeleton + single-condition prompts) +
SPA reveal-on-capture fix in `JourneyScraper._scrape_current_page` + has-text
substring equivalence in `golden_validator.py`. Result: LV regeneration
15/24 → 19/24 (79.2%), ideal-skeleton pipeline 21/24 → 24/24.
See `docs/sessions/2026-07-31_ai037_phase3_journey_guidance.md` for full detail.

**Original problem statement:** The remaining LV gap is NOT the resolver (100% on
identical descriptions). The LLM skeleton places steps on the wrong page →
wrong-page resolution. Evidence (9 misses):
`first name`/`postcode` → `#paymentFull`, `usage type`/`Add Vehicle` → `#quoteSubmit`.

**Levers:** skeleton prompt guidance in `src/prompt_builder.py` (now t-string structured):
"fill all fields on the current page before navigating; never place a field after
reaching a later page". Verify via `uat_tstring_prototype.py` / `eval_harness.py run --regenerate`.

**Anti-goal (confirmed):** do NOT add an insurance vocabulary list to `TOKEN_EXPANSIONS` —
it duplicates the DOM's own label text and doesn't scale across domains.

**What:** After the SPA scraper fix, LV Insurance resolution jumped 0% → 54%. The remaining
46% (11/24 placeholders) fail due to description-to-element mismatches — the skeleton says
"vehicle registration number" but the DOM has `#vehicleReg` labelled "Registration Number".
The resolver's token-matching pipeline lacks insurance-specific vocabulary.

**Phases:**
1. **Diagnostic** — Classify each failing placeholder into: synonym gap, description
   mismatch, scraper blind spot, scoring underflow, or page-not-found. Produce a structured
   report.
2. **Token Expansion** — Add insurance terms to `TOKEN_EXPANSIONS` in `semantic_matcher.py`
   (registration, license, occupation, scheme, premium, excess, overnight, NCD, usage).
   Wire `_split_camel_case` into `get_words()` so `#vehicleReg` → "vehicle Reg" → "vehicle
   registration".
3. **Description Cleanup** — Optional: tune skeleton prompt or post-process descriptions to
   match observed DOM labels.
4. **Scoring Tuning** — Optional: adjust thresholds/bonuses if underflow or false positives
   are detected.

**Success criteria:**
- LV Insurance linear resolution: 54% → ≥80% (19/24)
- LV Insurance graph resolution: 50% → ≥75% (18/24)
- Static eval (all 5 sites): 100% (no regression)
- Overall linear regeneration: 56.7% → ≥65%

**Related:** B-016 (synonym matching), AI-031 (resolver accuracy), AI-030 (mock site)

---

## 🆕 AI-038 — Unlimited OCR ROCm/AMD Compatibility Test

**Status:** 👤 DEFERRED 2026-08-07 — blocked by ROCm-on-Windows Python ABI ceiling; revisit when AMD ships ROCm torch for py≥3.13 or the project drops to 3.12
**Priority:** Low — future enhancement  
**Spec:** `src/ocr_backends.py` (Phase 1i)  
**Estimated sessions:** 0.5

**What:** Test Baidu's Unlimited-OCR 3B vision model on the Strix Halo AMD APU
(64GB unified memory) with a ROCm-compatible PyTorch build. The adapter is already
built (`OCR_BACKEND=unlimited-ocr`), but the model uses `trust_remote_code=True`
which may contain CUDA-specific kernels that fail on ROCm/HIP.

**Investigation 2026-08-07 — root cause found, feature deferred:**
1. **AMD installer silently skips the GPU stack on this laptop.** Its own log
   (`AMDInstallManager/Logs/CommonLibrary_Install.log_2026-8-7_8_26_42.log`) shows
   `DEBUG_ISHALOBOX registry key not found. Assuming not a HaloBox` — the
   Ryzen AI MAX+ 395 / Radeon 8060S is Strix Halo, but the installer's
   HaloBox detection failed, so it downloaded the ROCm/torch wheels
   (7.2.0.dev0, May 2026) and then **installed nothing**.
2. **No ROCm torch exists for Python 3.14 on Windows — this is the hard wall.**
   Verified across every source: the AMD Windows wheel repo
   (`repo.radeon.com/rocm/windows/rocm-rel-7.2.1`, Feb 2026 — fresher than the
   installer's 7.2.0) ships only `torch-2.9.1+rocm7.2.1-cp312-cp312-win_amd64.whl`;
   pytorch.org's ROCm index resolves no torch for 3.14; and the project venv is
   Python 3.14.5. PyTorch proper supports 3.14 (CPU + CUDA cp314 wheels exist),
   but **AMD's Windows ROCm wheels cap at cp312**. The OCR backend runs
   in-process (`get_ocr_backend()` in `src/agents/pipeline_graph.py`), so even a
   3.12 side-env install would need a subprocess bridge to be usable.
3. **Verdict per the item's own step 4** ("document limitation, keep PyMuPDF as
   default"): documented. PyMuPDF remains the OCR default; `unlimited-ocr` stays
   opt-in. Revisit when (a) AMD ships ROCm Windows wheels for py≥3.13, or (b) a
   3.12 side-env + subprocess OCR bridge is wanted, or (c) the Qwen-3.8-27B
   training work (below) already builds a 3.12/ROCm side-env worth reusing.

**Unblocking note (2026-08-07):** the fresh ROCm 7.2.1 wheels are available at
`repo.radeon.com/rocm/windows/rocm-rel-7.2.1/` for a Python 3.12 env. If the
Qwen training effort creates a dedicated 3.12 + ROCm environment, the same env
can run Unlimited-OCR via a subprocess bridge — the two deferrals share one
unblock.

**Steps (when unblocked):**
1. Install ROCm PyTorch 7.2.1 into a Python 3.12 env (replace `torch 2.13.0+cpu`)
2. Run `OCR_BACKEND=unlimited-ocr` against sample PDFs
3. If the model loads and infers successfully → enable as default for document
   mode when GPU is available
4. If custom CUDA kernels fail → document limitation, keep PyMuPDF as default

**Blocked by:** ROCm torch for Windows requires Python ≤3.12; project venv is 3.14

---

## ✅ AI-040 — Fine-Tuning Dataset Generation Tooling (TOOLING COMPLETE 2026-08-09 — training is AI-041)

**Status:** ✅ Complete (tooling + corpus + baseline shipped 2026-08-07/09); the actual training run is tracked as **AI-041**
**Priority:** Medium — enables the Qwen training effort referenced by AI-038
**Spec:** `scripts/build_finetune_dataset.py`, `scripts/synthesize_stories.py`, `training_data/`

**What:** Two scripts + a seed corpus that convert the pipeline's own artifacts into
instruction-tuning datasets for Unsloth Studio (or any SFT trainer):

- `build_finetune_dataset.py` — extracts (story → skeleton) Alpaca rows from
  `generated_tests/*/scrape_manifest.json` + the eval datasets, and (placeholder →
  locator) rows from eval golden keys. Emits `playwright_skeleton_alpaca.jsonl`
  and `playwright_resolution_alpaca.jsonl`.
- `synthesize_stories.py` — LLM-synthesizes new stories per eval site (anchored to a
  real element inventory so no hallucinations), runs the offline Phase-1 skeleton
  generator, validates through the same gates production uses
  (`normalise_placeholder_actions` → `validate_skeleton` → criteria-count check),
  and merges passing rows. `--mode linear|graph|both` (graph is deterministic,
  temp=0 — run once; linear is stochastic — rerun for diversity).

**Dataset state (2026-08-08):** 172 skeleton rows (22 generated + 7 eval + 143
synthetic), 90 resolution rows, **112 resolved-code rows** (story → resolved
test code, all 7 sites, 3464 evidence calls — from the `--resolve-and-learn`
full combo run: mocks × RAG on+off 56 passed / 6 failed, live × RAG on
20 passed / 23 failed). Verified: ruff ✓, mypy ✓, pytest ✓.

**Why it matters:** the 90 resolution pairs target AGENTS.md §13's open issue
(ASSERT placeholder resolution, 79.1% eval baseline) — a small LoRA on that set is
the fastest measurable pipeline win. The skeleton set is seed capital for a
story→code model. Both are input to the Qwen training effort AI-038 references.

**Blocker found while building (2026-08-07):** llama-server was launched with
`--ctx-size 156072` (156K context) — KV cache alone ~25 GB pinned against the
48 GB Strix Halo UMA, causing `vk::Queue::submit: ErrorOutOfDeviceMemory` on long
decodes. Relaunched at `--ctx-size 9072`; server healthy, suite green.

**B-047 found 2026-08-08 (multi-mock site_hash collision — pre-existing, protected code) — ✅ FIXED 2026-08-08:**
`domain_from_url()` in `src/rag_learn.py` stripped the port, so all localhost mock
sites (banking:8782, ecommerce:8783, lv_insurance:8781) shared one `site_hash`.
**Fix:** `domain_from_url()` now returns the full `netloc` (`host[:port]`,
lowercase, userinfo stripped) — both learn and resolve paths route through it,
so per-origin scoping is automatic; real sites (no port) are unchanged.
Regression coverage: `test_concurrent_mocks_scope_independently`,
`test_mock_ports_hash_distinctly`.

**Second root cause found while fixing B-047 — MockServer class-attribute leak
(`scripts/mock_server.py`, FIXED):** `SERVE_DIRECTORY`/`ROUTES` were base-class
attributes, so when `resolve_and_learn` started 3 mock servers in one process,
every port served the LAST-started directory (ecommerce HTML on the banking
port). This — not the site_hash alone — was the dominant contamination vector:
banking stories resolved ecommerce selectors (`#name`, `a[href="/products.html"]`,
`p:has-text("Stylish Dress")`) even in RAG-off runs. Fix: per-server handler
classes with their own `SERVE_DIRECTORY`/`ROUTES`. Regression test:
`test_multi_mock_servers_serve_own_directories`.

**Data cleanup (training quality):** 42 contaminated resolved rows
(banking_mock 25 + lv_insurance 17) purged from
`training_data/playwright_resolved_alpaca.jsonl`; re-ran
`resolve_and_learn --rag-both` for the 3 mocks → 52 clean site-correct rows
appended (122 total, 0 cross-site leaks, verified by selector-marker scan).
Purged 26 inert `site_hash=sha256("localhost")` learned patterns from the RAG
store (they could never match post-fix; store now 83 golden + 27 doc + 5
learned, all correct). **Known follow-up (evidence-backed 2026-08-09):
`learn_from_evidence` inside the pytest subprocess cannot open the Milvus
store while the resolve-and-learn parent holds it.** Controlled A/B proved:
(1) fresh process → subprocess learning works (inserted=1); (2) parent opens
store, `del` + `gc.collect()`, then subprocess → `DataDirLockedError: another
process holds the lock on evidence/rag_store.db` — the Milvus-lite lock is
held for the parent's ENTIRE lifetime, so EVERY subprocess hook in a
resolve-and-learn run fails silently (the conftest try/except swallows it).
The orchestrator opens the store on the first RAG-on pass (retriever
retrieve), so RAG-off passes are also blocked for the rest of the process.
Observed: learned count 27 → 27 across the 2026-08-08 3-mock re-run despite
27 passing tests; an instrumented single-file run (no holder) learned OK and
hit-bumped an existing pattern (hits 1→2). The historical 17→27 growth
provenance (resolved 2026-08-09): the 17-pattern baseline pre-dated the
2026-08-07/08 resolve-and-learn sessions — it came from prior uncontended mock
executions (2026-08-04 session's self-healing demo artifact `CLICK 'Cart link'
→ a[href="/cart.html"]` documented in
`docs/sessions/2026-08-04_consumer_config_and_self_learning_rag.md`, plus
eval-006's "8/8 execution passed" and earlier eval/UAT mock runs — the same
UAT / eval `--run` / verify_production phases cited below). The +10 (17→27)
was learned IN the 2026-08-07/08 session by the one uncontended standalone
ecommerce test (mock server up, no parent store-holder); the batch and
full-combo resolve-and-learn runs contributed 0 (lock-blocked). All 26 purged
patterns share `sha256("localhost")` because B-047's port-stripping was live
throughout — regardless of which session produced them, they were inert
post-fix, so the purge was correct. Fix
candidate: parent-side sweep of `evidence/*.evidence.json` sidecars after each
site's executions (parent calls `learn_from_evidence` itself — no lock
contention), ~30 lines in `scripts/synthesize_stories.py`.

**Completed follow-ups (2026-08-09):** dataset cleaned (--clean filter, 55
hallucinated-login rows dropped), skeleton prompt fixed (DO-NOT-INVENT-AUTH),
login URL resolution fixed, ecommerce skeletons regenerated, model-level
baseline captured with full reproducibility envelope. Full runbook in
`docs/sessions/2026-08-09_unsloth_training_runbook.md`.

**Next steps (now tracked as AI-041):**
1. Run the Unsloth Studio QLoRA training (see runbook §4)
2. Re-run `eval_model_baseline.py` against the fine-tuned model; compare
3. Decide where the fine-tuned model plugs into the pipeline (skeleton vs resolver)
4. ✅ (B-047) port-aware site_hash + MockServer multi-server fix (2026-08-08)

---

## 🆕 AI-041 — Unsloth Studio QLoRA Training Run (❌ FAILED / CLOSED 2026-08-11)

**Status:** ❌ failed — training worked (Qwen3.6-27B 4-bit QLoRA, loss 0.94→0.081) but the GGUF export never completed; no usable model produced; all artifacts deleted (2026-08-11)
**Priority:** High — the payoff for AI-040's corpus + baseline
**Spec:** Unsloth Studio (localhost:8888), `training_data/`, `scripts/eval/eval_model_baseline.py`

**Why it failed:** the GGUF export needs a 16-bit merge (~55 GB) that a 64 GB Windows box can't produce — unsloth's `merged_16bit` save doesn't merge, `merge_and_unload` doesn't exist on the Qwen3.5 architecture, memory caps at ~46 GB, disk peak needs ~110 GB. Studio's Train UI additionally flips 4-bit→16-bit for Qwen3.6 (fused-CE crash), which a direct script worked around.

**Field guide (full write-up incl. what worked + dead ends):** `docs/sessions/2026-08-10_strix_halo_27b_qlora_field_guide.md`

**Recommendation for a future attempt:** train a **14B bnb-4bit** model on this hardware (export fits: ~28 GB merge + ~9 GB GGUF) — or retry the 27B on a machine with ≥110 GB free disk AND ≥55 GB addressable memory (e.g. Linux/128 GB Strix Halo).

**What:** Fine-tune a QLoRA on the clean training corpus (158 skeleton + 96
resolved + 90 resolution rows), export to GGUF, swap into the pipeline, and
measure the before/after delta with the captured baseline.

**Runbook:** `docs/sessions/2026-08-09_unsloth_training_runbook.md` — model
choice (safetensors, NOT NVFP4/GGUF), Studio settings table, export + model
swap (no .env edit — auto-detect via /v1/models), baseline comparison.

**Hardware:** AMD Strix Halo (gfx1151) — Unsloth AMD support is FULL; training
is bitsandbytes-based QLoRA (4-bit).

**Current model baseline (before):**
`training_data/model_baseline_qwen36_27b_ud_q4_k_xl.json` — valid skeleton
100%, criteria cover 100%, hallucinated login 0%, eval static 97.9%.

**Steps:**
1. Studio: QLoRA, `Qwen/Qwen3.6-27B`, upload skeleton dataset, Train on
   Completions ON (runbook §4)
2. Export GGUF q4_k_m → `~/.lmstudio/models/unsloth/`
3. Load fine-tuned model on :8080 (pipeline auto-detects)
4. `eval_model_baseline.py` + `eval_harness.py run --mode static` → compare

---

## 👤 AI-039 — Repo Rename: TanCat (DEFERRED)

**Status:** 👤 ready-for-human — deferred by decision 2026-08-01; revisit at launch readiness
**Priority:** Medium — GTM (Phase 8)
**Estimated sessions:** 0.5

> **Why deferred:** Renaming the repo + PyPI package is disruptive once the package is
> published (users, CI, docs links depend on the name) and carries zero functional value
> pre-launch. Parked until the product is ready for launch; branding decisions (TanCat
> product name, Cat Tan Operations Ltd, domains) stay as decided.

**What:** Rename GitHub repo from `AI-Playwright-Test-Generator` to `tancat`.
Update all internal references: `pyproject.toml` (PyPI package name), README,
docs headers, script docstrings, CI badge URL. Regenerate graphify output.

**Product name:** TanCat (`pip install tancat` / `uv add tancat`)
**Holding company:** Cat Tan Operations Ltd (cattanooperations.co.uk)
**Domains acquired:** tancat.dev, cattanooperations.co.uk, cattanooperations.com

---

## ✅ AI-033 — Python T-String (PEP 750) Upgrade — ANALYSIS COMPLETE + PROMPT LAYER MIGRATED

**Status:** ✅ Complete 2026-07-31 (analysis + prompt-layer migration shipped)
**Priority:** Medium — technical debt / future-proofing
**Impact:** Prompt assembly now structured + auditable; Jinja2 blocker resolved

**What:** Evaluate and plan migration to Python t-strings (PEP 750, Python 3.14) for
internal template strings in the codebase.

**Original question:** Whether t-strings can separate LLM calls from other things
(structured rendering, audit trails, injection-aware transforms).

### ✅ Resolution — the Jinja2 blocker is NOT a blocker for the prompt path

**Critical finding disproved by implementation:** the original spec assumed
``{{CLICK:description}}`` double-brace skeleton placeholders would conflict with
t-string ``{expression}`` interpolation. In practice t-strings escape ``{{`` the
same way f-strings do — so ``t"...{{CLICK:x}}... {user_story}"`` renders literal
``{CLICK:x}`` *and* interpolates ``{user_story}`` side by side. Byte-identical to
the legacy ``.format()`` output (verified by UAT, 2886 chars, both count variants).

### ✅ Delivered 2026-07-31

- **`src/prompt_builder.py`** (new, PEP 750) — `PromptBuilder` + `RenderedPrompt`:
  renders a `Template` with per-field transforms keyed by `Interpolation.expression`,
  records structured metadata (fields, truncated, static-vs-dynamic parts),
  exposes `to_log_entry()` for structured audit logging. LangChain-parallel:
  declare template in code, bind variables, render — no runtime template parsing.
- **`build_skeleton_prompt()`** — t-string skeleton prompt, byte-identical to legacy.
- **`build_single_condition_prompt()`** — t-string single-condition prompt. Fixes a
  latent inconsistency: the legacy function sent literal `{{CLICK:...}}` (double
  braces) to the LLM while the main skeleton prompt sent `{CLICK:...}`. Now both
  render single braces (parser accepts both).
- **Wired into `src/test_generator.py`** `_generate_skeleton_single_call` and
  **`src/orchestrator.py`** `_generate_single_condition_fragment` — both now log
  `llm_call=... fields={...}` structured audit entries (prompt text to the LLM,
  metadata to the audit trail — the "separate LLM calls from other things" pattern).
- **`tests/test_prompt_builder.py`** (13 tests) — byte-identity, brace survival,
  per-field truncation, audit metadata. Full suite: 1913 passed.
- **UAT** (`scripts/eval/uat_tstring_prototype.py` + `scripts/eval/generated_tests/`)
  — prompts byte-identical; post-wiring regeneration variance (LEGACY 54.2→50%,
  TSTRING 50→37.5%) confirmed to be LLM skeleton sampling, not prompt-path change.

**Not migrated (deferred, separate work):** Streamlit HTML blocks, evidence/report
generation templates — no prompt-assembly benefit; double-brace skeleton
placeholders were the only compatibility question and it is resolved.

**Files:**
- `src/prompt_builder.py` (new)
- `src/test_generator.py` (wired)
- `src/orchestrator.py` (wired)
- `tests/test_prompt_builder.py` (new)
- `scripts/eval/uat_tstring_prototype.py` (new)

**Estimated sessions:** 1 (analysis) + 1 (migration)

**Background:** T-strings (`t"..."`) are a new string type introduced in Python 3.12 that:
- Provide lazy evaluation of embedded expressions
- Offer better introspection of string structure
- Are designed for use cases where the string structure matters

**Current State:** Project requires Python 3.14+ (fully supports t-strings). Current `.format()` usage:
- `src/agents/generator.py` — GENERATOR_USER_PROMPT_TEMPLATE
- `src/agents/planner.py` — PLANNER_USER_PROMPT_TEMPLATE
- `src/test_generator.py` — `get_skeleton_prompt_template()`
- `src/prompt_utils.py` — multiple template strings

**⚠️ Critical Finding — Jinja2 Conflict:**
The project uses Jinja2-style double-brace placeholders (`{{CLICK:description}}`, `{{FILL:...}}`, `{{ASSERT:...}}`) for LLM prompts. T-strings use `{expression}` syntax which **directly conflicts** with these placeholders.

**Where T-Strings Would Have Most Impact:**
1. **Prompt templates** (`src/prompt_utils.py`, `src/agents/generator.py`, `src/agents/planner.py`) — could enable lazy evaluation of user story/conditions
2. **HTML generation** (`src/cli/evidence_generator.py`) — cleaner string interpolation
3. **Report generation** (`src/cli/report_generator.py`) — structured templates

**Where T-Strings Won't Work (Without Major Changes):**
1. **Skeleton generation** — `{{CLICK:description}}` syntax conflicts with t-string `{expression}` syntax
2. **Credential substitution** (`src/journey_models.py` `substitute_templates()`) — uses `{{username}}`/`{{password}}` pattern
3. **Streamlit UI HTML blocks** — inline HTML with Jinja2-style interpolation

**What We're Waiting For:**
1. **Decision on Jinja2 migration** — Either:
   - Migrate to Jinja2 templates (breaks current LLM prompt format)
   - Use alternative placeholder syntax (e.g., `{{{description}}}` or `$description`)
   - Keep double-brace for LLM prompts, use t-strings only for internal templates
2. **Jinja2 library evaluation** — If Jinja2 is adopted, assess:
   - Version compatibility with Python 3.14
   - Impact on Streamlit rendering
   - Performance for HTML report generation
3. **Migration strategy** — Need clear plan for:
   - Which templates to migrate first (high-impact, low-conflict)
   - Backward compatibility during transition
   - Testing approach for migrated templates

**Potential Approach:**
1. **Phase 1:** Use t-strings for non-LLM templates (logging, report filenames, session state)
2. **Phase 2:** Evaluate Jinja2 adoption for HTML generation (Streamlit, evidence reports)
3. **Phase 3:** Decide on LLM prompt placeholder strategy — migrate to single-brace or adopt Jinja2

**Files to Analyze:**
- `src/prompt_utils.py` — template string usage analysis
- `src/agents/generator.py` — prompt template structure
- `src/agents/planner.py` — prompt template structure
- `src/cli/evidence_generator.py` — HTML generation patterns
- `src/cli/report_generator.py` — report template patterns

**Estimated Sessions:** 1-2 (analysis + proof of concept)

---

## ✅ B-027 — Requirements with distinct concerns generate single test case instead of multiple (FIXED 2026-08-01)

**Status:** ✅ Fixed 2026-08-01 (second attempt — the original 2026-07-24 fix was REVERTED as too aggressive)
**Priority:** Medium  
**Commits:** `db77c46`, `26bb827` (REVERTED in `5071621` 2026-07-29 — naive comma-splitting mangled narrative stories and broke golden-key alignment) → real fix 2026-08-01 (uncommitted at time of writing)
**Impact:** Unstructured requirements with multiple distinct concerns (e.g. "max items, max quantity, filters") produce only one happy-path test case instead of focused boundary/functional tests

**Real fix (2026-08-01):**
1. **Prompt** — `SpecAnalyzer.SYSTEM_PROMPT` gains SPLITTING RULES: one condition per distinct concern, `boundary` for limit questions, DO NOT collapse/skip.
2. **Routing** — `parse_requirements_text` wraps unstructured input as a single numbered item ("1. <story>"); a single numbered criterion with multi-concern signals now routes to the LLM path instead of the deterministic 1:1 mapping.
3. **JSON hardening** — prompt forbids verbatim quoting in `source`; retry-once with CORRECTION on parse failure; partial salvage (silently dropping corrupted objects) now raises so the retry fires.
4. **Conservative fallback** — if the LLM still collapses, split on sentence boundaries only (never mid-sentence commas — the revert lesson) and tag limit sentences `boundary`.

**Verified (real LLM, exact UI flow):** user story → 3 conditions (journey happy_path + 2 boundary). 22 spec_analyzer tests, 1998 total.

**Symptom:**
When a user enters requirements like:
```
changes made to the site around maximum amount of items purchaseable, maximum quantity of items and filters.
```
The pipeline produces only one test case:
```
TC01.01    happy_path    journey_step    ...maximum amount...    Meets acceptance criteria.
```
Expected: three focused test cases:
- TC01.01 — boundary: max different items purchasable
- TC01.02 — boundary: max quantity per item
- TC01.03 — filter functionality (ordering, missing items)

**Root cause:**
1. `FeatureParser.parse()` can't parse unstructured text (no "User Story:" / "Acceptance Criteria:" format) — falls through to `return cleaned, cleaned`
2. `SpecAnalyzer._extract_numbered_criteria()` only handles numbered lists (`1. ...`), not comma-separated concerns
3. LLM collapses three distinct concerns into one "happy_path" test case

**Proposed fix:**
1. **Short term:** Update `SpecAnalyzer._extract_numbered_criteria()` to also detect comma-separated or bullet-point concern lists in unstructured text and split them into separate criteria
2. **Medium term:** Add a pre-processing step that detects multiple distinct domains (amount, quantity, filters) before sending to the LLM and requests separate test conditions per domain
3. **Long term:** Add an LLM prompt instruction: "If the spec text contains multiple distinct concerns separated by commas or conjunctions, generate one test condition per concern"

**Files to modify:**
- `src/spec_analyzer.py` — `_extract_numbered_criteria()` or LLM prompt
- `src/user_story_parser.py` — `FeatureParser.parse()` for unstructured text
- `tests/test_spec_analyzer.py` — add regression test for comma-separated specs

**Estimated sessions:** 0.5-1

---

## ✅ AI-034 — Test Table Generation (COMPLETE 2026-08-01)

**Status:** ✅ Complete — Phases 1-3 shipped 2026-08-01
**Spec:** `docs/specs/FEATURE_SPEC_AI034_test_table_preflight.md`
**Note:** Pre-flight resolution reporting stripped from spec 2026-07-31 — the resolver already surfaces failures via `pytest.skip()` + evidence (AI-028).

**What:** A Test Table between Living Test Plan and skeleton generation. The LLM
expands each condition into one or more concrete test rows (e.g., "4 filters" →
4 rows); the tester reviews/edits/confirms rows before one skeleton is generated
per row.

**Delivered:**
- **Phase 1** — `src/test_table.py` (NEW): `TestRow`/`TestTable` data model + CRUD
  (add/remove/update/confirm per-row & per-condition), `TestTableExpander` (LLM
  expansion, 1-row-per-condition fallback on LLM failure, cap `DEFAULT_MAX_ROWS_PER_CONDITION=10`),
  `build_table()`, `apply_editor_rows()`. 33 unit tests.
- **Phase 2** — editors in **both** UIs: Streamlit `🧪 Test Table` expander
  (data_editor + Save/Confirm-All) and CLI "Expand into Test Rows" menu flow
  (`build_test_table_interactive`); LTP gains a disabled "Tests" column via
  `plan_rows_from_plan(plan, test_table)`.
- **Phase 3** — one skeleton per confirmed row: `table_to_conditions()` converts
  confirmed rows → `TestCondition`s (id=row.id, text=intent+target); wired into
  `reviewed_conditions` (Streamlit) and `_select_conditions_for_generation()` (CLI).
- **UAT** — `scripts/uat/uat_test_table.py` (real LLM): 2 conditions → 8 rows → 8
  skeleton functions (1:1, no skips). UI-verified: 9 rows → 9 test functions, live run.
- **Regressions:** none — full suite 1998 passed, static eval 100%.

---

## 🟡 Active Improvements (Prioritised)

## 📌 LangGraph Pipeline — Dormant / Not Wired into User Flow (documented 2026-08-01)

**Status:** 📌 Documented — no code change required
**Related:** Phase 1 Multi-Agent (ROADMAP), `src/agents/pipeline_graph.py`

**Finding (2026-08-01):** The Phase 1 Multi-Agent LangGraph pipeline
(`PipelineGraph`, `TestOrchestrator.run_pipeline_via_graph()`) is built and
unit-tested but **NOT active for users**:

- The user-facing path (Streamlit, CLI, `scripts/uat.py`) always calls
  `TestOrchestrator.run_pipeline()` — the **linear** pipeline (single-call
  skeleton → scraper → resolver).
- The graph is reachable only via `eval_harness.py run --use-graph` and its
  own unit tests.
- `langgraph` is a **core dependency** — graph tests run locally AND in CI
  (71/71 pass). The `pytest.importorskip` guards only degrade gracefully in
  minimal installs.
- Code comments previously contradicted each other (default-on vs opt-in) —
  corrected 2026-08-01 in `src/orchestrator.py` + `src/test_generator.py`.
- Doc-mode (`input_mode="document"`, PDF/Markdown parsing + persona routing)
  exists in the graph but has **no UI/CLI entry point** — only tests exercise it.

**Impact on results:** None for published numbers — static eval (100%) and
regeneration eval use the linear path by default, matching what users run.
Graph tests run in CI (langgraph is core) and pass 71/71.

**Decision:** Linear remains the production path; the graph is experimental and
opt-in (reachable via `eval --use-graph` + unit tests). Revisit options:
(1) wire the graph in as default, (2) add a user-facing doc-mode entry
(PDF → LTP conditions).

### ✅ AI-009 — Multi-Page Scraping ✅ Phase A COMPLETE, ✅ Phase B COMPLETE (2026-05-13)
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


