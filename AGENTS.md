# AGENTS.md — tancat-ai/tancat

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
| `src/agents/` | LangGraph multi-agent pipeline — Planner, Generator, Validator, Ingestion, QA Director, Synthesizer |

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
| Default LLM provider | `openai-local` (llama.cpp :8080) | Never hardcode `ollama` |

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
pytest -q --tb=short       # Default -n 4 from pytest.ini — the tested sweet spot
                            #   (-n 8 crashes on Windows; -n 1 for single-process)
pytest -v                  # Default -n 4 with output
# UAT
python scripts/uat.py --all-sites --save results.json  # Needs LM Studio running on :8080
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

### Work tracking — split of responsibility

Two files track active work; each owns a different class of item. **This split is the single source of truth for where an item lives.**

| File | Owns | Examples |
|------|------|----------|
| `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` | **Big features / phases** (multi-session, spec-backed, portfolio/GTM) | Phase 1–8, AI-010/011/026/028/029, traceability 16b, AI-042/043/044 |
| `BACKLOG.md` | **Fixes and smaller changes** (bugs B-xxx, focused improvements, experiments, watch-items) | B-030 family, AI-058/061/062/063/064/065, AI-054 |

**Rules (enforced to stop the muddle):**
- ✅ **One canonical location per item.** The full item (status, scope, decisions, session log) lives in exactly one of the two files.
- ✅ The *other* file may reference it, but **only as a one-line pointer** ("see AI-063 in BACKLOG.md") — **never** a second copy of status, checkboxes, or session history.
- ❌ **NEVER maintain the same item's status in both files** — that is what caused the 2026-09 drift (a spec line claimed Phase 6 "6b–6i shipped" while BACKLOG correctly kept 6c/6d/6e/6h open). Status lives in the owner file; everything else points.
- ✅ When an item is big enough to earn roadmap treatment, move it to the roadmap and leave a one-line pointer in BACKLOG (and vice-versa for a feature that shrinks to a fix).
- ✅ **Verify shipped-ness against the code, not the docs** — a "shipped" checkbox with no matching code is a doc bug; check the code before trusting or propagating a status line.

### Kanban Board

- **`BACKLOG.md` is the source of truth for bug/fix/small-change tracking** (the roadmap owns big features — see the split above).
- **`kanban.html` is a generated view** — never edit it directly. It's regenerated from `BACKLOG.md`.
- After updating `BACKLOG.md`, run `python scripts/maintenance/kanban.py` to regenerate.
- Commit `BACKLOG.md` and `kanban.html` together.
- Pre-commit hook and CI verify `kanban.html` is up to date.

### Backlog & Roadmap Sync
- ✅ Status updates (`BACKLOG.md`, `ROADMAP_ROADTO_PRODUCTION.md`) happen ONLY during ship-it — never mid-session
- ✅ Update the item's status in **its owner file only**; keep any pointer in the other file to one line
- ❌ NEVER mark an item `✅ Complete` before it's committed, pushed, and CI green
- See ship-it skill §3 for the full housekeeping checklist

### Housekeeping (run via ship-it skill or manually before commit)

- `python scripts/maintenance/kanban.py` — regenerate kanban
- If `graphify-out/graph.json` is stale: run `graphify update .` then regenerate callflow.html
- If new `src/` files added: run `document-manager` skill to update markdown_docs
- If notable changes shipped: update `CHANGELOG.md` [Unreleased] section
- If modules added/removed/renamed: update `docs/ARCHITECTURE.md`

---

## 11. General Discipline

- **Run `verify_production.py`** before declaring a feature done — unit tests passing ≠ product working
- **Run end-to-end** before declaring a feature done
- **One feature per session** — mixing creates inconsistency
- **Never commit directly** — `smoke.py` → `ruff` → `mypy` → `pytest` → human reviews diff → commit
- **Typos cause runtime errors** — search for misspellings after AI-generated code
- **Check class name consistency** — import name must match class name
- **Coverage mapping**: number-based (TC-001 → `test_01_*`) before keyword fallback

### Answer style — keep it short and plain (ASD-STE100 / Simplified Technical English)

The user switches off on long-winded answers. Follow this for **every** response:

- **Answer first, then (only if needed) why.** Lead with the direct answer / the thing to do. No preamble.
- **Kill the preamble-faf.** Do NOT open with "I'm glad…", "this is a concrete plan…", "I have to be honest…", "let me walk through it precisely", "I don't want to rubber-stamp…". Just start.
- **Short sentences. Common words. One idea per sentence.** ASD-STE100 style: no "utilize / leverage / facilitate / aforementioned / in order to" → use "use / help / do / that / to". No nested clauses.
- **Bullets over paragraphs.** A list of short items beats a wall of text.
- **No bolded signposts or section headers on a short answer.** Don't turn a 4-line answer into a 60-line one with headers.
- **Length cap:** most answers ≤ ~150 words. Only go longer when the task genuinely requires it (a code change, a real list, a multi-part plan) — and even then, keep each line short.
- **One recommendation, not five options with a "bottom line."** Pick the answer. If you must give options, ≤3, each one line.
- **No "the one thing I want to be clear about"** closing paragraphs. End when the answer is complete.
- **Honesty rule is NOT relaxed by brevity.** Still flag real errors / don't rubber-stamp / don't dodge — but do it in 1-2 short lines, not a long aside.

---

## 12. Debugging & UAT

### Verification layers (run in order)

| Layer | Command | What it tests | Cost |
|-------|---------|---------------|------|
| Smoke | `python scripts/smoke.py` | Offline: resolver, parser, imports | <1s |
| Unit | `pytest -q --tb=short` | Internal modules with mocks | ~10s |
| **Production** | `python scripts/verify_production.py` | **Full pipeline → execute → validate evidence** | ~60s |
| **Eval harness** | `python scripts/eval/eval_harness.py run --mode static` | **Resolution accuracy vs. golden keys (79.1% baseline)** | <1s |

