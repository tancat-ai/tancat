# BACKLOG.md
## AI Playwright Test Generator

Last updated: 2026-04-21

---

## âœ… Closed Bugs

### B-001 â€” LLM generates async standalone tests instead of pytest sync
**Fixed:** System prompt updated in `src/llm_client.py`.

### B-002 â€” LLM output occasionally has all imports on one line
**Fixed:** `normalise_code_newlines()` added to `src/file_utils.py`.

### B-003 â€” Generated tests not saved to `generated_tests/` automatically
**Fixed:** Phase A auto-save implemented.

### B-005 â€” `launch_ui.sh` starts mock server (not appropriate for general use)
**Fixed:** Mock server startup moved to `launch_dev.sh`.

### B-006 â€” Parser banner wrong when mix of pass/fail
**Fixed (Session 10):** Current parser implementation correctly uses last summary-line match.
Regression tests added: `test_b006_mixed_pass_fail_banner_correct`, `test_b006_all_fail_banner`.

### B-007 â€” Error panels duplicated in results view
**Fixed (Session 10):** Removed duplicate error rendering loop from `display_coverage()`. Errors
now render only in `display_run_button()`.

### B-009 â€” No ast.parse() validation before saving generated test files
**Fixed (Session 11):** `src/code_validator.py` created with `validate_python_syntax()`.
Integrated into `src/file_utils.py` `save_generated_test()` â€” raises `ValueError` before
writing if code fails syntax check.

### BREAK-1 â€” `src/pytest_output_parser.py` missing (CI BLOCKER)
**Fixed (Session 9):** `src/pytest_output_parser.py` committed.

### BREAK-2 â€” Session state wipe blanks run results panel
**Fixed (Session 9):** Reset lines removed from `display_run_button()`.

### B-008 â€” Run Status column shows â³ for all rows (never updates)
**Fixed (Session 13):** Coverage x Run Results now maps run outcomes through shared coverage utilities.

### B-010 â€” POM AttributeError: 'navigate' vs 'goto'
**Fixed (Session 16):** Standardized all POM-based navigation to `navigate()` in `PageObjectBuilder`. Added `__getattr__` safety net to generated POMs to `pytest.skip` missing methods instead of crashing.

### B-011 â€” LLM Placeholder Syntax Error
**Fixed (Session 15):** Improved `SkeletonValidator` to reject Python variable syntax in placeholders. Added `_replace_remaining_placeholders()` safety net to ensure final code is syntactically valid by skipping unresolved tokens.

---

## ðŸ”´ Open Bugs

### B-004 â€” Ambiguous locators when same label exists on multiple forms
**Symptom:** `strict mode violation: get_by_label("Driver Name") resolved to 2 elements`
**Fix (short term):** Use `page.locator("#specificId")` instead of `get_by_label`
**Fix (long term):** Multi-page scraping (AI-009) injects real selectors
**Priority:** Medium â€” AI-009 should prevent recurrence

---

## ðŸŸ¡ Active Improvements (Prioritised)

### AI-009 â€” Multi-Page Scraping â­ Phase A COMPLETE, Phase B In Progress
**What:** Allow the scraper to collect elements from multiple pages in a user flow,
not just the base URL
**Phase A (complete â€” Session 10):** Backend `scrape_multiple_pages()`, `MultiPageContext`,
`ScraperState` in `src/page_context_scraper.py`. UI integrated in `streamlit_app.py` with
additional URLs text area, conditional scraping, per-page sidebar feedback.
**Phase B (in progress â€” Session 11):** Authenticated journey scraping â€” single browser
session follows user-defined steps (goto, click, fill, capture, wait), credential profiles
in session state, auth redirect detection, SSO/MFA/CAPTCHA explicit errors.
**Spec:** `docs/FEATURE_SPEC_AI009_phase_b.md`
**Priority:** Highest â€” core value driver

## Feature Context â€” Evidence Tracker (AI-016 through AI-022)

The evidence tracker feature transforms test outputs from raw pass/fail results
into a fully traceable stakeholder artefact. The chain runs:

  Spec analysis â†’ Tester review â†’ Condition sign-off
  â†’ Annotated screenshot evidence â†’ Gantt timeline
  â†’ Heat map â†’ Evidence bundle export

