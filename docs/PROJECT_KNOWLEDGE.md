# PROJECT_KNOWLEDGE.md

## Project Overview

**AI Playwright Test Generator** — An AI-powered tool that generates Playwright Python test scripts from user stories and produces Jira-ready evidence bundles.

**Repository:** https://github.com/lacattano/AI-Playwright-Test-Generator

**Current Status:** Active development — CI green. Streamlit UI working, LLM pipeline connected (with multi-provider support), page context scraper wired in with anchor link extraction, all report formats generating. Pipeline architecture implemented. AI-002 (user story parser) and AI-005 (coverage utils extraction) are complete.

---

## ⚠️ Known Broken Items

> No critical breaks as of 2026-03-29. BREAK-1 and BREAK-2 were resolved in session 9.
> See **Logged Bugs** in the backlog section for non-blocking issues.

---

## Tech Stack

### Core Technologies
- **Python 3.13+** — Modern Python with full type hint support
- **Playwright** — Browser automation framework (sync API only — never async)
- **pytest** — Professional test framework (pytest-playwright integration)
- **Ollama** — Local LLM serving (model user-configurable; `qwen3.5:27b` recommended)
- **Streamlit** — Non-technical user UI
- **GitHub Actions** — CI/CD pipeline
- **Codecov** — Test coverage tracking
- **uv** — Package manager (NOT pip — always use `uv add` / `uv sync`)

### Key Dependencies
```
playwright>=1.45.0
pytest>=8.0.0
pytest-playwright>=0.4.0
pytest-html
pytest-json-report
ollama>=0.1.0
openai>=1.12.0
python-dotenv>=1.0.0
requests>=2.31.0
streamlit>=1.32.0
```

---

## Architecture Decisions (FINAL)

### ✅ Test Format: Pytest (DECIDED 2026-03-03)
- **Use:** pytest-playwright with sync API
- **Don't use:** Native async/await standalone tests
- **Reason:** Professional standard, better reporting, rich ecosystem
- **Impact:** All generated tests use pytest fixtures, expect() assertions, organised test discovery

### ✅ Screenshot Link Strategy: Multi-Format (DECIDED 2026-03-03)
- **Generate automatically:** 3 formats per evidence bundle
  1. `local.md` — Relative paths for local viewing/sharing
  2. `jira.md` — Jira attachment format (`!filename.png|thumbnail!`)
  3. `standalone.html` — Base64 embedded, fully self-contained
- **Reason:** Each format serves a specific purpose; generating all three is fast

### ✅ LLM Usage: Smart Hybrid Mode (DECIDED 2026-03-03)
- **Default mode:** "Smart" (hybrid regex + LLM)
- **Decision logic:**
  - Try regex parsing first (free, instant)
  - Use LLM only if: >3 criteria found, regex finds nothing, or ambiguous keywords present
  - User-configurable: Lightweight (regex only), Smart (default), Always LLM

### ✅ UI: Streamlit (DECIDED 2026-03-05)
- **Use:** Streamlit for non-technical user interface
- **Don't use:** Flask/Django/React — too much overhead for this use case
- **Entry point:** `streamlit_app.py` — launch with `bash launch_ui.sh`

### ✅ Package Manager: uv (DECIDED 2026-03-05)
- **Use:** `uv add <package>`, `uv sync`, `uv run`
- **Never use:** `pip install` directly
- **Reason:** Project uses uv.lock; pip is not on PATH in this setup

---

## Environment Setup

### Required Environment Variables
```bash
# .env (NEVER COMMIT)
OLLAMA_MODEL=qwen3.5:27b
OLLAMA_TIMEOUT=300
OLLAMA_BASE_URL=http://localhost:11434
```

> ⚠️ `OLLAMA_TIMEOUT` is only respected if `load_dotenv()` is called **before** `LLMClient`
> initialises. This is done at the top of `streamlit_app.py`. If timeout seems ignored,
> check that no module-level `LLMClient()` instantiation happens at import time.

### Development Setup
```bash
# 1. Clone repository
git clone https://github.com/lacattano/AI-Playwright-Test-Generator
cd AI-Playwright-Test-Generator

# 2. Create virtual environment and install dependencies
uv sync

# 3. Activate venv (Git Bash / Windows)
source .venv/Scripts/activate

# 4. Install playwright browsers
playwright install chromium

# 5. Configure environment
cp .env.example .env
# Edit .env — set OLLAMA_TIMEOUT=300, OLLAMA_MODEL=qwen3.5:27b

# 6. Start Ollama (in separate terminal)
ollama serve   # if not already running as a service

# 7. Launch UI
bash launch_ui.sh
```

