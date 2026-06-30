# scripts/

Utility and automation scripts for the AI-Playwright-Test-Generator project.

## Quick Reference

| Script | Purpose | Needs |
|--------|---------|-------|
| `smoke.py` | Fast pre-commit smoke test (<1s) | Nothing — fully offline |
| `debug.py` | Unified diagnostic CLI | Varies by command (see below) |
| `uat.py` | End-to-end pipeline validation | Browser + LLM |
| `maintenance/project_sanitizer.py` | Project housekeeping (CI) | Nothing |
| `maintenance/cli_e2e_validation.py` | CLI pipeline syntax validation | Browser + LLM |
| `3d map/*.py` | 3D documentation map generation | Nothing |

---

## smoke.py — Pre-commit Smoke Test

Fast offline checks that catch obvious regressions in <1 second. Run before `pytest`.

```bash
python scripts/smoke.py                  # human-readable
python scripts/smoke.py --json           # machine-readable (CI)
```

**Checks:**
- Module imports (12 critical modules)
- Text validation (12 resolver cases)
- Skeleton parsing (placeholder extraction, journey grouping)
- POM mode data model (ExportMode, PageObjectBuilder, PipelineRunResult)

---

## debug.py — Unified Diagnostic CLI

Single entry point for all pipeline debugging. Offline commands need no browser or LLM.

```bash
python scripts/debug.py --help
```

### Offline commands (no browser, no LLM)

```bash
python scripts/debug.py text-validation    # resolver text matching
python scripts/debug.py skeleton           # placeholder parsing on sample code
```

### Browser commands (needs Playwright)

```bash
python scripts/debug.py scrape <url>                              # dump elements
python scripts/debug.py resolve <url> --action CLICK --desc "..." # single placeholder
python scripts/debug.py resolve <url> --action ASSERT --desc "..." --pom
python scripts/debug.py score <url> --desc "..."                  # score across action types
```

### Full pipeline commands (needs browser + LLM)

```bash
python scripts/debug.py pipeline <url> --story "..."              # standard mode trace
python scripts/debug.py pom <url> --story "..."                   # POM mode trace
python scripts/debug.py pom <url> --story "..." --conditions "..."
```

---

## uat.py — End-to-End Pipeline Validation

Run the full skeleton-first pipeline against real sites. **POM mode is default.**

```bash
# Single site (POM mode)
python scripts/uat.py saucedemo
python scripts/uat.py automationexercise

# Both sites
python scripts/uat.py --all-sites

# Flat mode (non-POM)
python scripts/uat.py saucedemo --flat

# Execute generated tests too
python scripts/uat.py saucedemo --run

# Save baseline for regression comparison
python scripts/uat.py --all-sites --save baseline.json

# Compare against baseline
python scripts/uat.py --all-sites --compare baseline.json

# LLM provider override
python scripts/uat.py saucedemo --provider lm-studio --model qwen3.6-27b

# Headed browser
python scripts/uat.py saucedemo --headed
```

**Sites:**
- `automationexercise` — e-commerce browse/add-to-cart flow
- `saucedemo` — authenticated login → add-to-cart → checkout flow

**Output:** Human-readable summary + optional JSON (`--save`) with per-check results,
generation timing, and POM class metadata.

---

## debug/ — Targeted Debug Scripts

These remain as specialized tools for specific scenarios:

| Script | Purpose |
|--------|---------|
| `debug_pipeline.py` | Full pipeline trace with stage-by-stage diagnostics |
| `debug_cli_interactive.py` | CLI interactive walkthrough debugger |
| `debug_saucedemo_inventory.py` | Scrape SauceDemo inventory + test resolution |
| `debug_saucedemo_login.py` | Login to SauceDemo → scrape inventory → test resolution |

---

## maintenance/

| Script | Purpose |
|--------|---------|
| `project_sanitizer.py` | Auto-move misplaced tests, purge junk, audit doc links |
| `cli_e2e_validation.py` | CLI pipeline E2E with Python syntax validation |

```bash
python scripts/maintenance/project_sanitizer.py --check-only   # CI mode
python scripts/maintenance/cli_e2e_validation.py --url <url>
```

---

## archive/

Archived scripts from previous debugging sessions. Not executed, kept for reference.

| Folder | Contents |
|--------|----------|
| `archive/debug_scripts/` | One-off debug scripts, old comparison tools, POM debug scripts |
| `archive/cli_snapshots/` | Terminal output snapshots from CLI debugging sessions |
| `archive/misc/` | One-time migration scripts, old result files |

---

*Last updated: 2026-06-29*
