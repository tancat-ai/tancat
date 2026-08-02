# Session — 2026-08-02 (continued): Semantic layer (page-load, dialog scoping, polarity) + CLI quality + eval harness gap (shipped)

## Summary

Continued from the 2026-08-02 session doc's "Open work". Shipped the first three
semantic-layer items (page-load assertions, dialog-action scoping, assertion-state
polarity), then — after the user challenged the testing methodology ("have you
generated and run tests via the cli and reviewed the output?") — ran the real CLI
end-to-end and fixed 5 issues it surfaced (table truncation, log/menu interleaving,
export crash, empty export, POM→flat conversion), plus the eval-harness gap where
full-regenerate mode never executed tests.

## Shipped this session

### 1. Page-load assertions resolve correctly (the "upstream finding")

LLM-invented `{{ASSERT:home page title}}` fell through to element resolution and
matched a 200-char paragraph. Three coupled root causes:

| # | Bug | Fix |
|---|-----|-----|
| A | `_is_page_state_assertion` vetoed any description containing "title" — but the golden dataset encodes `<page> page title` → `url_assertion` 3× (eval-002 "products page title", "cart page title"; eval-003 "practice form page title" stays element — no page-state term) | Removed "title" from the element-keyword veto (`src/placeholder_orchestrator.py`) |
| B | `resolve_url` root-path bug: base URL's `path_norm=" "` substring-matched ANY multi-word description → `"cart page loaded"` resolved to the home URL with base-first `known_urls` | Root-path guard (home/start/landing/store tokens only) in both `known_urls` and discovered-URL loops (`src/placeholder_resolver.py`) |
| C | Trailing-slash mismatch: production `normalize_url` emits `to_have_url(".../")`, goldens hold the bare form → static eval only passed on stale captures | `_locators_match` compares `to_have_url` URLs trailing-slash-insensitively (`scripts/eval/golden_validator.py`) |

Prompt steering: page-state ASSERT form (`{{ASSERT:home page loaded}}` → URL check)
+ "Do NOT write `{{ASSERT:<page> title}}`" added to all skeleton templates
(`prompt_builder.py` ×2 live, `prompt_utils.py` ×2 legacy kept byte-identical,
orchestrator retry + minimal prompts).

**Production evidence**: generated `test_01_home_page_loads` → `to_have_url("https://automationexercise.com/")`.

### 2. Dialog-action scoping (Pass D)

`{{CLICK:OK}}` resolved to a hidden CSRF input — the fast-path haystack check
(`"ok" in "csrfmiddleware**TOKen**"`) returned a flat 100 with no penalties. Three
layers, all generic (no site-specific lists):

- `PlaceholderScorer.compute_element_score` CLICK fast path now applies
  `_hidden_element_penalty` (-30) + `_click_text_penalty` (-10) — parity with slow path.
- `pass2_structural_match` skips hidden/`role=hidden` for CLICK/FILL + requires ≥3-char
  substring containment ("ok" can't match "token").
- New **Pass D** (`ElementMatcher.pass_dialog_action`): dialog-intent descriptions
  (ok/okay/close/dismiss/confirm/cancel/accept/done/continue/got it, word-boundary)
  resolve against in-modal interactive elements (`in_modal` flag / dialog role),
  preferring the modal's dismissal control (`close-modal` class semantics). Falls
  through when no modal exists.

**Production evidence**: `click('OK button', selector='button.btn.close-modal')` —
the csrf pick is gone; automationexercise execution 2/7 → 5/7.

### 3. Assertion-state polarity

`assert_visible('p.text-center', label='popup closed')` asserted the opposite of
"closed". `polarity_assertion_type()` (closed/gone/disappeared/removed/hidden/
dismissed/vanished/no longer/not visible/not shown) → `toBeHidden` → `assert_hidden`
(`wait_for(state="hidden")` — hidden OR detached). Hooked at both resolution paths
(per-step + batch). Prompt rule added ("describe the ABSENCE").

**Production evidence**: generated chain
`assert_visible(...confirmation popup)` → `click('OK', selector='button.btn.close-modal')`
→ `assert_hidden('p.text-center', label='popup closed')`.

### 4. CLI fixes (found by running the real CLI, not unit tests)

Ran `scripts/cli_walkthrough.py --pass full` (spawns real `cli.main`, LLM + live
site) and reviewed the logs + artifacts. Found and fixed:

| # | Bug | Fix |
|---|-----|-----|
| D | Living Test Plan / Test Table cut text at 50 chars with `...` — useless | Both tables wrap to full terminal width (`shutil` + `textwrap`) in `src/cli/pipeline_runner.py` |
| E | `[llm_client]`/`[pipeline]` debug printed to stdout under `PIPELINE_DEBUG=1`, interleaving with menus | `LLMClient._debug` + `TestOrchestrator._debug` (and the two short-response Warnings) → stderr; scraper modules already did this |
| F | Export crashed: `'Session' object has no attribute 'story_slug'` | `Session.story_slug` property (slugify of first 50 chars of `raw_requirements`) |
| G | Export silently empty: "Tests: 0" — `ui_pipeline` stores the test-FILE path in `pipeline_saved_path`, export globbed it as a directory | file→parent-dir normalization in `export_clean_package` |
| H | Flat export produced broken code: POM imports/instantiations/calls + `evidence_tracker` refs remained; duplicate `import Page, expect, expect` | POM→flat conversion in `strip_evidence_from_test_code` (imports/instantiations removed, `_page.click(label, selector='sel')` → `page.locator('sel').click()`, idempotent `expect` import) |

Walkthrough hardening: added a `reject:` capability (fails if "Export failed"
appears — the export step previously passed while erroring, because it only checked
the "Press Enter" marker) and fixed a stale heal-flow marker that caused a 1200s
timeout ("2 test(s) still failing." → "Choice:" outcome).

**Exported flat test verified runnable**: `page.goto(...)` → `page.locator('a[href="/product_details/11"]').click()` → `expect(page.locator('#name')).to_be_visible()`.

### 5. Eval harness gap — full-regenerate never executed tests

`_load_test_files()` found nothing because `--regenerate` only produced an in-memory
code map. `EvalRunner._persist_regenerated_tests()` now writes the just-generated
code to `generated_tests/test_<site>.py` (matches the executor's glob). Full run now
executes **33 tests, 17 passed (51.5% pass rate)** — was "Tests executed: 0" every run.

## Full eval results (real LLM, regenerate)

- Static gate: **100%** all sites (matches baseline).
- Full-regenerate: resolution **65.7-67.2%** (best aggregate in DB history; prior
  full-mode runs 45-59%), test pass rate **51.5%** (eval-004 theinternet 5/5,
  eval-002 automationexercise 5/6, eval-001 saucedemo 3/6, eval-003 demoqa 4/6,
  eval-005 lv_insurance 0/10 — all SKIPPED, unresolved form fields = known B-024 class).
- Misses are the KNOWN semantic gaps: saucedemo checkout page never scraped,
  lv_insurance `<select>`/label resolution, LLM skeleton variance (±10pp).

## Verification status

- Full pytest: **2081 passed / 1 skipped** (+11 net new this session). smoke 35/35.
- ruff check + format clean; mypy `src/ cli/` clean (134 files; the 4 `eval_runner.py`
  errors are pre-existing scripts/ debt, confirmed at HEAD).
- Eval harness tests: 12 pass (`scripts/eval/eval_runner_test.py`).
- CLI walkthrough: NAV 41/41, FULL 60/60 (0 failed, incl. export with `reject` check).
- verify_production: 22/26 gates (semantic ceiling documented — unchanged).

## Note on protected files

`src/llm_client.py` is a protected file (AGENTS.md). The change is a 3-line stderr
routing fix for the CLI log-interleaving bug (debug + short-response warnings).
Flagged here per the protected-file rule; no behavior change beyond output stream.

## Open work (next session)

- LLM re-ranking with T-strings + bounded retries (open work #5, bigger refactor).
- saucedemo checkout-page scrape coverage (checkout button/continue/finish + form
  fields unresolved; the last execution-failure cluster).
- lv_insurance form-field resolution (B-024 class: scheme, postcode, ncdYears, DoB).
- Consent handling in exported clean tests (export strips dismissal; clean conftest
  has none — the exported test run hit OneTrust overlay intercepting clicks).
- `resolve_url` "checkout page loaded" gap: checkout URL not scraped → wrong fallback.