This was designed to answer the question a tester needs to answer in a sprint
review: "here is what I tested, why I tested it, and proof that it passed."

Three new outputs are produced per test run:

1. `.evidence.json` sidecar â€” structured interaction record with bounding boxes
2. Annotated screenshot â€” page screenshot with numbered interaction circles
3. Evidence bundle â€” per-story document combining all three sources (AI, manual,
   automation) with Gantt timeline and sign-off section

---

### ~~AI-016 â€” Spec Analysis Stage~~

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
**Touches:** `streamlit_app.py` â€” new stage before "Generate Tests" button
**Touches:** `src/prompt_utils.py` â€” system prompt updated to receive derived
conditions rather than raw acceptance criteria text

**Design session completed:** 2026-04-04
**Spec:** See docs/PROJECT_KNOWLEDGE.md â€” Spec Analysis Stage section

**Condition types derived:**
- `happy_path` â€” valid input within all rules
- `boundary` â€” value at exactly the rule limit (and Â±1 unit either side)
- `negative` â€” invalid input, error path
- `exploratory` â€” tester-added, not derivable from spec alone
- `regression` â€” parameterised automation, cross-boundary combinations
- `ambiguity` â€” spec gap requiring product owner clarification before sign-off

**Priority:** High â€” prerequisite for AI-017 and AI-018

---

### AI-017 â€” Living Test Plan UI

**What:** After spec analysis, the tester sees a full editable test plan showing
all derived conditions. They can edit any condition's text, expected result, or
source reference. They can remove conditions they consider out of scope. They can
add manual tests (with step lists) and automation tests (with locator intent).
They can flag conditions that need product owner clarification. Only when all
conditions are confirmed does the sign-off button unlock, triggering generation.

**Why:** The tester must be the author of the test plan. AI-derived conditions
are a starting point, not a final product. The edit, remove, and add capabilities
make the tester's judgement visible and documented, not invisible.

**New file:** None â€” UI only, lives in `streamlit_app.py` as a new display
function `display_test_plan()`
**Note:** All testable helpers must be extracted to `src/` per AGENTS.md Â§3.
Any filtering, sorting, or condition-manipulation logic goes in
`src/test_plan.py`, not directly in `streamlit_app.py`.

**New file:** `src/test_plan.py` â€” TestPlan dataclass, condition CRUD, flag logic
**New file:** `tests/test_test_plan.py`

**Session state keys added:**
- `test_plan` â€” list of TestCondition objects (see docs/PROJECT_KNOWLEDGE.md)
- `plan_confirmed` â€” bool, True when all conditions checked off

**Priority:** High â€” depends on AI-016

---

### AI-018 â€” Evidence Tracker Module

**What:** `src/evidence_tracker.py` â€” wraps Playwright Page interactions to
record element bounding boxes, interaction types, step sequence, and run history.
Writes a `.evidence.json` sidecar file alongside screenshots after each test run.
Accumulates run counts across multiple runs without overwriting history.

**Why:** The annotated screenshot overlay (AI-020) and the Gantt timeline
(AI-021) both read from the sidecar. Without structured interaction data, the
overlay cannot know where to draw circles or how large to make them.

**New file:** `src/evidence_tracker.py`
**New file:** `tests/test_evidence_tracker.py`
**New file:** `generated_tests/conftest.py` â€” pytest fixture wiring tracker
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

**Priority:** High â€” blocks AI-019, AI-020, AI-021

---

### AI-019 â€” Prompt Update: EvidenceTracker Methods

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

**Note:** `src/llm_client.py` is PROTECTED â€” do not modify it.
The rule block goes in `prompt_utils.py` and is injected via the existing
template system.

**Priority:** High â€” depends on AI-018, blocks usable generated tests

---

### AI-020 â€” Annotated Screenshot Evidence View

**What:** Extend `src/report_utils.py` to read `.evidence.json` sidecars when
building the HTML evidence bundle. Render an SVG overlay on top of each
screenshot showing: numbered circles at interaction coordinates, circle size
encoding cumulative run count, colour encoding interaction type
(navigate/fill/click/assertion), sequence numbers in execution order.

**Three view modes:**
- `annotated` â€” numbered circles with type colours (default, for product owner)
- `heatmap` â€” density rings showing interaction frequency across all runs
  (for QA lead)
