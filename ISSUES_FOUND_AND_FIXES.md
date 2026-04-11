# AI-Playwright-Test-Generator — Issues Found and Fixes

## Overview
This document tracks issues identified in the `AI-Playwright-Test-Generator` repository
and the fixes applied. Issues are categorised by type and include root cause analysis,
solution implemented, and impact of each fix.

> **Architecture note:** Issues 3 and 4 below were fixed in the pre-session-2 codebase
> and reflect the original standalone async format. The project architecture was
> subsequently decided (2026-03-03) to use **pytest sync format** exclusively.
> Any references to async/await tests or "no pytest" as a fix are superseded.
> See PROJECT_KNOWLEDGE.md — Architecture Decisions for the current standard.

---

## Session 1-2 Issues (2026-03-01 to 2026-03-04)

### 1. GitHub Actions CI/CD Pipeline ⚠️
**Problem:** CI/CD badge not properly configured for renamed project.
**Fix:** Updated badge URL to reflect renamed repository.
**Impact:** CI/CD status badge now displays correctly.

### 2. Path Calculation Problem ⚠️
**Problem:** Paths calculated incorrectly when running from different directories.
**Fix:** Changed to `Path.cwd()` for consistent path resolution.
**Impact:** Script runs correctly from any directory.

### 3. ~~Pytest Import in Generated Tests~~ ⚠️ SUPERSEDED
**Original fix:** Told LLM not to import pytest (standalone async format).
**Superseded by:** Architecture decision 2026-03-03 — project now uses pytest sync
format exclusively. Generated tests must use pytest fixtures and sync API.
See B-001 in BACKLOG.md for the corrective fix applied in session 3.

### 4. LLM Prompt Structure ⚠️
**Problem:** Prompt too verbose, used XML tags LLM didn't respect.
**Fix:** Restructured with clear numbered requirements and explicit DO NOT instructions.
**Impact:** More consistent LLM output.

### 5. Markdown Code Fence Parsing ⚠️
**Problem:** LLM outputs markdown fences around generated code, parser handled inconsistently.
**Fix:** Enhanced cleaning logic to detect and strip fences, auto-detect code block start.
**Impact:** Generated files no longer contain markdown artifacts.

### 6. CLI Output Formatting ⚠️
**Problem:** CLI output minimal with no visual hierarchy.
**Fix:** Added separator lines, emoji icons, clearer option menus.
**Impact:** Improved developer UX.

### 7. CLI Module Architecture 🆕
**Problem:** No proper CLI interface with argument parsing.
**Fix:** Implemented complete CLI module with argparse, subcommands, config enums,
modular components (InputParser, UserStoryAnalyzer, TestCaseOrchestrator, etc.)
**Impact:** Tool supports both interactive and programmatic/CI usage.

### 8. Output Directory Argument Mismatch 🆕
**Problem:** CLI parser used `--output` but handler expected `output_dir`.
**Fix:** Used `dest="output_dir"` in argparse definition.

### 9. Report Format LOCAL Not Implemented 🆕
**Problem:** `ReportFormat.LOCAL` enum defined but `_save_local` not implemented.
**Fix:** Implemented `_save_local` generating both JSON and XML reports.

### 10. Missing `parse_json` Method 🆕
**Problem:** `InputParser` had no method to parse JSON-formatted input.
**Fix:** Added `parse_json` method to handle JSON test case definitions.

### 11. Class Name Inconsistency 🆕
**Problem:** Module imported `EvidenceGenerator` but class was named `EvidenceGen`.
**Fix:** Consistent class naming throughout evidence generator module.

### 12. Pre-commit Configuration 🆕
**Problem:** No `.pre-commit-config.yaml` — no automated quality checks before commits.
**Fix:** Created `.pre-commit-config.yaml` with ruff linting and ruff-format.
**Impact:** Automated code quality checks run before every commit.

---

## Session 3 Issues (2026-03-06)

### 13. Generated Tests Not Auto-Saved (B-003) ✅
**Problem:** Tests only existed in browser session after generation, not on disk.
**Fix:** Phase A — `save_generated_test()` in `src/file_utils.py`, called after every
successful generation. Path and filename stored in session state.

### 14. Import Newlines Collapsed (B-002) ✅
**Problem:** LLM occasionally returned all imports on one line causing SyntaxError.
**Fix:** `normalise_code_newlines()` in `src/file_utils.py`, applied after generation.

### 15. Async Tests Generated Instead of Pytest (B-001) ✅
**Problem:** Despite architecture decision, LLM still generated async standalone tests.
**Fix:** System prompt in `src/llm_client.py` updated. `generate_test_for_story()` prompt
reinforced with explicit pytest format requirements and DO NOT async instructions.

### 16. `launch_ui.sh` Started Mock Server (B-005) ✅
**Problem:** `launch_ui.sh` started mock insurance site alongside UI — wrong for general use.
**Fix:** Mock server startup moved to new `launch_dev.sh`. `launch_ui.sh` launches UI only.

### 17. Helper Functions in `streamlit_app.py` Untestable ⚠️
**Problem:** Importing `streamlit_app` in tests triggers `st.set_page_config()` crash.
**Fix (partial):** `save_generated_test`, `rename_test_file`, `normalise_code_newlines`
moved to `src/file_utils.py`. Coverage helpers still in `streamlit_app.py` — tracked as AI-005.
**Rule established:** All testable helper functions must live in `src/` not `streamlit_app.py`.

---

## Session 4 Issues (2026-03-07)