### Running Tests
```bash
# Run all unit tests for the tool itself
pytest tests/ -v

# Run generated tests only
pytest generated_tests/ -v

# Run with headed browser (see the browser)
pytest generated_tests/ --headed -v
```

### Commit Process
```bash
# 1. Lint + type-check
bash fix.sh        # runs ruff + mypy

# 2. Unit tests
pytest tests/ -v

# 3. Stage ALL changes before committing (pre-commit checks staged version)
git add -A
git diff --staged --stat

# 4. Commit (no backticks in message)
git commit -m "your message here"
git push
```

> ⚠️ Always `git add` fixes **before** running pre-commit or committing. pre-commit
> stashes unstaged files and checks the stale staged version — you will commit a broken
> state without realising it.

---

## File Structure

```
AI-Playwright-Test-Generator/
├── .github/workflows/
│   └── ci.yml                          # GitHub Actions CI/CD
├── cli/                                # CLI module
│   ├── config.py
│   ├── evidence_generator.py
│   ├── input_parser.py
│   ├── main.py
│   ├── report_generator.py
│   ├── story_analyzer.py
│   └── test_orchestrator.py
├── docs/                               # Architecture and session documentation
├── generated_tests/                    # Output: tests produced BY the tool
│   ├── mock_insurance_site.html        # Mock test environment
│   └── test_*.py                       # Generated test files
├── screenshots/                        # Screenshot evidence storage
├── src/
│   ├── __init__.py
│   ├── code_validator.py               # ast.parse() guard before saving tests
│   ├── file_utils.py                   # save_generated_test, rename_test_file, normalise_code_newlines
│   ├── llm_client.py                   # PROTECTED — Ollama API client
│   ├── orchestrator.py                 # Core pipeline orchestrator
│   ├── page_object_builder.py          # Builds Page Object Models
│   ├── pipeline_models.py              # Foundational data models
│   ├── pipeline_report_service.py      # Generates output reports
│   ├── pipeline_run_service.py         # Test execution service
│   ├── pipeline_writer.py              # Test writing components
│   ├── placeholder_resolver.py         # Resolves placeholders within generated scripts
│   ├── scraper.py                      # Interacts with DOM for metadata
│   ├── semantic_candidate_ranker.py    # Optimizes and ranks DOM search spaces
│   ├── skeleton_parser.py              # Handles skeleton scripts
│   ├── page_context_scraper.py         # Headless scraper, returns PageContext (subprocess-based)
│   ├── prompt_utils.py                 # _PAGE_CONTEXT_RULES, prompt assembly helpers
│   ├── pytest_output_parser.py         # parse pytest stdout → RunResult / TestResult
│   ├── report_utils.py                 # generate_local_report, generate_jira_report, generate_html_report
│   ├── test_generator.py               # PROTECTED — Test generation logic
│   └── user_story_parser.py            # parse user stories into criteria
├── tests/                              # Unit tests FOR the tool itself
│   ├── fixtures/
│   │   └── user_stories/               # PLANNED (AI-006) — 10-15 varied user story examples
│   ├── test_file_utils.py
│   ├── test_page_context_scraper.py
│   ├── test_pytest_output_parser.py
│   ├── test_report_utils.py
│   └── test_user_story_parser.py       # IN PROGRESS (AI-002)
├── .env                                # Local config (NEVER COMMIT)
├── .env.example                        # Template for .env
├── .streamlit/
│   └── config.toml                     # Streamlit theme config
├── AGENTS.md                           # LLM coding agent conventions
├── BACKLOG.md                          # Feature and bug backlog
├── fix.sh                              # Runs ruff + mypy
├── launch_dev.sh                       # Start UI + mock server (dev only)
├── launch_ui.sh                        # Start UI only
├── main.py                             # PROTECTED — CLI entry point
├── pytest.ini                          # Pytest configuration
├── pyproject.toml                      # Project deps (managed by uv)
├── streamlit_app.py                    # Streamlit UI (primary working file — NOT protected)
├── uv.lock                             # Dependency lock file
└── PROJECT_KNOWLEDGE.md               # This file
```

---

## Protected Files (DO NOT MODIFY Without Explicit Request)

| File | Reason |
|------|--------|
| `src/llm_client.py` | Ollama API client — working correctly |
| `src/test_generator.py` | Core generation logic — working correctly |
| `main.py` | CLI entry point — referenced in docs as `python -m cli.main` |
| `.github/workflows/ci.yml` | CI/CD configured and working |

**Rule:** Always ask before modifying these files.

> ⚠️ `streamlit_app.py` is **NOT** in the protected list. It is the primary working file
> and is expected to be edited frequently. Some LLM agents have incorrectly treated it as
> protected — this is wrong.

---

## Forbidden Actions (NEVER DO)