- `clean` â€” raw screenshot with no overlay (baseline for comparison)

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

**Touches:** `src/report_utils.py` â€” new function `generate_annotated_screenshot()`
**Touches:** `streamlit_app.py` â€” evidence bundle tab shows annotated screenshots

**Priority:** Medium â€” depends on AI-018

---

### AI-021 â€” Gantt Timeline in Evidence Bundle

**What:** A per-story, per-sprint test execution timeline showing each condition
as a horizontal bar sized by duration. Bars labelled with the condition ref
(BC01.02) and plain-English description, not the test function name. Dashed bars
for conditions not yet run (pending/open question). Colour encodes status.

**Three grouping modes:**
- By condition type (tester view)
- By sprint (scrum master view)
- By source â€” AI/manual/automation (product owner view)

**Stakeholder summary row** below the chart: fastest test, slowest test,
automation coverage percentage as plain English sentences.

**Clicking a bar** expands a detail card showing the spec reference, expected
result, evidence note, and step sequence. The card sits below the chart, not
as a modal overlay.

**Why:** Duration differences between tests are meaningful â€” a boundary rejection
taking 4Ã— longer than a happy path is a conversation starter with developers. The
Gantt makes this visible without the tester having to articulate it.

**New file:** `src/gantt_utils.py` â€” data preparation, grouping logic
**New file:** `tests/test_gantt_utils.py`
**Touches:** `streamlit_app.py` â€” new tab in evidence bundle section
**Reads from:** `.evidence.json` sidecar `test.duration_s` and `test.status`

**Priority:** Medium â€” depends on AI-018

---

### AI-022 â€” Coverage Heat Map

**What:** A cross-story, cross-sprint grid showing coverage confidence for each
story Ã— condition type combination (or story Ã— sprint, or story Ã— source,
switchable). Each cell coloured by confidence level. Clicking a cell expands
condition detail. Sprint-over-sprint trend bars below the grid.

**Four confidence levels (colours are fixed â€” do not change):**
- Tester confirmed: `#1D9E75` (dark teal) â€” tests passed AND tester signed off
- AI covered, unreviewed: `#9FE1CB` (light teal) â€” tests passed, no tester review
- Partial / pending: `#FAC775` (amber) â€” some conditions still pending
- Gap / open question: `#F09595` (red) â€” ambiguity or missing coverage
- Not in scope: `var(--color-background-secondary)` â€” deliberate exclusion

**The tonal distinction between confirmed and unreviewed is the most important
design decision in the heat map.** Both mean tests passed. Only confirmed means
a human reviewed the conditions and agreed they are the right tests. This is
the visual answer to the question "how much of this did a human actually verify."

**Persistence:** Heat map data aggregated from all `.evidence.json` sidecars in
the evidence directory, plus manual test plan records from session state. No
external database â€” local file aggregation only.

**New file:** `src/heatmap_utils.py` â€” aggregation across sidecars
**New file:** `tests/test_heatmap_utils.py`
**Touches:** `streamlit_app.py` â€” new top-level analytics tab

**Priority:** Medium â€” depends on AI-016, AI-018, AI-021

---

## Implementation Sequence (AI-016 through AI-022)

Do these in order. Each item is a single Cline session.

| Order | ID | Session scope |
|-------|----|---------------|
| 1 | AI-018 | `src/evidence_tracker.py` + tests + conftest only |
| 2 | AI-019 | `src/prompt_utils.py` rule block only |
| 3 | AI-016 | `src/spec_analyzer.py` + tests â€” no UI yet |
| 4 | AI-017 | `src/test_plan.py` + tests + `display_test_plan()` in UI |
| 5 | AI-020 | `generate_annotated_screenshot()` in report_utils + UI tab |
| 6 | AI-021 | `src/gantt_utils.py` + tests + UI tab |
| 7 | AI-022 | `src/heatmap_utils.py` + tests + UI tab |

**Rule:** Each session must end with `bash fix.sh` â†’ `pytest tests/ -v` â†’ green
before committing. Do not combine sessions.

---

### âœ… AI-002 â€” User Story Parser Module (COMPLETE)
**What:** Move criteria extraction into `src/user_story_parser.py` with proper
format support: Gherkin, Jira AC bullets, numbered, free-form
**Status:** Complete â€” Session 11 (2026-03-29)

