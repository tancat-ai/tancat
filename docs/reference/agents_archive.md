# AGENTS.md Archive — Reference Sections

> This file contains reference/historical sections removed from AGENTS.md to reduce
> context window usage. LLM agents should only read specific sections when needed.

---

## §4 — Full Project Structure

```
AI-Playwright-Test-Generator/
├── streamlit_app.py             # Streamlit UI — primary entry point
├── launch_ui.sh                 # Start UI only (general use)
├── launch_dev.sh                # Start UI + mock insurance site (dev/demo only)
├── launch_cli.sh                # Start interactive CLI via python -m cli.main
├── pytest.ini                   # testpaths = tests (NOT generated_tests)
├── pyproject.toml               # Dependencies — managed by uv
├── .pre-commit-config.yaml      # ruff + ruff-format + mypy
├── cli/                         # CLI module (argparse-based)
│   ├── main.py                  # Supported CLI entry point (366 lines after refactor)
│   ├── color.py                 # ANSI colour helpers
│   ├── config.py                # AnalysisMode, ReportFormat enums
│   ├── input_parser.py
│   ├── menu_renderer.py         # Menu rendering functions
│   ├── pipeline_runner.py       # Pipeline execution from CLI
│   ├── report_generator.py
│   ├── run_results_display.py   # CLI structured run results (metrics, table, failure classification)
│   ├── session.py               # CLI session state dataclass
│   └── test_case_orchestrator.py
│   └── evidence_generator.py
├── docs/                        # Documentation hub
│   ├── specs/
│   ├── ARCHITECTURE.md
│   ├── PROJECT_KNOWLEDGE.md
│   ├── PROMPT_EXAMPLES.md
│   ├── DEMO_GUIDE.md
│   ├── implementation_plan.md
│   ├── walkthrough.md
│   ├── nodes.csv                # 3D map node data
│   ├── links.csv                # 3D map link data
│   ├── session_*.md             # Session documentation
│   ├── test_suite_audit_*.md    # Test suite audit reports
│   ├── plans/                   # Implementation plans
│   └── private/                 # GTM strategy and other private docs
├── scripts/                     # Utility and UAT scripts (see scripts/README.md)
│   ├── README.md                # Scripts directory index
│   ├── 3d map/                  # 3D documentation map generation
│   │   ├── generate_3d_map.py
│   │   ├── audit_3d_map.py
│   │   └── 3d_map_data.json
│   ├── debug/                   # Diagnostic scripts
│   │   ├── debug_all.py         # Unified debug entry point
│   │   ├── debug_pipeline.py
│   │   ├── debug_saucedemo_*.py
│   │   └── debug_scoring.py
│   ├── maintenance/             # Project housekeeping
│   │   ├── cli_e2e_validation.py
│   │   └── project_sanitizer.py
│   └── uat/                     # User acceptance testing
│       └── uat_automationexercise.py
├── notebooks/                   # Interactive debugging notebooks
│   └── debug_pipeline.ipynb     # Jupyter pipeline debugger
├── src/                         # Core modules — tested via tests/
│   ├── llm_client.py            # PROTECTED
│   ├── test_generator.py        # PROTECTED
│   ├── orchestrator.py          # Core pipeline orchestrator
│   ├── pipeline_models.py       # Data models for the pipeline
│   ├── placeholder_resolver.py  # Resolves LLM generated placeholders
│   ├── placeholder_orchestrator.py # Per-page resolution
│   ├── skeleton_parser.py       # Parses basic skeletons
│   ├── scraper.py               # DOM metadata scraper
│   ├── journey_scraper.py       # Journey-aware stateful scraping
│   ├── page_object_builder.py   # Page Object Model generation
│   ├── semantic_candidate_ranker.py # Context candidate prioritization
│   ├── locator_scorer.py        # Scores locators by reliability
│   ├── evidence_tracker.py      # Captures runtime diagnostics
│   ├── evidence_loader.py       # Loads evidence JSON from test packages
│   ├── evidence_serializer.py   # Evidence JSON serialization
│   ├── form_detector.py         # Form detection and selector constants
│   ├── intent_matcher.py        # Intent classification for placeholders
│   ├── placeholder_scorers.py   # Composite scoring engine
│   ├── llm_reasoning_filter.py  # LLM reasoning text detection/stripping
│   ├── code_normalizer.py       # Code normalization transforms
│   ├── semantic_matcher.py      # Token-based semantic similarity
│   ├── screenshot_capture.py    # Screenshot capture utilities
│   ├── state_tracker.py         # DOM state tracking
│   ├── ui_pipeline.py           # Pipeline execution for Streamlit UI
│   ├── ui_renderers.py          # Streamlit rendering helpers
│   ├── url_inference.py         # URL inference from page context
│   ├── report_builder.py        # Builds report dicts
│   ├── report_formatters.py     # Renders reports (local MD, Jira MD, HTML)
│   ├── pipeline_report_service.py
│   ├── pipeline_run_service.py
│   ├── pipeline_writer.py
│   ├── file_utils.py            # save_generated_test, rename, normalise helpers
│   └── stateful_scraper.py      # State-aware scraping
├── tests/                       # Unit tests FOR the tool (not generated tests)
├── generated_tests/             # OUTPUT — tests produced by the tool
│   └── mock_insurance_site.html # Mock insurance environment
└── screenshots/                 # Screenshot evidence
```

