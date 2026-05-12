# AGENTS.md — AI-Playwright-Test-Generator

> This file is the single source of truth for any AI assistant working on this project.
> Read this file in full before writing or modifying any code. Do not rely on README.md
> for rules — it is employer-facing documentation, not a ruleset.
> Cline users: also read `.clinerules` for session and MCP behaviour rules.
---

## 1. What This Project Does

Generates Playwright Python test scripts from user stories using a local LLM (Ollama).
Primary interface: Streamlit UI (`streamlit_app.py`). Secondary: CLI (`cli/main.py`, launched by `launch_cli.sh`).
Tests are written to `generated_tests/`, run via pytest, and evidence exported as Jira/HTML/JSON.

---

## 2. Non-Negotiable Rules (Read These First)

### Package Manager
- ✅ Use `uv add <package>` and `uv sync`
- ❌ NEVER use `pip install` — pip is not on PATH in this project

### Test Format
- ✅ All generated tests use **pytest sync format** with `playwright` fixtures
- ❌ NEVER generate `async def test_` or `asyncio.run()` style tests
- ❌ NEVER use native async/await Playwright API in generated tests
- Decision finalised: 2026-03-03. This is not open for discussion.

### Helper Functions
- ✅ Testable helpers go in `src/<module_name>.py`, imported into `streamlit_app.py`
- ❌ NEVER put testable functions directly in `streamlit_app.py`
- Reason: importing `streamlit_app` outside Streamlit context triggers `st.set_page_config()` crash

### Type Hints
- ✅ All functions must have full type annotations
- ❌ NEVER remove or omit type hints

### Git Hygiene
- ❌ NEVER commit `.env` — it contains secrets
- ❌ NEVER commit `__pycache__/`, `generated_tests/test_*.py`, or `coverage.xml`
- ❌ NEVER force push to `main` without explicit instruction
- ✅ Always run `ruff`, `mypy`, and `pytest` before accepting work as done
- ✅ Review `git diff --staged --stat` before every commit

---

## 3. Protected Files — Do Not Modify Without Explicit Instruction

| File | Reason |
|------|--------|
| `src/test_generator.py` | Working test generation pipeline — stable |
| `.github/workflows/ci.yml` | CI/CD configured and passing |

**Rule:** If you find a bug in a protected file, document it in BACKLOG.md and ask before editing.

### Deprecated Compatibility Entry Point

| File | Status |
|------|--------|
| `main.py` | Deprecated wrapper only. The retired pre-pipeline CLI menu was superseded by `cli/main.py`. Do not add new behavior here; route users to `python -m cli.main` or `bash launch_cli.sh`. |

## 3a. Protected Directories

| Directory | Reason |
|-----------|--------|
| `src/llm_providers/` | Provider implementations — stable after initial implementation |
| `docs/specs/FEATURE_SPEC_multi_provider_llm.md` | Multi-provider architecture spec — do not modify without explicit instruction |

**Rule:** New protected files created during the multi-provider refactor are automatically covered by this rule.

---

## 4. Project Structure