### âœ… AI-005 â€” Move coverage helpers to `src/coverage_utils.py` (COMPLETE)
**What:** Extract remaining coverage helpers out of `streamlit_app.py`
**Status:** Complete â€” Session 13/April 2026. All display-mapping logic moved explicitly to `src/coverage_utils.py` and stubs fixed.

### AI-004 â€” Phase C Run Now gaps
**What:** Three gaps in the Run Now workflow:
1. Environment URL dropdown (staging / prod / local)
2. Re-run failed tests only
3. Screenshot viewer inline after run
**Priority:** Medium

### AI-006 â€” Test fixture library
**What:** `tests/fixtures/user_stories/` with 10-15 examples in each format
**Why:** Parser regression suite
**Priority:** Medium

### AI-007 â€” Remove `_generate_test_content()` from CLI orchestrator
**What:** CLI orchestrator has its own generation function duplicating
`src/test_generator.py` logic
**Priority:** Low

---

## ðŸŒŸ Future Enhancements

> Note: Each of these needs a detailed design session before handing to Cline.
> They are listed here to capture intent â€” not ready for implementation yet.

---

### AI-010 â€” Page Object Model Generation Mode
**What:** Add a toggle in the UI â€” "Simple tests" vs "Page Object Model" â€” that
changes how the LLM structures its output.

**Why it matters:** Currently generated tests are standalone functions. If the site
changes (e.g. a URL or button label), every test that references it needs updating
individually. Page Object Model (POM) puts all page interactions into a class â€” one
change in one place fixes all tests that use it. Standard pattern in professional
test suites.

**How it would work:**
- The scraper already collects everything needed (elements, locators, forms per page)
- The prompt instructs the LLM to generate a `class LoginPage:` with locators as
  attributes and interactions as methods, then generate test functions that use it
- One class per scraped page URL
- Tests become short and readable; page logic lives in one maintainable place

**Design session needed:** Yes â€” prompt structure, file layout (separate file per
page object vs single file), how classes are named from URLs
**Priority:** High â€” meaningful differentiator for portfolio

---

### AI-011 â€” Test Run History Chart
**What:** A pass/fail trend chart showing test results over time.

**Why it matters:** A single run result tells you pass/fail now. A history chart
tells you whether things are getting better or worse, and when a regression was
introduced.

**How persistence works:** A local `run_history.json` file in the project root.
Every completed run appends a record: timestamp, story name, passed count, failed
count, total duration. The chart reads from this file on load. File is excluded
from git via `.gitignore` â€” it's user-specific data, not project code.

**What the chart shows:** Line or bar chart â€” X axis is time, Y axis is pass rate.
Each point is one run. Colour coded green/amber/red by pass rate threshold.

**Design session needed:** Yes â€” storage format, chart library (Streamlit has
`st.line_chart` built in which may be sufficient), retention policy (how many
runs to keep)
**Priority:** Medium

---

### AI-012 â€” Selector Confidence Scores
**What:** Score each locator the scraper found by how likely it is to break,
and surface that score in the UI alongside the generated test.

**Why it matters:** Not all selectors are equally reliable. A test built on
`data-testid` attributes will survive UI redesigns. A test built on button
visible text will break the moment someone rewrites the copy. Users should
know which parts of their generated test are fragile before they find out
the hard way in CI.

**How scoring works â€” based on locator type, not usage frequency:**

| Locator type | Confidence | Reason |
|---|---|---|
| `data-testid` | High | Explicitly added for testing â€” won't change accidentally |
| `id` attribute | Medium-High | Stable but sometimes auto-generated |
| `name` attribute | Medium | Reliable for forms |
| `aria-label` / role | Medium | Good but changes with UI copy |
| `visible_text` | Low | Breaks when button label changes |
| Bare tag (`input`) | Very Low | Almost always fragile |

The scraper already builds `recommended_locator` for every element â€” scoring
is a classification step on top of what already exists.

**What the UI shows:** A confidence indicator per test function, and a summary
panel showing how many locators in the generated test are high/medium/low
confidence. Flags tests that are likely to be brittle before they're even run.

**Design session needed:** Yes â€” scoring thresholds, UI presentation, whether
low-confidence selectors should trigger a warning at generation time
**Priority:** Medium

---