- NEVER commit `.env` files — Contains sensitive configuration
- NEVER commit `__pycache__/` — Python bytecode cache
- NEVER use `pip install` — Use `uv add` instead
- NEVER use native async format for tests — pytest sync format is decided
- NEVER remove type hints — Full type annotation is project standard
- NEVER force push to main without explicit request
- NEVER rename `generated_tests/` — Hardcoded in `main.py` and `src/test_generator.py`

---

## Key Implementation Details

### `streamlit_app.py` — Current Behaviour
- Sidebar (Settings) is always visible from page load
- LLM model selector fetches live from `ollama list` via `_get_ollama_models()`
- `load_dotenv()` is called at startup so `OLLAMA_TIMEOUT` is applied before `LLMClient` initialises
- Text area (Paste story tab) is live — no intermediate confirm button
- URL is auto-normalised: `www.foo.com` becomes `https://www.foo.com` before scraping
- Scraper result shown in sidebar: success with element count, or warning with error snippet
- Generated code + Coverage tabs persist after any button click (rendered from `session_state`)
- Three download buttons always visible: `local.md`, `jira.md`, `standalone.html`

### ⚠️ Retired Module: page_context_scraper.py

**Status:** DEPRECATED and REPLACED by the skeleton-first pipeline (see below).  
**Reason for retirement:** This scraper injects real selectors into LLM prompts via `PageContext.to_prompt_block()`. The LLM then misreads, combines, or varies these selectors — causing **locator hallucination**.

The current architecture uses a two-phase approach:
1. Phase 1 (LLM): Generates skeletons with placeholder syntax like `{{CLICK:description}}`
2. Phase 2 (Resolver): Fills placeholders from scraped DOM elements without exposing selectors to the LLM

**Do not use or restore this module.** The hallucination-prone path was removed intentionally.

---

### ⚠️ Retired: page_context_scraper.py Section Removed

The following section describing the old single-phase flow with direct locator injection has been removed as it is no longer accurate and causes confusion for new LLMs joining the project:

> **Old content that was here:**
> - Runs Playwright in a subprocess...
> - `PageContext.to_prompt_block()` formats elements as plain text for LLM prompt injection
> - etc.

This retired documentation was the source of hallucination-restoration attempts by new AI sessions.

---

### `src/prompt_utils.py` — Locator Rules
- Contains `_PAGE_CONTEXT_RULES` — rules injected into LLM prompt to guide selector generation
- **Planned additions (not yet implemented):**
  - NEVER use bare tag names as locators (e.g., `page.locator("input")`)
  - Selector priority: `data-testid` > `id` > `role+name` > `text` — never bare tags
  - Never reuse the same selector across different pages

### `src/pytest_output_parser.py` — How It Works
- `parse_pytest_output(raw: str) -> RunResult` is the single public entry point
- Parses PASSED/FAILED lines with regex, extracts inline error messages
- Collects totals from the `N passed, M failed in Xs` summary line
- `RunResult.raw_output` preserves the original string for the expander panel in the UI
- **No Streamlit imports** — safe to import in unit tests without triggering `st.set_page_config()`

### `src/report_utils.py` — Report Generators
- `generate_local_report(rows)` → `local.md` with relative screenshot paths
- `generate_jira_report(rows)` → `jira.md` with `!filename.png|thumbnail!` syntax
- `generate_html_report(rows)` → `standalone.html` with base64-embedded images
- All three expect a `list[dict]` built by `_build_report_dicts()` in `streamlit_app.py`

### `src/file_utils.py` — Key Functions
- `save_generated_test(test_code, story_text, base_url)` — saves to `generated_tests/`
- `rename_test_file(old_path, new_stem)` — renames with validation
- `normalise_code_newlines(code)` — normalises `\r\n` and `\r` to `\n`

### Coverage Analysis — How It Works
After generation, `streamlit_app.py`:
1. Extracts test function names with `re.findall(r"^def (test_\w+)", code, re.MULTILINE)`
2. For each criterion, matches by `test_NN_` prefix then falls back to keyword overlap
3. Builds `RequirementCoverage` objects stored in `st.session_state.coverage_analysis`
4. `display_coverage()` renders the Coverage tab from session state

---

## Evidence Traceability Pipeline — Overview

The tool now produces a fully traceable chain from business requirement to
proof of execution. The pipeline has two new stages before test generation
and three new output formats after it.

**New pipeline (full):**

```
Input → Spec Analysis → Tester Review + Sign-off
      → Test Generation (with EvidenceTracker) → pytest Run
      → .evidence.json sidecar written
      → Evidence Bundle (annotated screenshots + Gantt + sign-off doc)
      → Heat Map (cross-story, cross-sprint aggregation)
```

