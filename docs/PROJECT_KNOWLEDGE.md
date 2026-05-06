# PROJECT_KNOWLEDGE.md

> AI coding agents: read this file before writing code. It contains architecture decisions,
> known gotchas, and recurring bugs that have caused repeated failures.

## Architecture Decisions (FINAL)

### Test Format: Pytest Sync + Playwright Fixtures
- **Use:** `def test_xxx(page: Page):` with `playwright` fixture
- **Don't use:** `async def test_xxx` or `asyncio.run()` style
- **Decision date:** 2026-03-03. This is not open for discussion.

### Package Manager: uv
- **Use:** `uv add <package>`, `uv sync`
- **Never use:** `pip install` — pip is not on PATH in this project

### UI Framework: Streamlit
- **Use:** `streamlit_app.py` as primary entry point
- **Don't use:** Flask/Django/React — too much overhead
- **Entry:** `bash launch_ui.sh`

### CLI Entry Point
- **Use:** `cli/main.py` via `bash launch_cli.sh` or `python -m cli.main`
- **Don't use:** root `main.py` for new behavior. It is a deprecated compatibility wrapper only.
- **Reason:** The older root menu flow predates the skeleton-first pipeline and was superseded by the argparse CLI module.

### Testable Helpers Location: `src/` modules
- **Use:** `src/<module>.py` for testable functions
- **Don't use:** `streamlit_app.py` for testable logic — importing it outside
  Streamlit context triggers `st.set_page_config()` crash

### LLM Parsing: Smart Hybrid
- **Default:** regex first, LLM only if regex fails or >3 criteria found
- **Don't use:** Always-LLM mode

### Screenshot Reports: 3 Formats
1. `local.md` — relative paths for local viewing
2. `jira.md` — Jira attachment format (`!filename.png|thumbnail!`)
3. `standalone.html` — base64-embedded, fully self-contained

### Skeleton-First Pipeline: Two-Phase Generation
1. **Phase 1 (LLM):** Generates skeletons with placeholder syntax `{{ACTION:description}}`
2. **Phase 2 (Resolver):** Fills placeholders from scraped DOM elements
- **Never** inject real selectors into LLM prompts — this was the source of selector hallucination

## Retired Modules (DO NOT RESTORE)

### `src/page_context_scraper.py` — DELETED (2026-04-22)
- **Reason:** Injected real selectors into LLM prompts via `to_prompt_block()`,
  causing the LLM to hallucinate variations of those selectors
- **Replaced by:** skeleton-first two-phase pipeline
- **Rule:** Do not use or restore this module

## Environment Setup

```bash
# .env (NEVER COMMIT)
OLLAMA_MODEL=qwen3.5:35b
OLLAMA_TIMEOUT=300          # Must be 300 — default 60s causes timeouts
OLLAMA_BASE_URL=http://localhost:11434
```

> ⚠️ `OLLAMA_TIMEOUT` is only respected if `load_dotenv()` is called **before**
> `LLMClient` initialises. Check that no module-level `LLMClient()` instantiation
> happens at import time.

## Protected Files (DO NOT MODIFY Without Explicit Instruction)

| File | Reason |
|------|--------|
| `src/test_generator.py` | Working test generation pipeline — stable |
| `src/llm_client.py` | Ollama API client — working correctly |
| `.github/workflows/ci.yml` | CI/CD configured and passing |

**Rule:** If you find a bug in a protected file, document it in BACKLOG.md and ask before editing.

## Deprecated Compatibility Files

| File | Status |
|------|--------|
| `main.py` | Deprecated wrapper to `cli.main`. Keep it minimal and do not restore the retired pre-pipeline CLI menu. |

## Protected Directories

| Directory | Reason |
|-----------|--------|
| `src/llm_providers/` | Provider implementations — stable after initial implementation |
| `docs/specs/FEATURE_SPEC_multi_provider_llm.md` | Multi-provider architecture spec |

## Recurring Bugs to Watch For

These have appeared multiple times during AI-assisted development:

| Bug | Symptom | Fix |
|-----|---------|-----|
| Wrong class name | `ImportError: cannot name ...` | Check class name consistency (e.g., `EvidenceGenerator` vs `EvidenceGen`) |
| `sync_playwright` not patchable | Import inside function body | Move all playwright imports to module level |
| `mypy no-redef` on type annotation | Variable annotated twice in try/except | Declare `var: type | None = None` before the `try` block |
| `mypy import-untyped` for pandas | `pandas-stubs` not installed | `uv add --dev pandas-stubs` |
| `mypy import-untyped` for plotly | No official stubs exist | Add `[[tool.mypy.overrides]]` with `ignore_missing_imports` in `pyproject.toml` |
| Session state wipe pattern | Results blank after button click | Never set state key to None/empty after setting real value |
| Tabs inside button block | Content disappears on rerun | Render from `session_state` outside button block |
| `scrape_page_context` not unpacked | TypeError | Always use `ctx, err = scrape_page_context(url)` |
| `base_url.split(':')[1]` | list index out of range | Use `re.sub(r"[^\w]", "_", base_url)` for slugs |