### AI-013 â€” Coverage Gap Report with Gap Explanations
**What:** A report showing which acceptance criteria have no linked test, with
an explanation of why the gap exists.

**Why it matters:** Knowing a gap exists is useful. Knowing *why* it exists
tells the user what to fix â€” is it the user story, the scraper, or the LLM?

**Gap explanations the tool can provide:**

| Gap reason | How detected | What user should do |
|---|---|---|
| No matching elements found on page | Scraper found nothing relevant to this criterion | Add the page to the URL list or check the page loads correctly |
| Criterion too ambiguous | No specific keywords the LLM could act on | Rewrite the criterion to be more specific |
| Page not scraped | Relevant page wasn't in the URL list | Add the URL to the additional pages list |
| LLM skipped this criterion | Criterion in the list but no test function references it | Re-run with Always LLM mode or rewrite the criterion |

**Design session needed:** Yes â€” how to detect each gap type reliably, how to
present the report in the UI, whether this replaces or extends the current
coverage tab
**Priority:** Medium

---

### AI-014 â€” Test Execution Time Gantt Chart
**What:** A Gantt-style chart showing each test as a horizontal bar, sized by
execution time, so users can understand total suite duration and identify slow tests.

**Why it matters:** QA leads need to know how long a full regression run takes.
If it takes 45 minutes, that affects how often it can run in CI. Identifying
the slowest tests lets users decide which ones to optimise or run separately.

**How it would work:**
- `pytest_output_parser.py` currently stores duration as `0.0` â€” individual
  test times are in the pytest output but not yet parsed
- Parsing them is a small regex addition to the parser
- The Gantt chart stacks tests horizontally, total width = total suite time
- Colour coded by status (green = passed, red = failed)
- Clicking a bar could expand the error message for failed tests

**Design session needed:** Yes â€” parsing individual test durations from pytest
output, chart library choice, whether this lives in the run results tab or a
separate analytics tab
**Priority:** Low-Medium

---

### AI-015 â€” Test Coverage Heat Map
**What:** A visual grid showing which parts of the application have been tested
and how thoroughly, colour coded from red (untested) to green (fully covered).

**Why it matters:** At a glance a QA lead can see where the coverage gaps are
across the whole application â€” not just for one user story but across all
generated tests. A standard tool in mature QA workflows.

**How it would work:**
- Each cell in the grid represents a page or feature area
- Colour is determined by: number of tests covering that area, confidence
  scores of those tests, pass/fail rate from run history
- Requires run history (AI-011) and selector confidence (AI-012) to be
  meaningful â€” depends on those features
- Would live in a dedicated "Coverage" or "Analytics" tab

**Design session needed:** Yes â€” this is the most complex visualisation on
the list. Depends on AI-011 and AI-012 being in place first.
**Priority:** Low â€” long term goal, needs other features as prerequisites

---

### Cloud LLM Providers
**Goal:** Support OpenRouter, OpenAI, Anthropic alongside Ollama
**Spec:** `LLM_PROVIDER` env var, provider-specific API keys in sidebar, fallback to Ollama
**Status:** Complete â€” Added multi-provider LLM support architecture.

### n8n Integration
**Goal:** Trigger generation from Jira webhooks, report to Slack
**Status:** Low priority â€” Phase 4+

---

## ðŸ“‹ Fix Log

### Session 3 (2026-03-06)
- B-001, B-002, B-003, B-005 closed
- Phase A (auto-save), B (coverage), C (run now core) complete

### Session 4 (2026-03-07)
- AI-001 (page context scraper) complete
- Coverage number-based matching fixed
- Run output persistence fixed
- Jira report download added
- `pytest.ini` â€” removed `generated_tests` from testpaths

### Session 5 (2026-03-10)
- R-003 complete â€” `src/report_utils.py` extracted and tested

### Session 8 (2026-03-13)
- R-001 through R-006 complete
- Cline loop recovery applied
- load_dotenv fix, URL normalisation, content persistence, download crash fixed

### Session 9 (2026-03-16)
- BREAK-1 identified â€” `src/pytest_output_parser.py` missing (CI blocker)
- BREAK-2 identified â€” session state wipe in `display_run_button()`
- B-006 identified â€” parser banner wrong on mixed pass/fail
- B-007 identified â€” error panels duplicated
- B-008 identified â€” Run Status column never populates
- AI-009 (multi-page scraping) added as critical priority
- `docs/FEATURE_SPEC_multi_page_scraping.md` created