**Three new deliverables per story:**
1. Annotated screenshot — page screenshot with numbered interaction circles
2. Gantt timeline — per-condition execution bars with duration and status
3. Heat map — cross-story confidence grid for stakeholder review

**The stakeholder question this answers:** "Here is what I tested, why I
tested it, and proof that it passed." Each condition in the evidence bundle
carries the exact spec clause that drove it, the test that verified it, and
the screenshot at the moment of assertion.

---

### `src/spec_analyzer.py` — Spec Analysis Stage

Analyses raw input (functional spec, user story, or free-form text) and
derives explicit test conditions before any test is generated.

**Four analysis steps:**
1. Extract business rules (logic statements, thresholds, constraints)
2. Map boundary values (for each numeric rule: at-limit, below-limit, above-limit)
3. Surface ambiguities (spec gaps where behaviour is undefined)
4. Derive test conditions (one condition per scenario)

**Condition types:**

| Type | Description | Example (BC01) |
|------|-------------|----------------|
| `happy_path` | Valid input, all rules pass | 30×20×15cm bag accepted |
| `boundary` | Value at exactly the rule limit | 55cm longest side accepted |
| `negative` | Invalid input, error path shown | Non-numeric input rejected |
| `exploratory` | Tester-added, not spec-derivable | 999×999×999cm extreme values |
| `regression` | Parameterised, cross-boundary | Volume at 0.05m³ all dim combos |
| `ambiguity` | Spec gap requiring PO clarification | Longest-side ordering undefined |

**Key output:** `list[TestCondition]` — each condition has:
- `id` (e.g. `BC01.02`)
- `type` (from table above)
- `text` (plain English description)
- `expected` (plain English expected result)
- `source` (spec clause that drove this condition)
- `flagged` (bool — true for ambiguities)
- `src` (`ai` | `manual` | `automation`)

**Assumptions are test conditions.** The spec assumption
"all flights carry the same restrictions" generates a test: does the
calculator behave identically regardless of any ticket-type context on the
page? Assumptions are not just noted — they are verified.

---

### `src/test_plan.py` — Living Test Plan

The test plan is the tester's document. AI conditions are a starting point.

**TestPlan dataclass:**
```python
@dataclass
class TestPlan:
    story_ref: str
    sprint: str
    conditions: list[TestCondition]
    confirmed_ids: set[str]
    sign_off_notes: str
    tester_name: str
    sign_off_date: str | None
```

**Tester capabilities on the plan:**
- Edit any condition's text, expected result, or source reference
- Remove conditions considered out of scope
- Add manual tests (with step lists for a colleague to execute)
- Add automation tests (with locator intent)
- Flag conditions needing PO clarification
- Confirm each condition individually
- Sign off when all confirmed — this unlocks test generation

**Sign-off is not optional.** The generate button is disabled until
`len(confirmed_ids) == len(conditions)`. This makes the tester's review
active and documented, not passive.

**Session state keys:**
- `test_plan` — current TestPlan object (serialised to JSON for persistence)
- `plan_confirmed` — bool, True when sign-off complete

---

### `src/evidence_tracker.py` — Evidence Tracker

Wraps Playwright Page interactions to produce structured evidence records.

**Public API (these are the only methods generated tests should use):**

```python
tracker.navigate(url: str) -> None
tracker.fill(locator: str, value: str, label: str = "") -> None
tracker.click(locator: str, label: str = "") -> None
tracker.assert_visible(locator: str, label: str = "") -> None
tracker.write(status: str = "passed") -> str  # returns sidecar path
```

**What each method does internally:**
- Executes the Playwright action
- Calls `locator.bounding_box()` to get element coordinates
- Converts to `viewport_pct` (percentage of viewport width/height)
- Reads existing sidecar to increment `run_count` without overwriting history
- Appends a Step record to internal list
- `navigate()` and `assert_visible()` also call `page.screenshot()`

**Coordinate storage:**
```python
# Both stored — overlay uses pct, aggregation uses bbox
bbox:         { x, y, width, height, center_x, center_y }  # absolute pixels
viewport_pct: { x, y }  # center_x / viewport_width * 100
```

**Run history accumulation:**
- Before writing, reads existing sidecar if present
- Increments `total_runs`, `passed_runs` or `failed_runs`
- Per-step `run_count` incremented by reading previous value for that step index
- `first_run` preserved from original sidecar, never overwritten

**conftest.py fixture pattern:**
```python
@pytest.fixture
def evidence_tracker(page, request):
    marker = request.node.get_closest_marker("evidence")
    tracker = EvidenceTracker(
        page=page,
        test_name=request.node.name,
        condition_ref=marker.kwargs.get("condition_ref", "unknown"),
        story_ref=marker.kwargs.get("story_ref", "unknown"),
    )
    yield tracker
    status = "passed" if request.node.rep_call.passed else "failed"
    tracker.write(status=status)
```