---

## §6 — Full Environment Detail

### .env (NEVER COMMIT)
```
OLLAMA_MODEL=qwen3.5:35b
OLLAMA_TIMEOUT=300          # Must be 300 — default 60s causes timeouts
OLLAMA_BASE_URL=http://localhost:11434
```

### LM Studio model detection
When using LM Studio without `LM_STUDIO_MODEL` set, the system auto-detects the model currently loaded in memory via `/api/v0/models` (state=`"loaded"`). This avoids triggering a model reload when the user has a different model loaded than the fallback default. Set `LM_STUDIO_MODEL` only to force a specific model.

### OpenAI-Compatible (local) provider
For llama.cpp, vLLM, text-gen-webui, or any local OpenAI-compatible server. Select "OpenAI-Compatible (local)" from the provider menu to:
- Skip API key requirement (uses dummy key internally)
- Auto-detect the server by probing ports: 8080 (llama.cpp), 8000 (vLLM), 5000 (text-gen-webui)
- Auto-detect available models via `/v1/models`
- No `.env` editing required

For cloud OpenAI, select "OpenAI (cloud)" which requires `OPENAI_API_KEY`. The error message for missing API key now directs users to the local option.

### Setup
```bash
uv sync
.venv\Scripts\activate   # Windows
playwright install chromium
```

### Run UI
```bash
bash launch_ui.sh      # Your own target site
bash launch_dev.sh     # UI + mock insurance site (dev only)
```

### Run tests
```bash
pytest -n auto -x -q                   # Parallel (default) — 778 tests in ~2min
pytest -v                              # Single-process with output
pytest generated_tests/test_X.py -v    # Run a specific generated test explicitly
pytest --cov=src --cov-report=html -v  # With coverage (CI only — adds ~10min)
```

**Test Performance** — The 778-test suite runs in ~2min with `-n auto` (pytest-xdist parallel). Coverage adds ~10min overhead, so only use for CI gates, not local development.

---

## §7 — Full Common Issues Table

