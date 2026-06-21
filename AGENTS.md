# AGENTS.md — AI-Playwright-Test-Generator

> Single source of truth for AI assistants. Read `.clinerules` for session/MCP rules.
> Historical & reference sections moved to `docs/reference/agents_archive.md`.

---

## 1. What This Project Does

Generates Playwright Python test scripts from user stories using a local LLM.
Primary interface: Streamlit UI (`streamlit_app.py`). Secondary: CLI (`cli/main.py`, launched by `launch_cli.sh`).
Tests written to `generated_tests/`, run via pytest, evidence exported as Jira/HTML/JSON.

---

## 2. Non-Negotiable Rules

### Package Manager
- ✅ Use `uv add <package>` and `uv sync`
- ❌ NEVER use `pip install` — pip is not on PATH

### Test Format
- ✅ All generated tests use **pytest sync format** with `playwright` fixtures
- ❌ NEVER generate `async def test_` or `asyncio.run()` style tests
- ❌ NEVER use native async/await Playwright API in generated tests

### Helper Functions
- ✅ Testable helpers go in `src/<module_name>.py`, imported into `streamlit_app.py`
- ❌ NEVER put testable functions directly in `streamlit_app.py`

### Type Hints
- ✅ All functions must have full type annotations
- ❌ NEVER remove or omit type hints

### Git Hygiene
- ❌ NEVER commit `.env`, `__pycache__/`, `generated_tests/test_*.py`, or `coverage.xml`
- ❌ NEVER force push to `main` without explicit instruction
- ✅ Always run `ruff` → `mypy` → `pytest` before accepting work as done
- ✅ Review `git diff --staged --stat` before every commit

---

## 3. Protected Files — Do Not Modify Without Explicit Instruction

| File | Reason |
|------|--------|
| `src/test_generator.py` | Working test generation pipeline — stable |
| `src/llm_client.py` | Stable LLM client |
| `.github/workflows/ci.yml` | CI/CD configured and passing |
| `src/llm_providers/` | Provider implementations — stable |

**Rule:** If you find a bug in a protected file, document it in BACKLOG.md and ask before editing.

---

## 4. Project Structure (Key Files)

```
streamlit_app.py             # Primary UI entry point
launch_ui.sh / launch_cli.sh # Launch scripts
pyproject.toml               # Dependencies — managed by uv
pytest.ini                   # testpaths = tests (NOT generated_tests)
cli/                         # CLI module (argparse-based)
src/                         # Core modules — tested via tests/
tests/                       # Unit tests FOR the tool
generated_tests/             # OUTPUT — tests produced by the tool
docs/                        # Documentation hub
scripts/                     # Utility and UAT scripts
notebooks/                   # Interactive debugging notebooks
```

Full directory tree: see `docs/reference/agents_archive.md` §4.

---

## 5. Architecture Decisions

| Decision | Choice | Do Not Use |
|----------|--------|------------|
| Test format | pytest sync + playwright fixtures | async/await standalone |
| Package manager | `uv` | `pip` |
| UI framework | Streamlit | Flask / Django / React |
| Testable helpers | `src/` modules | `streamlit_app.py` |
| LLM parsing | Regex first, LLM fallback | Always-LLM mode |

---

## 6. Environment & Run Commands

```bash
# Setup
uv sync && .venv\Scripts\activate && playwright install chromium

# Run
bash launch_ui.sh          # UI only
bash launch_dev.sh         # UI + mock insurance site
bash launch_cli.sh         # Interactive CLI

# Tests
pytest -n auto -x -q       # Parallel (~2min for 778 tests)
pytest -v                  # Single-process with output
```

Full environment detail (LM Studio, OpenAI providers): see `docs/reference/agents_archive.md` §6.

---

## 7. Common Issues — Quick Reference

| Symptom | Fix |
|---------|-----|
| "LLM returned empty response" | `OLLAMA_TIMEOUT=300` in `.env` |
| `SyntaxError` on imports | `normalise_code_newlines()` after generation |
| strict mode violation (2 elements) | Use specific ID locator |
| Last criteria omitted | Enumerate criteria with numbers + "DO NOT skip" |
| Buttons clear page | Store output in `st.session_state` |
| pre-commit "files modified" | `git add -A` then commit again |

Full table with causes: see `docs/reference/agents_archive.md` §7.

---

## 8. LLM Prompt Rules (Skeleton-First Pipeline)

- ✅ Enumerate criteria: `1. Criterion`, `2. Criterion` + `(Total: N criteria)`
- ✅ `"Generate ONE skeleton function per criterion"`
- ✅ `"DO NOT use async def — use pytest sync format"`
- ✅ `"DO NOT skip, combine, or omit any criteria"`
- ✅ Placeholder syntax: `{{{{ACTION:description}}}}` for unknown locators
- ✅ `"Use ONLY the placeholder types listed in ALLOWED PLACEHOLDERS"`
- ❌ NEVER use XML tags in prompts
- ❌ NEVER make prompts verbose
- **TWO PHASES:** Phase 1 = skeletons with placeholders. Phase 2 = resolve using scraped DOM.

---

## 9. Adding New Modules

1. Create `src/<module_name>.py` with full type annotations
2. Create `tests/test_<module_name>.py` with unit tests
3. Import into `streamlit_app.py` if needed — never define logic there
4. Run `ruff check` + `mypy` before committing
5. Move playwright imports to module level
6. Create `markdown_docs/src/<module_name>.py.md` using `document-manager` skill
7. Update `markdown_docs/.sweep_progress.json`

---

## 10. Documentation Maintenance

- Module docs in `markdown_docs/src/<module_name>.py.md`
- Use `document-manager` skill to generate/update
- Check `markdown_docs/.sweep_progress.json` for coverage status

---

## 11. General Discipline

- **Run end-to-end** before declaring a feature done
- **One feature per session** — mixing creates inconsistency
- **Never commit directly** — `ruff` → `mypy` → `pytest` → human reviews diff → commit
- **Typos cause runtime errors** — search for misspellings after AI-generated code
- **Check class name consistency** — import name must match class name
- **Coverage mapping**: number-based (TC-001 → `test_01_*`) before keyword fallback

---

## 12. Debugging & UAT

- **Interactive**: `notebooks/debug_pipeline.ipynb` — preferred for placeholder/scraper issues
- **CLI fallback**: `scripts/debug/debug_pipeline.py`
- **E2E validation**: `scripts/uat/uat_automationexercise.py`
- **GPU VRAM**: use same LM Studio model as Cline to avoid contention

Full UAT usage: see `docs/reference/agents_archive.md` §12.

---

## 13. Known Issues — Placeholder Resolution

| Symptom | Status |
|---------|--------|
| ASSERT placeholders resolve to wrong element | Open — needs semantic matching improvement |
| Navigation criteria generate GOTO not CLICK | By design |

Full detail: see `docs/reference/agents_archive.md` §13.

---

## Agent skills

### Issue tracker

Local markdown — issues live in `BACKLOG.md`. See `docs/agents/issue-tracker.md`.

### Triage labels

Mapped to emoji-backed status strings (`🆕 new`, `❓ needs-info`, `🟡 ready-for-agent`, `👤 ready-for-human`, `superseded`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` at repo root + `docs/adr/` for ADRs. See `docs/agents/domain.md`.

---

*Last updated: 2026-06-20*
*Historical/reference sections: `docs/reference/agents_archive.md`*