# scripts/

Utility and automation scripts for the AI-Playwright-Test-Generator project.

## Quick Reference

| Script | Purpose | Needs |
|--------|---------|-------|
| `smoke.py` | Fast pre-commit smoke test (<1s) | Nothing — fully offline |
| `debug.py` | Unified diagnostic CLI | Varies by command (see below) |
| `debug_step_through.py` | Step-by-step interactive debugger for generated tests (headed) | Browser + Enter |
| `uat.py` | End-to-end pipeline validation (static checks) | Browser + LLM |
| `verify_production.py` | Production gate — generates, executes, validates evidence | Browser + LLM |
| `export_gate.py` | Export gate — exports flat+POM, validates artifacts, runs the exported suites | Browser (golden: localhost only) |
| `maintenance/project_sanitizer.py` | Project housekeeping (CI) | Nothing |
| `maintenance/cli_e2e_validation.py` | CLI pipeline syntax validation | Browser + LLM |
| `eval/eval_harness.py` | Eval harness — regression detection vs. golden keys | Nothing (static) / Browser (full) |
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

## debug_step_through.py — Step-By-Step Interactive Test Debugger

Runs the **real generated test functions** in a headed Chromium window and pauses
after every tracker step, printing the live state that the auto-dismissal logic
normally hides (add-to-cart modal, FreeCmp consent dialog, Google vignette,
cart-link count, URL). Use it to watch flaky popup/overlay behavior.

```bash
# Step through one failing test, interactively (press Enter after each step)
python scripts/debug_step_through.py generated_tests/test_XXX/test_....py --test test_t10

# Step through an entire package
python scripts/debug_step_through.py generated_tests/verify_automationexercise_20260803_032242/test_automationexercise.py

# Non-interactive (used by CI / quick dumps)
python scripts/debug_step_through.py <test_file.py> --auto --headless
```

**Why it exists:** `EvidenceTracker.click()` silently auto-dismisses consent
overlays and confirmation modals before every click — invisible in the test
file. This tool surfaces exactly what the tracker sees at each step.

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

## export_gate.py — Export Verification Gate

Proves that **exported test suites actually run** (B-031). The 2026-08-03 CLI
review found 34 of 35 exports were `def test_x(page): pass` stubs and the one
real export was non-importable (POM imports with no `pages/` dir, dead
`@pytest.mark.evidence` decorators). This is the export analogue of
`verify_production.py`:

1. Exports a source package in **both** modes (flat + POM)
2. Validates the exported artifacts — no evidence_tracker remnants, no
   `@pytest.mark.evidence` decorators, no stub bodies, POM pages shipped,
   run-history DB copied (B-032)
3. Collects both exported suites (catches import errors)
4. Runs both exported suites and asserts they pass

Default source is the bundled **golden fixture** (`fixtures/golden_package/`),
which mirrors a real generated package and targets a tiny localhost site
served by the script — fully deterministic, no external network, CI-able.

```bash
python scripts/export_gate.py                  # golden fixture, full run
python scripts/export_gate.py --keep           # keep export dirs on pass
python scripts/export_gate.py --source <pkg>   # real package, offline checks
python scripts/export_gate.py --source <pkg> --run-remote  # + live execution
```

**Gates (9):** stub guard · export flat · export POM · flat artifacts clean ·
POM artifacts clean · run-history DB copied · suites collect · flat executes
and passes · POM executes and passes.

**Exit codes:** `0` = PASS, `1` = FAIL

---

## eval/ — Automated Evaluation Harness

Regression detection for the test generation pipeline. Measures placeholder
resolution accuracy, test pass rate, and false positive rate against frozen
golden answer keys.

**Baseline:** 79.1% resolution accuracy (34/43 placeholders correct)

```bash
python scripts/eval/eval_harness.py run --mode static        # Fast, offline (<1s)
python scripts/eval/eval_harness.py run --mode full           # Resolution + test execution
python scripts/eval/eval_harness.py run --min-accuracy 79     # Quality gate (exit 2 if below)
python scripts/eval/eval_harness.py baseline --save            # Save reference baseline
python scripts/eval/eval_harness.py compare                    # Current vs. baseline
python scripts/eval/eval_harness.py dataset --validate         # Validate golden keys
```

**When to run:** Before shipping changes to pipeline/resolver/prompt files.
**Not part of ship-it** — it's a pre-commit quality gate for pipeline changes.

**Maintenance:** Golden keys decay — re-validate locators every 3-6 months.

Full usage guide: `scripts/eval/README.md`

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

*Last updated: 2026-07-15*
