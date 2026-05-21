# scripts/

Utility and automation scripts for the AI-Playwright-Test-Generator project.

## Directory Structure

| Folder | Purpose |
|--------|---------|
| `3d map/` | 3D documentation map generation and auditing |
| `debug/` | Diagnostic scripts for pipeline debugging |
| `maintenance/` | Project housekeeping and CI utilities |
| `uat/` | User acceptance testing scripts |

---

## 3d map/

Generates and audits the project's 3D documentation map (nodes.csv + links.csv).

| Script | Description |
|--------|-------------|
| `generate_3d_map.py` | Scans the project and generates `docs/nodes.csv`, `docs/links.csv`, and `scripts/3d map/3d_map_data.json` |
| `audit_3d_map.py` | Validates the map: dead links, orphaned docs, import drift |
| `3d_map_data.json` | Generated JSON output for the 3D visualizer |

**Usage:**
```bash
python scripts/3d\ map/generate_3d_map.py
python scripts/3d\ map/audit_3d_map.py
```

---

## debug/

Diagnostic scripts for investigating pipeline issues. Most were created during specific debugging sessions and are now consolidated.

| Script | Description |
|--------|-------------|
| `debug_all.py` | **Unified entry point** — run `--help` for all options |
| `debug_pipeline.py` | Full pipeline trace (skeleton → scrape → resolve → final code) |
| `debug_saucedemo_inventory.py` | Scrape SauceDemo inventory page and test placeholder resolution |
| `debug_saucedemo_login.py` | Login to SauceDemo, scrape inventory, test resolution |
| `debug_saucedemo_scrape2.py` | Quick scrape of SauceDemo login page |
| `debug_scoring.py` | Debug scoring for specific elements (e.g., shopping cart icon) |

**Usage:**
```bash
# Unified entry point (recommended)
python scripts/debug/debug_all.py --help
python scripts/debug/debug_all.py pipeline --url https://example.com
python scripts/debug/debug_all.py saucedemo-login
python scripts/debug/debug_all.py scoring

# Or run individual scripts directly
python scripts/debug/debug_pipeline.py --url https://saucedemo.com
```

---

## maintenance/

Project housekeeping tools — safe to run in CI.

| Script | Description |
|--------|-------------|
| `cli_e2e_validation.py` | End-to-end CLI validation: runs the full pipeline and validates generated Python syntax |
| `project_sanitizer.py` | Project cleanup: auto-move misplaced tests, purge junk files, audit doc links |

**Usage:**
```bash
# CLI E2E validation
python scripts/maintenance/cli_e2e_validation.py --url https://example.com

# Project sanitizer (CI mode)
python scripts/maintenance/project_sanitizer.py --check-only
```

---

## uat/

User acceptance testing scripts for end-to-end pipeline validation against real websites.

| Script | Description |
|--------|-------------|
| `uat_automationexercise.py` | Full pipeline validation against automationexercise.com (or saucedemo.com) |

**Usage:**
```bash
# Default: automationexercise.com
python scripts/uat/uat_automationexercise.py --provider lm-studio

# SauceDemo target
python scripts/uat/uat_automationexercise.py --provider lm-studio --site saucedemo

# Headed mode (show browser)
python scripts/uat/uat_automationexercise.py --provider lm-studio --headed

# Run generated tests too
python scripts/uat/uat_automationexercise.py --provider lm-studio --run
```

**NOTE:** When running through Cline, use `--provider lm-studio` with the same model Cline is already using to avoid GPU VRAM contention.

---

## Deleted Scripts (Consolidated)

These scripts were removed during cleanup — their functionality was either redundant or superseded:

| Script | Reason |
|--------|--------|
| `dump_manifest.py` | Scratch script for debugging scrape manifests |
| `run_lmstudio_pipeline_once.py` | Superseded by `uat_automationexercise.py` |
| `uat_full_pipeline.py` | Minimal stub — superseded by `uat_automationexercise.py` |
| `uat_goto_error.py` | One-off bug reproduction — issue resolved |
| `uat_llm_call.py` | Minimal LLM connectivity test — superseded by full UAT |
| `uat_reproducible_failure.py` | One-off bug reproduction — issue resolved |
| `uat_saucedemo.py` | Superseded by `uat_automationexercise.py --site saucedemo` |
| `uat_workflow.py` | 3-stage workflow — superseded by individual UAT scripts |

---

## Refactor 2026-05-20 — Intent Matcher + Placeholder Scorers

Two new modules extracted during the refactor session (2026-05-20/21):

| Script | Description |
|--------|-------------|
| `scripts/debug/skeleton_variability_report.md` | Debug report generated during skeleton variability investigation |

**Related modules:**
- `src/intent_matcher.py` — refactored into composable bucket-match functions (`match_clickable`, `match_fillable`, `match_assert_text`)
- `src/placeholder_scorers.py` — new composite scoring engine with individual, testable scoring functions
- `tests/test_intent_matcher.py` — 13 tests for all bucket functions and `apply_intent_filter()`
- `tests/test_placeholder_scorers.py` — 23 tests for all scoring functions and `CompositeScorer.apply_all()`

**Audit report:** `docs/implementation/refactor_audit_2026-05-20.md` documents the complete refactoring session.

---

*Last updated: 2026-05-21*