- ✅ Run smoke → pytest → **verify_production** before declaring a feature done
- ✅ `verify_production.py` is the single source of truth: "does the product work?"
- ✅ It generates real tests, runs them against live sites, and validates evidence output
- ✅ Run **eval harness** before shipping changes to pipeline/resolver/prompt files — catches regression
- ✅ Eval harness is a *pre-commit quality gate*, not part of ship-it skill
- ✅ Eval harness tracks: resolution accuracy, test pass rate, false positive rate, skeleton completeness

### When to run the eval harness

**Run it when touching these files:**
- `src/orchestrator.py`, `src/placeholder_scorers.py`, `src/intent_matcher.py`
- `src/test_generator.py`, `src/llm_client.py`
- Any prompt templates or generation logic

**Don't run it for:** UI changes, CLI changes, Docker, unrelated features

**Commands:**
```bash
python scripts/eval/eval_harness.py run --mode static        # Fast, offline
python scripts/eval/eval_harness.py run --min-accuracy 79     # Quality gate (exit code 2 if below)
python scripts/eval/eval_harness.py baseline --save            # Update baseline after verified improvement
python scripts/eval/eval_harness.py compare                    # Current vs. saved baseline
python scripts/eval/eval_harness.py dataset --validate         # Validate golden keys
```

**Maintenance:** Golden keys decay — re-validate locators against live sites every 3-6 months.

### Debug CLI
- **`python scripts/debug.py --help`** — unified entry point
- `text-validation` / `skeleton` — offline, no browser or LLM needed
- `scrape <url>` — dump elements from any site
- `resolve <url> --action CLICK --desc "..."` — single placeholder resolution
- `score <url> --desc "..."` — cross-action scoring diagnostics
- `pipeline <url> --story "..."` — full trace, standard mode
- `pom <url> --story "..."` — full trace, **POM mode** (default for new work)

### E2E UAT
- **`python scripts/uat.py --all-sites`** — validates both automationexercise + saucedemo
- POM mode is default; `--flat` for standard mode
- `--save baseline.json` / `--compare baseline.json` for regression tracking
- `--run` to also execute generated tests against the real site
- **GPU VRAM**: use same LM Studio model as Cline to avoid contention

### Targeted debug scripts (`scripts/debug/`)
- `debug_pipeline.py` — full pipeline trace with stage-by-stage output
- `debug_saucedemo_login.py` — login + scrape inventory + resolution test
- `debug_saucedemo_inventory.py` — scrape inventory page only
- `debug_cli_interactive.py` — CLI interactive walkthrough debugger

### Script maintenance
- Scripts live in `scripts/` — new scripts go in root, targeted tools in `scripts/debug/`
- One-off debug scripts → archive to `scripts/archive/debug_scripts/`
- Update `scripts/README.md` when adding new scripts
- CI runs `smoke.py` on every push (Gate 0) — keeps resolver/parsing checks enforced

---

## 12b. Knowledge Graph (graphify) — when to use

`graphify-out/graph.json` is a gitignored, LLM-extracted **view** of the repo — orientation, never truth. It is a generated artifact, not a source of truth (same discipline as §10 "verify shipped-ness against the code").

**Reach for it when the question is graph-shaped:**
- "what is X connected to / what depends on X" — impact before editing a shared module (`graphify_query` BFS, or `affected`)
- "explain the <area>" — orientation before deep code reading (`graphify_explain` / `graphify_path`)
- architecture-path questions ("how does A reach B?") — `graphify_path` DFS

**Never trust it for precision:** line-level bugs, exact wiring, or any answer where a stale extraction would mislead — verify against code before acting. This session's bug hunts (skeleton story-bleed, mock-ensure parity, launcher kill path) all needed direct code reading; graphify pointed at neighborhoods, not lines.

**Maintenance:**
- `graphify update .` after any session that adds/removes `src/` modules, then regenerate `graphify-out/callflow.html` (uncommitted — gitignored)
- `graphify update` is code-only (no LLM needed); semantic extraction/build needs an LLM key (`DEEPSEEK_API_KEY` or `GEMINI_API_KEY`)
- `graphify-out/` is gitignored — never commit it

---

## 12c. zvec-grep (zg) — local semantic search, adopted 2026-09-05

`zg` is a local-first search layer (ripgrep + BM25 + vector) over the whole workspace — source AND the big markdown docs (specs/sessions/BACKLOG) where plain grep fails on prose-shaped questions. Index lives in `.zvec-grep/` (gitignored, regenerable, ~115 MB incl. the local `potion-retrieval-32m` embedding model).

**Use it for content-shaped questions** — "where does X get discussed/implemented", "the rag store seeding marker wipe problem" — `zg query "<question>" --limit N`. Complements graphify (§12b: structure/impact) — same discipline: **hits are leads, verify against code before acting**.

**Maintenance / operations:**
- Re-index after sessions that move code: `zg index` (incremental, ~60s; embedding `local/potion-retrieval-32m`, stays local — remote embeddings need explicit `zg auth`)
- Shared MCP daemon: `zg server on` (loopback :7999, agent toolset) — wired into `.mcp.json` as `zvec-grep` (`zg server --stdio`, lazy; **`.mcp.json` is gitignored** — recreatable: add `{"mcpServers":{"zvec-grep":{"command":"zg","args":["server","--stdio"],"lifecycle":"lazy"}}}`)
- `.zvec-grep/` is gitignored — never commit it; Node 22+ is a dev-tool runtime only
- Server auth: token file or `ZVEC_GREP_SERVER_TOKEN` if the loopback daemon needs locking down

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