| Symptom | Cause | Fix |
|---------|-------|-----|
| "LLM returned empty response" | `OLLAMA_TIMEOUT` too low or `.env` not loading | Set `OLLAMA_TIMEOUT=300` in `.env`; ensure `load_dotenv()` fires before `LLMClient` init |
| `SyntaxError` on import lines in generated tests | LLM strips newlines (B-002) | `normalise_code_newlines()` is applied automatically — if missing, call it after generation |
| `strict mode violation: resolved to 2 elements` | Ambiguous label matches multiple elements | Use specific ID: `page.locator("#specificId")` instead of `get_by_label` |
| Last 2+ criteria get no generated tests | LLM truncates response | Enumerate criteria with line numbers, add explicit "DO NOT skip" instruction, show total count |
| Run/download buttons clear the page | Output in local variables lost on Streamlit rerun | Store all output in `st.session_state`; render from `.get()` not local vars |
| pre-commit fails "files modified by this hook" | ruff auto-fixed files | `git add -A` then commit again — fixes are already applied |
| `mypy no-redef` on type annotation | Variable annotated twice in try/except | Declare `var: type \| None = None` before the `try` block |
| `sync_playwright` not patchable in tests | Import inside function body | Move all playwright imports to module level |
| Generated tests fail in CI: `ERR_CONNECTION_REFUSED` | `generated_tests/` was in `testpaths` | `pytest.ini` — `testpaths = tests` only. Run generated tests explicitly. |
| Wrong venv active | Old venv from renamed project | `rm -rf .venv && uv sync && source .venv/Scripts/activate` |
| `bash` not found | Running in PowerShell | Switch to Git Bash, or: `uv run streamlit run streamlit_app.py` |
| mypy `import-untyped` for pandas | `pandas-stubs` not installed | `uv add --dev pandas-stubs` |
| mypy `import-untyped` for plotly | No official stubs exist | Add `[[tool.mypy.overrides]]` with `module = "plotly.*"` and `ignore_missing_imports = true` in `pyproject.toml` |
| mypy `grouping_mode` Literal type mismatch | `st.selectbox` returns `str`, not `Literal` | Add `# type: ignore[arg-type]` at call site (values are correct at runtime) |

---

## §11 — Enhanced Failure Diagnostics (Completed 2026-04-29)

The following improvements were added to reduce wrong locator matches and surface failure diagnostics:

- **Text-Content Validation** — `PlaceholderResolver.text_matches_description()` validates element text matches action description before accepting a match. Prevents `#subscribe` being matched for "Continue Shopping".
- **Confidence Threshold** — `PLACEHOLDER_MIN_CONFIDENCE` env var (default 0.3) rejects low-confidence matches. `PlaceholderResolver.rank_candidates()` applies +10 text-content bonus when element text matches action description. `LocatorScorer` (separate module) is used by runtime fallback (`locator_fallback.py`) and diagnostics (`failure_reporter.py`), NOT design-time resolution.
- **Page-Context Validation** — `PlaceholderOrchestrator._verify_page_context()` logs warnings when a resolved locator was scraped from a different page.
- **Evidence Loader** — `src/evidence_loader.py` loads evidence JSON from test packages for reports.
- **Enriched Reports** — All 3 report formats now include "Failure Diagnostics" section with page URL, failure note, suggested alternatives, available elements, screenshot paths.
- **CLI Debug View** — "View Failure Diagnostics" menu item in `cli/main.py`.

See `docs/plans/FEATURE_PLAN_enhanced_failure_diagnostics.md` for full details.

---

## §12 — UAT Scripts Detail

See `scripts/README.md` for a complete index of all utility scripts.

### `scripts/uat/uat_automationexercise.py` — End-to-end pipeline validation

Runs the full skeleton-first pipeline against automationexercise.com with a realistic e-commerce user story, then validates the generated code.

**Usage:**
```bash
# Use LM Studio (auto-detects loaded model, avoids GPU VRAM contention)
.venv\Scripts\python.exe scripts\uat\uat_automationexercise.py --provider lm-studio

# Use LM Studio with specific model if needed
.venv\Scripts\python.exe scripts\uat\uat_automationexercise.py --provider lm-studio --model qwen3.6-27b

# Use Ollama (when Cline is not running)
.venv\Scripts\python.exe scripts\uat\uat_automationexercise.py --provider ollama
```

**When to use:**
- After changes to placeholder resolution, scraper, or pipeline orchestration
- Before declaring a placeholder-related fix as done
- When validating the pipeline against a real multi-page e-commerce site

**CRITICAL: GPU VRAM contention** — When running through Cline, use LM Studio with the same model Cline is already using (e.g., `qwen3.6-27b`). Loading a second model (e.g., Ollama `qwen3.5:9b`) causes VRAM contention → 500 errors or truncated responses. The script uses `LLMClient.set_session_provider()` so all pipeline components share the same provider.