**Protected files note:** `src/llm_client.py` and `src/test_generator.py`
are untouched. The tracker is injected via the conftest fixture pattern,
not wired into the generator directly.

---

### Sidecar Schema — `.evidence.json`

Schema version `1.0`. One file per test function. Written to `evidence/`
directory alongside screenshots. File named `{test_name}.evidence.json`.

**Top-level keys:**

```
schema_version  string   "1.0"
test            object   Test identity and run result
page            object   URL, viewport, screenshot paths
run_history     object   Cumulative pass/fail counts across all runs
steps           array    Ordered interaction records
```

**Step record:**

```
step            int      Execution order (1-based)
type            string   navigate | fill | click | assertion | wait
label           string   Plain English description (shown in evidence UI)
locator         string   Playwright locator expression, null for navigate
value           string   Filled value or navigated URL, null for clicks/asserts
screenshot      string   Path to screenshot taken at this step, null if none

element:
  tag           string   HTML tag name
  element_id    string   id attribute, null if absent
  test_id       string   data-testid attribute, null if absent
  bbox:         object   x, y, width, height, center_x, center_y (pixels)
  viewport_pct: object   x, y (percentage of viewport — used by overlay)

result:
  status        string   passed | failed | skipped
  elapsed_ms    int      Wall-clock time for this step
  run_count     int      Cumulative times this step has been executed
  matched_text  string   Text matched by assertion, null for non-assertions
  error         string   Error message if status is failed, null otherwise
```

**Consumer notes:**
- Evidence bundle overlay renderer reads `steps[*].element.viewport_pct`
- Heat map aggregator reads `test.status`, `test.condition_ref`,
  `test.story_ref`, `test.sprint`, `run_history.total_runs`
- Gantt timeline reads `test.duration_s`, `test.status`, `test.condition_ref`
- Screenshot annotator reads `steps[*].type` for circle colour encoding

---

### `src/prompt_utils.py` — Evidence Tracker Rules (Addition)

New constant `_EVIDENCE_TRACKER_RULES` to be added alongside existing
`_BASE_PLAYWRIGHT_RULES`, `_PAGE_CONTEXT_RULES`, `_TEST_ISOLATION_RULES`.

**Six mandatory LLM rules:**

```
1. Use evidence_tracker.navigate(url) instead of page.goto(url)
   — Records step and takes entry screenshot automatically

2. Use evidence_tracker.fill(locator, value, label=...) instead of
   page.locator(locator).fill(value)
   — Captures bounding box and value for overlay rendering

3. Use evidence_tracker.click(locator, label=...) instead of
   page.locator(locator).click()
   — Records click position, drives circle size in annotated view

4. Use evidence_tracker.assert_visible(locator, label=...) instead of
   expect(page.locator(locator)).to_be_visible()
   — Takes assertion screenshot and records matched text

5. Always add @pytest.mark.evidence(condition_ref=..., story_ref=...)
   decorator to every test function
   — Links test to condition in evidence bundle and heat map

6. Never call page.screenshot() directly
   — Tracker handles all screenshots; direct calls break sidecar registration
```

**Generated test function signature (always):**
```python
@pytest.mark.evidence(condition_ref="BC01.02", story_ref="BC01")
def test_02_boundary_longest_side_55cm(
    page: Page,
    evidence_tracker: EvidenceTracker,
) -> None:
```

---

### Annotated Screenshot — Overlay Rendering

The overlay is SVG rendered at display time over the screenshot image.
It is not baked into the PNG — the annotation layer stays interactive.

**Circle rendering formula:**
```
base_radius = 14 + min(run_count * 0.7, 20)
cx = (viewport_pct.x / 100) * container_width
cy = (viewport_pct.y / 100) * container_height
```

**Colour encoding (fixed — documented in legend):**

| Interaction type | Colour | Hex |
|-----------------|--------|-----|
| navigate | Pink-red | `#993556` |
| fill | Teal | `#0F6E56` |
| click | Blue | `#185FA5` |
| assertion | Amber | `#854F0B` |

**Three view modes:**
- `annotated` — numbered circles with type colours (product owner default)
- `heatmap` — density rings, colour by type, opacity by run count (QA lead)
- `clean` — raw screenshot, no overlay (baseline comparison)

**Hover behaviour:** Hovering a circle highlights the corresponding step in
the timeline below. Hovering a timeline row highlights the circle on the
screenshot. Both use the same `hoveredId` state variable.

**Implementation note:** The overlay must re-render on container resize.
Use a `ResizeObserver` or `window.addEventListener('resize', renderOverlay)`.

---

