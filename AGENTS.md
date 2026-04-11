# AGENTS.md — AI-Playwright-Test-Generator

> This file is the single source of truth for any AI assistant working on this project.
> Read this file in full before writing or modifying any code. Do not rely on README.md
> for rules — it is employer-facing documentation, not a ruleset.
> Cline users: also read `.clinerules` for session and MCP behaviour rules.
---

## 1. What This Project Does

Generates Playwright Python test scripts from user stories using a local LLM (Ollama).
Primary interface: Streamlit UI (`streamlit_app.py`). Secondary: CLI (`cli/main.py`).
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
| `main.py` | Working CLI entry point — stable |
| `.github/workflows/ci.yml` | CI/CD configured and passing |

**Rule:** If you find a bug in a protected file, document it in BACKLOG.md and ask before editing.

## 3a. Protected Directories

| Directory | Reason |
|-----------|--------|
| `src/llm_providers/` | Provider implementations — stable after initial implementation |
| `FEATURE_SPEC_multi_provider_llm.md` | Multi-provider architecture spec — do not modify without explicit instruction |

**Rule:** New protected files created during the multi-provider refactor are automatically covered by this rule.

---

## 4. Project Structure

```
AI-Playwright-Test-Generator/
├── streamlit_app.py             # Streamlit UI — primary entry point
├── main.py                      # PROTECTED — Interactive CLI
├── launch_ui.sh                 # Start UI only (general use)
├── launch_dev.sh                # Start UI + mock insurance site (dev/demo only)
├── pytest.ini                   # testpaths = tests (NOT generated_tests)
├── pyproject.toml               # Dependencies — managed by uv
├── .pre-commit-config.yaml      # ruff + ruff-format + mypy
├── cli/                         # CLI module (argparse-based)
│   ├── main.py
│   ├── config.py                # AnalysisMode, ReportFormat enums
│   ├── input_parser.py
│   ├── story_analyzer.py
│   ├── test_orchestrator.py
│   ├── evidence_generator.py
│   └── report_generator.py
├── docs/                        # Architecture and session documentation
├── src/                         # Core modules — tested via tests/
│   ├── llm_client.py            # PROTECTED
│   ├── test_generator.py        # PROTECTED
│   ├── orchestrator.py          # Core pipeline orchestrator
│   ├── pipeline_models.py       # Data models for the pipeline
│   ├── placeholder_resolver.py  # Resolves LLM generated placeholders
│   ├── skeleton_parser.py       # Parses basic skeletons
│   ├── scraper.py               # DOM metadata scraper
│   ├── page_object_builder.py   # Page Object Model generation
│   ├── semantic_candidate_ranker.py # Context candidate prioritization
│   ├── pipeline_report_service.py
│   ├── pipeline_run_service.py
│   ├── pipeline_writer.py
│   ├── file_utils.py            # save_generated_test, rename, normalise helpers
│   └── page_context_scraper.py  # DOM scraper for real locator injection
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
source .venv/Scripts/activate   # Git Bash / Windows
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

---

## 8. LLM Prompt Rules (for Generated Tests)

When writing or modifying prompts that generate test code:

- ✅ Enumerate acceptance criteria with numbers: `1. Criterion`, `2. Criterion`
- ✅ State total count: `(Total: N criteria)`
- ✅ Add explicit: `"Generate ONE test function per criterion"`
- ✅ Add explicit: `"DO NOT use async def — use pytest sync format"`
- ✅ Add explicit: `"DO NOT skip, combine, or omit any criteria"`
- ✅ Add closing warning: `"All N criteria must have tests"`
- ❌ NEVER use XML tags in prompts for this LLM — it ignores them
- ❌ NEVER make prompts verbose — clear numbered requirements outperform long prose

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

## 11. Planned Work (Next Up)

| ID | Feature | Files to Create |
|----|---------|----------------|
| AI-018 | Evidence Tracker Module — wraps Playwright interactions to record data | `src/evidence_tracker.py`, `tests/test_evidence_tracker.py` |
| AI-019 | Prompt Update: EvidenceTracker Methods | `src/prompt_utils.py` |

---

*Last updated: 2026-04-10*
*Supersedes: PROJECT_KNOWLEDGE.md for LLM/AI use. PROJECT_KNOWLEDGE.md remains the human reference.*