```
AI-Playwright-Test-Generator/
├── streamlit_app.py             # Streamlit UI — primary entry point
├── main.py                      # Deprecated wrapper to cli/main.py
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
│   ├── session.py               # CLI session state dataclass
│   └── test_case_orchestrator.py
│   └── evidence_generator.py
├── docs/                        # Documentation hub
│   ├── specs/                   # Feature specification documents
│   │   ├── FEATURE_SPEC_intelligent_scraping_pipeline.md
│   │   ├── FEATURE_SPEC_multi_page_scraping.md
│   │   ├── FEATURE_SPEC_multi_provider_llm.md
│   │   ├── FEATURE_SPEC_page_context_scraper.md
│   │   ├── FEATURE_SPEC_run_results.md
│   │   └── FEATURE_SPEC_AI009_phase_b.md
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
├── src/                         # Core modules — tested via tests/
│   ├── llm_client.py            # PROTECTED
│   ├── test_generator.py        # PROTECTED
│   ├── orchestrator.py          # Core pipeline orchestrator
│   ├── pipeline_models.py       # Data models for the pipeline
│   ├── placeholder_resolver.py  # Resolves LLM generated placeholders — text validation + confidence threshold
│   ├── placeholder_orchestrator.py # Per-page resolution — page-context validation
│   ├── skeleton_parser.py       # Parses basic skeletons
│   ├── scraper.py               # DOM metadata scraper
│   ├── journey_scraper.py       # Journey-aware stateful scraping
│   ├── page_object_builder.py   # Page Object Model generation
│   ├── semantic_candidate_ranker.py # Context candidate prioritization
│   ├── locator_scorer.py        # Scores locators by reliability (data-testid > id > name > aria-label > css-class > text > xpath)
│   ├── evidence_tracker.py      # Captures runtime diagnostics (failure_note, diagnosis, screenshots)
│   ├── evidence_loader.py       # Loads evidence JSON from test packages for reports
│   ├── evidence_serializer.py   # Evidence JSON serialization (extracted from evidence_tracker)
│   ├── form_detector.py         # Form detection and selector constants (extracted from journey_scraper)
│   ├── intent_matcher.py        # Intent classification for placeholders (extracted from placeholder_resolver)
│   ├── llm_reasoning_filter.py  # LLM reasoning text detection/stripping (extracted from code_postprocessor)
│   ├── code_normalizer.py       # Code normalization transforms (extracted from code_postprocessor)
│   ├── semantic_matcher.py      # Token-based semantic similarity (extracted from placeholder_resolver)
│   ├── screenshot_capture.py    # Screenshot capture utilities (extracted from evidence_tracker)
│   ├── state_tracker.py         # DOM state tracking (extracted from journey_scraper)
│   ├── ui_pipeline.py           # Pipeline execution for Streamlit UI (extracted from streamlit_app)
│   ├── ui_renderers.py          # Streamlit rendering helpers (extracted from streamlit_app)
│   ├── url_inference.py         # URL inference from page context (extracted from placeholder_orchestrator)
│   ├── report_builder.py        # Builds report dicts — merges evidence data
│   ├── report_formatters.py     # Renders reports (local MD, Jira MD, HTML) with failure diagnostics
│   ├── pipeline_report_service.py
│   ├── pipeline_run_service.py
│   ├── pipeline_writer.py
│   ├── file_utils.py            # save_generated_test, rename, normalise helpers
│   └── stateful_scraper.py      # State-aware scraping — fallback scraper in placeholder_orchestrator.py (not removed yet)
├── tests/                       # Unit tests FOR the tool (not generated tests)
├── generated_tests/             # OUTPUT — tests produced by the tool
│   └── mock_insurance_site.html # Mock insurance environment
└── screenshots/                 # Screenshot evidence
```

---

## 5. Architecture Decisions

| Decision | Choice | Do Not Use |
|----------|--------|------------|
| Test format | pytest sync + playwright fixtures | async/await standalone |
| Package manager | `uv` | `pip` |
| UI framework | Streamlit | Flask / Django / React |
| Testable helpers location | `src/` modules | `streamlit_app.py` |
| Screenshot reports | 3 formats: local `.md`, Jira `.md`, base64 HTML | single format only |
| LLM parsing | Smart hybrid: regex first, LLM only if needed | Always-LLM mode |
| LLM model | `qwen3.5:35b` (default) | — |

---

## 6. Environment

```bash
# .env (NEVER COMMIT)
OLLAMA_MODEL=qwen3.5:35b
OLLAMA_TIMEOUT=300          # Must be 300 — default 60s causes timeouts
OLLAMA_BASE_URL=http://localhost:11434
```

**Setup:**
```bash
uv sync
.venv\Scripts\activate   # Windows
playwright install chromium
```

**Run UI:**
```bash
bash launch_ui.sh      # Your own target site
bash launch_dev.sh     # UI + mock insurance site (dev only)
```

**Run tests:**
```bash
pytest -v                           # Tool's own unit tests only
pytest generated_tests/test_X.py -v  # Run a specific generated test explicitly
```

---

## 7. Common Issues — Known Fixes

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

## 8. LLM Prompt Rules (for Skeleton-First Pipeline)

When writing or modifying prompts that generate test skeletons:

- ✅ Enumerate acceptance criteria with numbers: `1. Criterion`, `2. Criterion`
- ✅ State total count: `(Total: N criteria)`
- ✅ Add explicit: `"Generate ONE skeleton function per criterion"`
- ✅ Add explicit: `"DO NOT use async def — use pytest sync format"`
- ✅ Add explicit: `"DO NOT skip, combine, or omit any criteria"`
- ✅ Add closing warning: `"All N criteria must have placeholders"`
- ✅ ALWAYS use placeholder syntax `{{{{ACTION:description}}}}` for unknown locators
- ✅ NEVER instruct the LLM to write real CSS selectors or XPath
- ✅ Add explicit: `"Use ONLY the placeholder types listed in ALLOWED PLACEHOLDERS section"`
- ❌ NEVER use XML tags in prompts — the LLM ignores them
- ❌ NEVER make prompts verbose — clear numbered requirements outperform long prose

**CRITICAL:** The skeleton pipeline uses TWO PHASES. Phase 1 generates skeletons with placeholders. Phase 2 resolves placeholders using scraped DOM data. Prompts must reflect this architecture — never ask for direct locators in Phase 1.

---

## 9. Adding New Modules

Follow this pattern for every new `src/` module:

1. Create `src/<module_name>.py` with full type annotations
2. Create `tests/test_<module_name>.py` with unit tests
3. Import into `streamlit_app.py` if needed — never define logic there directly
4. Run `ruff check src/<module_name>.py` and `mypy src/<module_name>.py` before committing
5. Move playwright imports to module level (not inside function bodies)

---

## 10. Work Session Rules (Lessons from AI Sessions)

These rules exist because of real failures. Follow them.

- **Run the app end-to-end before declaring a feature done.** An AI declared AI-001 complete without running the app — introduced 5 separate bugs.
- **One feature per session.** Mixing tools or features mid-session creates inconsistency.
- **Never commit directly.** Always: `ruff` → `mypy` → `pytest` → human reviews `git diff --staged` → then commit.
- **Give implementation AI the full project rules,** not just the spec doc.
- **Typos cause runtime errors.** After any AI-generated code, search for: common misspellings, wrong method names, mismatched class names.
- **Check class name consistency.** Past failure: module imported `EvidenceGenerator`, class was named `EvidenceGen`.
- **Coverage mapping: number-based matching before keyword fallback.** TC-001 → `test_01_*`, then keyword. Keyword-only matching causes false positives on shared words.

---

## 11. Enhanced Failure Diagnostics (Completed 2026-04-29)

The following improvements were added to reduce wrong locator matches and surface failure diagnostics:

- **Text-Content Validation** — `PlaceholderResolver.text_matches_description()` validates element text matches action description before accepting a match. Prevents `#subscribe` being matched for "Continue Shopping".
- **Confidence Threshold** — `PLACEHOLDER_MIN_CONFIDENCE` env var (default 0.3) rejects low-confidence matches. `LocatorScorer` applies +10 bonus when element text matches action description.
- **Page-Context Validation** — `PlaceholderOrchestrator._verify_page_context()` logs warnings when a resolved locator was scraped from a different page.
- **Evidence Loader** — `src/evidence_loader.py` loads evidence JSON from test packages for reports.
- **Enriched Reports** — All 3 report formats now include "Failure Diagnostics" section with page URL, failure note, suggested alternatives, available elements, screenshot paths.
- **CLI Debug View** — "View Failure Diagnostics" menu item in `cli/main.py`.

See `docs/plans/FEATURE_PLAN_enhanced_failure_diagnostics.md` for full details.

## 12. UAT Scripts

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

## 13. Known Issues — Placeholder Resolution

| Symptom | Cause | Status |
|---------|-------|--------|
| ASSERT placeholders resolve to wrong element | Resolver matches on shared attributes (e.g., `data-product-id`) rather than assertion intent | Open — needs semantic matching improvement |
| "Products link" resolves to brand product link | Scraper sees all elements on single-page app; resolver picks first match by score | Partially fixed (2026-05-08) — global best resolution reduces cross-page mismatches but same-page ambiguity remains |
| Navigation criteria generate GOTO not CLICK | "navigate" verb in user story → GOTO placeholder → direct `page.goto()` | By design but produces non-click journeys |

---

*Last updated: 2026-05-08*
*Supersedes: docs/PROJECT_KNOWLEDGE.md for LLM/AI use. docs/PROJECT_KNOWLEDGE.md remains the human reference.*