## Common Issues & Solutions

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Could not connect to Ollama" | Ollama not running | `ollama serve` + `ollama list` |
| "LLM returned empty response" | `OLLAMA_TIMEOUT` too low | Set `OLLAMA_TIMEOUT=300` in `.env` |
| Unexpected skeleton count or only one generated test | local LLM nondeterminism or prompt adherence variance | Rerun the pipeline; the skeleton prompt now explicitly injects the expected test count and uses stricter retry guidance. If it persists, try a different LM Studio model variant. |
| Generated tests fail in CI | `generated_tests/` in testpaths | `pytest.ini` — `testpaths = tests` only |
| Wrong venv active | Old venv from renamed project | `rm -rf .venv && uv sync` |
| mypy cache corruption | Stale `.mypy_cache` | `rm -rf .mypy_cache` then re-run |
| Port 8501 already in use | Another Streamlit running | `taskkill //F //IM streamlit.exe` (Windows) |

## Key Implementation Patterns

### Coverage Analysis
After generation, the tool:
1. Extracts test function names with `re.findall(r"^def (test_\w+)", code, re.MULTILINE)`
2. For each criterion, matches by `test_NN_` prefix then falls back to keyword overlap
3. Builds `RequirementCoverage` objects stored in `st.session_state.coverage_analysis`

### Evidence Tracker Public API
Generated tests should use these methods (not raw Playwright calls):
```python
tracker.navigate(url: str) -> None
tracker.fill(locator: str, value: str, label: str = "") -> None
tracker.click(locator: str, label: str = "") -> None
tracker.assert_visible(locator: str, label: str = "") -> None
tracker.write(status: str = "passed") -> str  # returns sidecar path
```

### Placeholder Resolution (Two-Phase Pipeline)
- **Phase 1:** LLM generates skeletons with `{{ACTION:description}}` placeholders — never sees real locators
- **Phase 2:** `PlaceholderOrchestrator` coordinates resolution using scraped DOM data
- **LocatorScorer priority:** `data-testid > id > name > aria-label > css-class > text > xpath` (+10 bonus for text match)
- **SemanticCandidateRanker:** LLM tiebreaker when top candidates within ±2 score threshold
- **Confidence threshold:** `PLACEHOLDER_MIN_CONFIDENCE` env var (default 0.3) rejects low-confidence matches
- **Page-context validation:** `_verify_page_context()` warns if locator scraped from different page than journey URL
- See `docs/ARCHITECTURE.md` §4 for full dependency graph

## Test Folder Coverage

| src/ File | Test File | Status |
|-----------|-----------|--------|
| `code_postprocessor.py` | `test_code_postprocessor_llm_reasoning.py` | ✅ Covered |
| `url_utils.py` | — | ❌ Missing — pure functions, easy to add |
| `analyzer.py` | — | ⚠️ Only indirectly tested via CLI |
| `evidence_report.py` | — | ⚠️ Partially covered by `test_report_utils.py` |
| `report_builder.py` | — | ⚠️ Partially covered by `test_report_utils.py` |
| `report_formatters.py` | — | ⚠️ Partially covered by `test_report_utils.py` |
| `llm_providers/__init__.py` | `test_llm_client.py` | ✅ Covered (via LLMClient tests) |
| `config.py` | — | ❌ Missing (trivial constants) |

**New modules with test coverage:**
- `placeholder_orchestrator.py`, `journey_scraper.py`, `locator_scorer.py`, `evidence_loader.py`, `failure_reporter.py` all have dedicated test files in `tests/`.

See `docs/ARCHITECTURE.md` §2 for complete module responsibility map.

## Planned Work

| ID | Feature | Files to Create |
|----|---------|----------------|
| AI-019 | Prompt Update: EvidenceTracker Methods | `src/prompt_utils.py` |

## Version History

- **2026-03-03:** Initial creation, Phase 1-4 roadmap defined, architecture decisions finalised
- **2026-03-05:** Session 2 — Streamlit UI built, uv adopted
- **2026-03-13:** Sessions 3-8 — AI-001 page context scraper, coverage mapping, run results parser, feature recovery
- **2026-03-16:** Session 9 — BREAK-1/BREAK-2 fixed
- **2026-03-29:** Docs refresh — PROJECT_KNOWLEDGE.md updated
- **2026-04-04:** Evidence traceability pipeline designed (AI-016 through AI-022)
- **2026-04-08:** Pipeline architecture refactor, multi-provider LLM support
- **2026-04-12:** Documentation refactoring — consolidated overlapping docs
- **2026-04-22:** CLI module split — removed `story_analyzer.py`; CLI analysis now routes through `src/analyzer.py` and `cli/config.py`
- **2026-05-01:** Root `main.py` deprecated as compatibility wrapper; supported CLI entry point is `cli/main.py`.
- **2026-04-22:** Test folder cleanup — removed stale `tests/src/` (duplicates of src/ files),
  `tests/example_test.py`, `tests/uat_pipeline_test.py`, `tests/coverage.xml`.
  Deleted deprecated `src/page_context_scraper.py`. 299 tests passing.

---

*Last Updated: 2026-04-22*
*Project Status: CI green — Pipeline architecture, multi-provider LLM, Evidence Tracker (AI-018), CLI split complete.*