### 18. Page Context Scraper — `sync_playwright` Not Patchable (AI-001) ✅
**Problem:** `sync_playwright` imported inside function body, not at module level.
`@patch("src.page_context_scraper.sync_playwright")` raised AttributeError in tests.
**Fix:** Moved all playwright imports to top of `src/page_context_scraper.py`.

### 19. Generated Tests Running in CI (pytest.ini) ✅
**Problem:** `pytest.ini` had `testpaths = tests generated_tests`. Generated tests
require a live server at `localhost:8080` — all failed in CI with `ERR_CONNECTION_REFUSED`.
**Fix:** Removed `generated_tests` from `testpaths`. Generated tests run explicitly only.

### 20. Coverage Mapping — All Criteria Mapped to test_01 ✅
**Problem:** Keyword overlap matcher found `test_01_can_enter_driver_name` for TC-001,
TC-002, and TC-003 because all share common words (driver, add, can).
**Fix:** Number-based matching added before keyword fallback. TC-001 looks for `test_01_*`
first, TC-002 looks for `test_02_*` first. Keyword matching only fires if no numbered
match found.

### 21. Run Output Lost on Download Button Click ✅
**Problem:** `success` and `output` were local variables in `display_run_button()`,
lost on every Streamlit rerun triggered by download button clicks.
**Fix:** Run results persisted in `session_state.last_run_success` and
`session_state.last_run_output`. Output section renders from session state.

### 22. Jira Report Missing from Downloads ✅
**Problem:** `report_jira` key existed in `_session_defaults` since Phase A but was
never populated or surfaced in the UI. Gemini AI dropped the tab during the persistence
fix and added JSON/HTML but not Jira.
**Fix:** `_generate_jira_report()` added, called in output section with coverage data.
4th download button added to `display_run_button()`.

### 23. High Confidence Metric Misleading ✅
**Problem:** Confidence hardcoded to 0.9 for any keyword match, making High Confidence %
identical to Covered %. Metric provided no additional information.
**Fix:** Replaced with Tests Generated count — total number of test functions linked
across all criteria.

### 24. `run_playwright_test()` Called Wrong Command ✅
**Problem:** Function called `["playwright", "test", file_path]` (Node.js CLI) instead
of `["pytest", file_path, "-v", "--tb=short"]`. Generated tests are pytest format.
**Fix:** Command updated to use pytest.

### 25. Git Hygiene — Tracked Files That Should Not Be ✅
**Problem:** `generated_tests/test_*.py`, `coverage.xml`, `*.pyc` files committed to repo.
**Fix:** Files removed with `git rm --cached`. `.gitignore` updated and reformatted
with clear sections. `generated_tests/test_*.py` pattern added.

### 26. Gemini AI Session — Multiple Issues Introduced
**Problem:** Gemini AI implemented AI-001 without running the app end-to-end. Declared
done before testing. Issues introduced:
- Typos: `scrape_errror`, `ffailed`, `funcctions`, `Revieww` (runtime errors)
- Wrong playwright command in `run_playwright_test()` (issue 24 above)
- `sync_playwright` import inside function body (issue 18 above)
- Missing Jira report (issue 22 above)
- `coverage.xml` committed (issue 25 above)
- Multiple mypy errors (`dict[str, None]`, `dict[str, str]`, missing type annotations)

**Lessons learned:**
- Always run ruff, mypy, pytest before accepting AI-generated code
- Review `git diff --staged --stat` before every commit
- Never let an AI commit directly without human review
- Give implementation AIs the full project rules, not just the spec doc
- One feature per AI session — mixing tools mid-feature creates inconsistency

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-01 | Initial release with interactive CLI |
| 1.1.0 | 2026-03-03 | CLI overhaul with argparse, report generation, multi-format support |
| 1.2.0 | 2026-03-04 | Pre-commit configuration with ruff, automated code quality checks |
| 1.3.0 | 2026-03-06 | Streamlit UI, Phase A/B/C (save/coverage/run), B-001/002/003/005 fixed |
| 1.4.0 | 2026-03-07 | Page context scraper (AI-001), coverage mapping fix, Jira download, git hygiene |
| 1.5.0 | 2026-03-21 | B-006/007 fixed, AI-003 closed, AI-009 Phase A complete (multi-page scraper UI) |
| 1.6.0 | 2026-04-10 | Pipeline architecture added, multi-provider LLM support, anchor link extraction, transitioned pip to uv |

---

## April Updates and Fixes (2026-04-01 to 2026-04-10)

### 27. Missing Links in Page Context Scraper 🆕
**Problem:** The page context scraper was not capturing navigation links (`<a>` tags), resulting in missed elements on some pages.
**Fix:** Added anchor link extraction to `src/page_context_scraper.py`.
**Impact:** Elements found increased significantly, enabling the LLM to access hidden flows and deep links.

### 28. Single-Provider Limitation 🆕
**Problem:** The tool was hardcoded to use Ollama, preventing users from leveraging more powerful models (e.g., GPT-4 or Claude) externally.
**Fix:** Implemented multi-provider LLM architecture, falling back gracefully to Ollama when necessary.

### 29. Monolithic Architecture Bottlenecks 🆕
**Problem:** As logic became complex, test orchestration and CLI modules were tightly coupled.
**Fix:** Implemented pipeline architecture to improve component separation and update outdated dependencies.

### 30. pip Dependency Residue 🆕
**Problem:** Remnants of `pip` were still lingering in instructions or utility scripts despite the project transition to `uv`.
**Fix:** Fixed utility scripts to strictly adhere to the `uv` adoption constraints and tightened gitignore for `.tmp` and PNG files.
