# scripts/

Utility and automation scripts for the AI-Playwright-Test-Generator project.

## Quick Reference

| Script | Purpose | Needs |
|--------|---------|-------|
| `smoke.py` | Fast pre-commit smoke test (<1s) | Nothing — fully offline |
| `debug.py` | Unified diagnostic CLI | Varies by command (see below) |
| `uat.py` | End-to-end pipeline validation (static checks) | Browser + LLM |
| `verify_production.py` | Production gate — generates, executes, validates evidence | Browser + LLM |
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

## uat.py — End-to-End Pipeline Validation (Static)

Run the full skeleton-first pipeline against real sites and check generated code.
Does NOT execute tests by default (use `--run` flag). **POM mode is default.**

```bash
python scripts/uat.py saucedemo                  # static checks only
python scripts/uat.py --all-sites --run          # with test execution
python scripts/uat.py saucedemo --save baseline.json
```

**Sites:**
- `automationexercise` — e-commerce browse/add-to-cart flow
- `saucedemo` — authenticated login → add-to-cart → checkout flow

## verify_production.py — Production Verification Gate

The definitive check that the product works end-to-end. Unlike `uat.py` (static)
and `pytest` (unit tests with mocks), this script:

1. **Generates** tests via the full pipeline
2. **Executes** them against the real website
3. **Validates** evidence output (JSON sidecars, screenshots, step logs)
4. Produces a clear **PASS / FAIL** verdict

Run this **before declaring a feature done**.

```bash
python scripts/verify_production.py              # both sites, POM mode
python scripts/verify_production.py saucedemo    # single site
python scripts/verify_production.py --headed     # show browser
python scripts/verify_production.py --verbose    # print code + test output
python scripts/verify_production.py --keep       # keep output dirs
python scripts/verify_production.py --flat       # flat mode (non-POM)
```

**Gates per site (11 total):**
1. LLM connected
2. Pipeline generation succeeds
3. No unresolved `{{{{ACTION:...}}}}` placeholders
4. Sufficient test functions generated
5. Evidence tracker calls present
6. `@pytest.mark.evidence` decorators present
7. No `pytest.skip` in output
8. POM imports present (POM mode)
9. Pipeline resolved all placeholders
10. Generated tests pass against the real site
11. Evidence JSON files generated with meaningful steps

**Exit codes:** `0` = PASS (ship it), `1` = FAIL (fix gates first)

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