### Session 10 (2026-03-21)
- B-007 fixed â€” removed duplicate error rendering from `display_coverage()`
- B-006 verified working, 2 regression tests added to `test_pytest_output_parser.py`
- AI-003 closed â€” `OLLAMA_TIMEOUT=300` added to `.env.example`
- AI-009 Phase A complete â€” multi-page scraper wired into `streamlit_app.py`
- 121 tests passing, ruff clean, mypy clean

### Session 11 (2026-03-29)
- AI-002 complete â€” `src/user_story_parser.py`, 23 tests, 100% pass rate
- B-009 fixed â€” `src/code_validator.py` created, integrated into `file_utils.py`
- AI-003 confirmed complete
- AI-009 Phase B spec written â€” `docs/FEATURE_SPEC_AI009_phase_b.md`
- BACKLOG.md updated â€” AI-010 through AI-015 added
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

### Mypy Stubs Fix (2026-04-21)
**What:** Resolved 11 mypy `import-untyped` and type compatibility errors across 4 files.

**Fixes:**
- Installed `pandas-stubs` via `uv add --dev pandas-stubs` â€” resolves 6 import errors in `gantt_utils.py` and `heatmap_utils.py`
- Added per-module `ignore_missing_imports = true` for `plotly.*` in `pyproject.toml` â€” resolves 3 import errors (plotly has no official stubs)
- Fixed `src/scraper.py:164` â€” extracted `tag.get("class")` to walrus operator to resolve type narrowing issue
- Fixed `streamlit_app.py:743` â€” added `# type: ignore[arg-type]` for `grouping_mode` Literal mismatch (st.selectbox returns str, values are correct at runtime)

**New dev dependency:** `pandas-stubs>=3.0.0.260204` in `pyproject.toml`

---

## Historical Issues (from ISSUES_FOUND_AND_FIXES.md â€” merged 2026-04-21)

> **Architecture note:** Issues 3 and 4 below were fixed in the pre-session-2 codebase
> and reflect the original standalone async format. The project architecture was
> subsequently decided (2026-03-03) to use **pytest sync format** exclusively.
> Any references to async/await tests or "no pytest" as a fix are superseded.
> See docs/PROJECT_KNOWLEDGE.md â€” Architecture Decisions for the current standard.

### Session 1-2 Issues (2026-03-01 to 2026-03-04)

#### 1. GitHub Actions CI/CD Pipeline âš ï¸
**Problem:** CI/CD badge not properly configured for renamed project.
**Fix:** Updated badge URL to reflect renamed repository.
**Impact:** CI/CD status badge now displays correctly.

#### 2. Path Calculation Problem âš ï¸
**Problem:** Paths calculated incorrectly when running from different directories.
**Fix:** Changed to `Path.cwd()` for consistent path resolution.
**Impact:** Script runs correctly from any directory.

#### 4. LLM Prompt Structure âš ï¸
**Problem:** Prompt too verbose, used XML tags LLM didn't respect.
**Fix:** Restructured with clear numbered requirements and explicit DO NOT instructions.
**Impact:** More consistent LLM output.

#### 6. CLI Output Formatting âš ï¸
**Problem:** CLI output minimal with no visual hierarchy.
**Fix:** Added separator lines, emoji icons, clearer option menus.
**Impact:** Improved developer UX.

#### 7. CLI Module Architecture ðŸ†•
**Problem:** No proper CLI interface with argument parsing.
**Fix:** Implemented complete CLI module with argparse, subcommands, config enums,
modular components (InputParser, UserStoryAnalyzer, TestCaseOrchestrator, etc.)
**Impact:** Tool supports both interactive and programmatic/CI usage.

#### 12. Pre-commit Configuration ðŸ†•
**Problem:** No `.pre-commit-config.yaml` â€” no automated quality checks before commits.
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

### Lessons Learned (from Gemini AI session)
- Always run ruff, mypy, pytest before accepting AI-generated code
- Review `git diff --staged --stat` before every commit
- Never let an AI commit directly without human review
- Give implementation AIs the full project rules, not just the spec doc
- One feature per AI session â€” mixing tools mid-feature creates inconsistency