**Known results (2026-05-05):** 4/6 tests pass on automationexercise.com. test_04 and test_06 fail because ASSERT placeholders for "confirmation message" resolve to `.cart_quantity_delete` (delete button) instead of the actual confirmation popup. This is a resolution quality issue for ASSERT-type placeholders, not an infrastructure problem.

### `scripts/debug/debug_pipeline.py` — Debug pipeline with inspection

Stops at each phase and prints scraped data, resolution results, and generated code for inspection. Use when diagnosing why placeholders resolve incorrectly.

### `scripts/debug/debug_all.py` — Unified debug entry point

Consolidated entry point for all debug scripts. Run `--help` for available commands.

---

## §12a — Interactive Debugging: Jupyter Notebook

`notebooks/debug_pipeline.ipynb` — Interactive pipeline debugger with state preservation between cells.

**When to use (instead of CLI scripts):**
- Diagnosing why placeholders resolve incorrectly — Cell 5 shows per-token resolution with scores
- Testing selector fixes without code changes — Cell 7 scratchpad patches selectors in-place
- Inspecting scraper output — Cell 4 DataFrame shows all candidates with element details
- Iterating on ranking logic — re-run Cell 5 after editing `src/semantic_candidate_ranker.py`

**Prerequisites:**
- `nest_asyncio` package required (patches Jupyter's asyncio loop for sync Playwright)
- Run cells top-to-bottom for full trace, or re-run individual cells after changes

**Cell guide:**
| Cell | Stage | What to look for |
|------|-------|------------------|
| 1 | Setup | Import errors, asyncio conflicts |
| 2 | Config | Edit URL, story, model before proceeding |
| 3 | Skeleton | Token inventory — `{{TOKEN:description}}` only, no real selectors |
| 4 | Scraper | Candidate count, element types, JS render issues |
| 4b | Search | Filter candidates by token description |
| 5 | Resolution | Per-token status, winner selector, scores, fallback flags |
| 5b | Deep-dive | Top 10 candidates for a failing token |
| 6 | Output | Final test file, `pytest.skip()` count |
| 7 | Patch | Manual selector override without code changes |

**Advantages over `scripts/debug/debug_pipeline.py`:**
- State preserved between cells — no full re-run needed
- Pandas DataFrames with color-coded status columns
- Scratchpad patching (Cell 7) — test fixes before committing code
- Targeted candidate filtering (Cell 4b)

---

## §12b — Current Feature Specifications

| Spec | Status | Description |
|------|--------|-------------|
| `docs/specs/FEATURE_SPEC_remove_pages_needed.md` | In Progress | Replace PAGES_NEEDED with inline scrape-on-navigation |
| `docs/specs/FEATURE_SPEC_journey_scraper_silent_failure.md` | In Progress | Fix `_discover_selector` silent failure when all strategies fail |

---

## §13 — Full Known Issues: Placeholder Resolution

| Symptom | Cause | Status |
|---------|-------|--------|
| ASSERT placeholders resolve to wrong element | Resolver matches on shared attributes (e.g., `data-product-id`) rather than assertion intent | Open — needs semantic matching improvement |
| "Products link" resolves to brand product link | Scraper sees all elements on single-page app; resolver picks first match by score | Partially fixed (2026-05-08) — global best resolution reduces cross-page mismatches but same-page ambiguity remains |
| Navigation criteria generate GOTO not CLICK | "navigate" verb in user story → GOTO placeholder → direct `page.goto()` | By design but produces non-click journeys |

---

## §14 — CLI Structured Run Results (Completed 2026-06-02)

The CLI now displays structured run results matching the Streamlit UI quality:

- **Metrics line** — `render_run_metrics()` shows colored summary: `✅ 5 passed, 1 failed, 0 errors in 12.3s`
- **Results table** — `render_results_table()` renders ASCII table with test name, status badge, duration
- **Failure details** — `render_failure_details()` shows classified failure type (timeout, strict violation, assertion, navigation) with repair suggestions
- **Raw output** — `render_raw_output()` optionally expands raw pytest output
- Integrated into `cli/pipeline_runner.py` after `run_saved_test()` returns
- 31 unit tests in `tests/test_cli_run_results_display.py`

---

*Archive created: 2026-06-10*