### Evidence Bundle — Structure

The complete per-story stakeholder document contains:

1. **Header** — story reference, sprint, tester name, date, overall status
2. **Open questions panel** — red, top of page, blocks sign-off if present
3. **Coverage summary** — 4-cell metric row (total, passed, pending, open)
4. **Coverage breakdown bars** — by source (AI / manual / automation)
5. **Gantt timeline** — execution timeline for all conditions
6. **Condition index** — scannable table with ref, badge, status per condition
7. **Full detail section** — per-condition: spec clause, expected result,
   evidence note, annotated screenshot, step timeline, manual steps if present
8. **Tester sign-off** — name, date, notes field, overall status statement

**Export formats:**
- Interactive HTML (in-tool view, fully interactive)
- Static HTML (for Jira attachment, no JS dependencies)
- PDF (via browser print — generate static HTML then instruct browser to print)

---

### Heat Map — Confidence Levels

The heat map shows coverage confidence, not just pass/fail.

**Four confidence levels (colours are fixed):**

| Level | Colour | Hex | Meaning |
|-------|--------|-----|----------|
| Tester confirmed | Dark teal | `#1D9E75` | Tests passed AND tester signed off |
| AI covered, unreviewed | Light teal | `#9FE1CB` | Tests passed, no tester review yet |
| Partial / pending | Amber | `#FAC775` | Some conditions still pending |
| Gap / open question | Red | `#F09595` | Ambiguity or missing coverage |
| Not in scope | `var(--color-background-secondary)` | — | Deliberate exclusion |

**The distinction between confirmed and unreviewed is the most important
design decision.** Both mean tests passed. Only confirmed means a human
reviewed the conditions and agreed they are the right tests to run. This
is the visual answer to "how much of this did a human actually verify."

**Three grouping dimensions:**
- By condition type — tester view (where are the boundary gaps?)
- By sprint — scrum master view (is coverage improving sprint-over-sprint?)
- By source — product owner view (how much was AI vs manual vs automation?)

**Data source:** Aggregated from all `.evidence.json` sidecars in `evidence/`
directory plus manual condition records from `test_plan` session state.
No external database required.

---

### Planned Evidence Pipeline Architecture (AI-017 to AI-022)
*Note: These files are defined in the design spec and will be created as the evidence pipeline is implemented.*

```
src/
├── spec_analyzer.py       # AI-016 — derives test conditions from spec input
├── test_plan.py           # AI-017 — TestPlan dataclass, condition CRUD
├── evidence_tracker.py    # AI-018 — wraps Playwright, writes sidecar JSON
├── gantt_utils.py         # AI-021 — Gantt data preparation and grouping
└── heatmap_utils.py       # AI-022 — cross-sidecar aggregation for heat map

tests/
├── test_spec_analyzer.py
├── test_test_plan.py
├── test_evidence_tracker.py
├── test_gantt_utils.py
└── test_heatmap_utils.py

generated_tests/
└── conftest.py            # AI-018 — evidence_tracker fixture for all tests

evidence/                  # Runtime output — gitignored
├── bc01_02_entry_143201.png
├── bc01_02_assert_143201.png
└── test_02_boundary_longest_side_55cm.evidence.json
```

**`.gitignore` addition required:**
```
evidence/
!evidence/.gitkeep
```

---

### Recurring Bugs to Watch For (Cline / LLM Loop Patterns)

These have appeared multiple times — check for them after any AI-assisted edit:

| Bug | Symptom | Fix |
|-----|---------|-----|
| Ambiguous variable `l` | ruff E741 | Rename to `line` in list comprehensions |
| `tr` redefined in inner loop | mypy error | Use `found` or `match` for inner `run_map.get()` result |
| `scrape_page_context` not unpacked | TypeError | Always use `ctx, err = scrape_page_context(url)` |
| `base_url.split(':')[1]` | list index out of range | Use `re.sub(r"[^\w]", "_", base_url)` for slugs |
| Tabs inside button block | Content disappears on rerun | Render from `session_state` outside button block |
| `import re` inside function body | ruff E402 | Move to top-level imports |
| Invented imports | ModuleNotFoundError | Verify import exists before accepting output |
| Duplicate function definitions | SyntaxError or wrong behaviour | Rebuild from last known-good output |
| Session state wipe pattern | Results blank after button click | Never set state key to None/empty after setting real value |
| LLM "it passed" without explanation | Test passing for wrong reason | Require mechanistic explanation — what exactly matched? |
| B009 linting rule confused with B-009 bug | Wrong plan from LLM | B-009 is the ast.parse validation bug ID; B009 is a flake8-bugbear rule — unrelated |

**Recovery strategy:** When Cline corrupts a file, rebuild from the last known-good output and re-apply changes cleanly. Do not attempt further incremental edits on a corrupted file.

**Cline behaviour:** Add "Stop after that" to prompts and name specific MCP tool calls explicitly. If Cline enters a death spiral: stop immediately → `git reset --hard` to last working commit → resume with scoped task.

---

## Common Issues & Solutions

### LLM Timeout / Empty Response
**Symptoms:** "LLM returned empty response", debug expander shows empty raw response  
**Cause:** `OLLAMA_TIMEOUT` too low (default 60s), or `load_dotenv()` firing after `LLMClient` initialises  
**Solution:** Set `OLLAMA_TIMEOUT=300` in `.env`; confirm `load_dotenv()` is called at the very top of `streamlit_app.py` before any imports that instantiate `LLMClient`

### Generated Tests Fail With Wrong Locators
**Symptoms:** `AssertionError: Locator expected to be visible`, invented element names like `username_input`  
**Cause 1:** Page scraper failed silently because URL was missing `https://` — now auto-added  
**Cause 2:** Scraper only captures the first page. Selectors for pages 2+ are guessed — this is the core limitation AI-009 will fix.  
**Solution short-term:** Check sidebar for scraper warning. Ensure Base URL starts with `https://`.

### venv not activating / wrong environment
```bash
rm -rf .venv
uv sync
source .venv/Scripts/activate
```

### mypy cache corruption
**Symptoms:** mypy reports errors on files that are clean  
**Solution:** `rm -rf .mypy_cache` then re-run

### Port 8501 already in use
```bash
taskkill //F //IM streamlit.exe    # PowerShell
pkill -f streamlit                  # Git Bash
```

### Ollama "address already in use"
Ollama is already running — this is fine, ignore the error.

---

## Models Available Locally

| Model | Size | Architecture | Use |
|-------|------|--------------|-----|
| `qwen3.5:27b` | ~16 GB | Dense — true 27B | **Recommended for code generation** — better quality than 35b on this hardware |
| `qwen3.5:35b` | 23 GB | MoE — ~3B active params per token | Previous default; effective reasoning ~10B dense equivalent |
| `qwen2.5-coder:1.5b-base` | 986 MB | Dense | Fast testing, ~6 sec, simpler output |

> The model is user-configurable in the sidebar via `_get_ollama_models()`. `.env`
> `OLLAMA_MODEL` sets the default. `qwen3.5:27b` is the recommended default for code
> generation quality on AMD Strix Halo (64 GB unified memory).

---

## Implementation Roadmap

### Completed

| Phase | Status |
|-------|--------|
| Phase 0: Setup & Cleanup | Done |
| Phase UI: Streamlit Interface | Done |
| AI-001: Page Context Scraper | Done |
| AI-008: Run Results Parser | Done (BREAK-1 resolved) |
| R-001 to R-006: Feature Recovery | Done (2026-03-13) |
| BREAK-1: `src/pytest_output_parser.py` missing | Fixed |
| BREAK-2: Session state wipe in `display_run_button()` | Fixed |
| AI-002: User story parser (`src/user_story_parser.py`) | Done (2026-03-29) |
| AI-003: `.env.example` updated with correct defaults | Done (2026-03-29) |
| AI-005: `src/coverage_utils.py` extraction | Done |
| B-009: `src/code_validator.py` AST guard | Done |
| AI-018: Evidence Tracker Module | Done |
| Pipeline Architecture Refactor | Done |
| Multi-provider LLM Support | Done |

### R-001 to R-006 Detail

| ID | Feature |
|----|---------|
| R-001 | Ollama model selector in sidebar |
| R-002 | Pipeline log |
| R-003 | `normalise_code_newlines()` on generated code |
| R-004 | Page context scraping wired into generation flow |
| R-005 | Three report download buttons |
| R-006 | Rename test file UI |

### In Progress

*Currently no active features in progress. Moving to next phase of evidence pipeline.*

### Logged Bugs (Non-Blocking)

> Bug IDs **must** be documented here or in BACKLOG.md. An ID that exists only in
> conversation history is invisible to LLMs in future sessions.

| ID | Symptom | Status |
|----|---------|--------|
| B-006 | Parser banner shows wrong result on mixed pass/fail runs | Logged |
| B-007 | Duplicate error panels in run results UI | Logged |
| B-008 | Run Status column never populates in results table | Logged |
| B-009 | No `ast.parse()` validation before saving generated test files — truncated LLM output saved silently | Fixed (`src/code_validator.py`) |
| E-001 | Tracker not injected | `evidence_tracker` fixture not found | Check `generated_tests/conftest.py` exists and is importable |
| E-002 | Sidecar not written on failure | Failed tests produce no `.evidence.json` | Verify `pytest_runtest_makereport` hook is in conftest |
| E-003 | Circles all same size | `run_count` always 1 | Tracker not reading existing sidecar before writing — check `_load_run_count()` |
| E-004 | Overlay coordinates wrong | Circles appear offset from elements | Using `bbox` pixels not `viewport_pct` — check renderer uses percentage coordinates |
| E-005 | LLM uses `page.goto()` | No navigation step in sidecar | System prompt missing `_EVIDENCE_TRACKER_RULES` — check `prompt_utils.py` |
| E-006 | Marker not on test function | `condition_ref` is "unknown" in sidecar | LLM not adding `@pytest.mark.evidence` — enforce in prompt rule 5 |
| E-007 | Heat map all same shade | Confirmed vs unreviewed not distinguished | Sign-off flag not being read from `test_plan` session state |
| E-008 | Evidence dir not created | `FileNotFoundError` on first run | `EvidenceTracker.__init__` must call `evidence_dir.mkdir(exist_ok=True)` |

### Backlog (Next — after B-009)

| ID | Feature | Notes |
|----|---------|-------|
| AI-004 | Phase C UI gaps (env dropdown, re-run failed, screenshot viewer) | |
| AI-006 | Create `tests/fixtures/user_stories/` with 10-15 format examples | Feeds AI-002 validation |
| AI-007 | Remove `_generate_test_content()` from CLI orchestrator | |
| AI-009 Phase A | Multi-page scraping: user-provided URL list | Prerequisite for Phase B |
| AI-009 Phase B | Multi-page scraping: Playwright-driven authenticated flow following | **Core value driver** — see note below |

> **AI-009 is the highest-priority feature.** Without multi-page scraping, all tests beyond
> page one use guessed selectors, undermining the tool's core value regardless of other
> improvements. Graceful failure is required for SSO, MFA, and CAPTCHA (out of scope with
> explicit error messages, not silent failures).

---

## Resources & Links

- **Repository:** https://github.com/lacattano/AI-Playwright-Test-Generator
- **Playwright Docs:** https://playwright.dev/python/
- **pytest Docs:** https://docs.pytest.org/
- **Ollama Docs:** https://ollama.com/docs
- **Streamlit Docs:** https://docs.streamlit.io

---

## Version History

- **2026-03-03:** Initial creation, Phase 1-4 roadmap defined, architecture decisions finalised
- **2026-03-05:** Session 2 — Streamlit UI built, uv adopted, mock site updated, BACKLOG.md created
- **2026-03-12:** Sessions 3-7 — AI-001 page context scraper, coverage mapping, run results parser, multiple bug fixes, feature recovery plan identified
- **2026-03-13:** Session 8 — R-001 through R-006 implemented, Cline loop recovery, load_dotenv fix, URL normalisation, content persistence fix, download crash fix
- **2026-03-16:** Session 9 — BREAK-1/BREAK-2 identified and fixed; `src/pytest_output_parser.py` committed; session state wipe removed from `display_run_button()`
- **2026-03-29:** Docs refresh — PROJECT_KNOWLEDGE.md updated: stale breaks cleared, models table updated (qwen3.5:27b recommended), `src/prompt_utils.py` added to file structure, B-006 through B-009 logged, AI-009 phases documented, streamlit_app.py explicitly noted as non-protected
- **2026-03-29:** AI-002 complete — `src/user_story_parser.py` and `tests/test_user_story_parser.py` committed, all tests passing. AI-003 done manually. B-009 next.
- **2026-04-04:** Design session — Evidence traceability pipeline
  - AI-016 through AI-022 designed and specced
  - Sidecar schema v1.0 defined
  - EvidenceTracker public API finalised
  - Annotated screenshot overlay rendering designed
  - Gantt timeline three-grouping-mode design finalised
  - Heat map four-confidence-level design finalised
  - Living test plan (tester-editable conditions) designed
  - Spec analysis stage (boundary derivation, ambiguity surfacing) designed
  - Evidence tracker feature block integrated into BACKLOG.md
  - Evidence pipeline implementation details integrated into PROJECT_KNOWLEDGE.md
- **2026-04-04:** Added anchor link extraction to page context scraper.
- **2026-04-05:** Added multi-provider LLM support, fixed coverage_utils stub, tightened gitignore for tmp files and PNGs, and cleaned up Cline artefacts.
- **2026-04-08:** Refactor: implemented pipeline architecture and updated dependencies.
- **2026-04-10:** Utils fix and pip to uv transitions documented.

---

*Last Updated: 2026-04-12*
*Project Status: CI green — Pipeline architecture, multi-provider LLM, Evidence Tracker (AI-018), and anchor link extraction implemented.*
*Next Phase: AI-019 → AI-022 implementation in sequence*
