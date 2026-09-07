# scripts/

Utility and automation scripts for the tancat-ai/tancat project.

## Quick Reference

| Script | Purpose | Needs |
|--------|---------|-------|
| `smoke.py` | Fast pre-commit smoke test (<1s) | Nothing — fully offline |
| `audit_generated_tests.sh` | Read-only safety audit of `generated_tests/` — git-depth check, .gitignore validation, evidence sha256 snapshot. Non-destructive (exit 2 = untracked artifacts at risk) | Nothing — offline |
| `debug.py` | Unified diagnostic CLI | Varies by command (see below) |
| `debug_step_through.py` | Step-by-step interactive debugger for generated tests (headed) | Browser + Enter |
| `uat.py` | End-to-end pipeline validation (static checks) | Browser + LLM |
| `verify_production.py` | Production gate — generates, executes, validates evidence | Browser + LLM |
| `ci_generate.py` | Headless test-generation driver (Phase 7) — exit codes 0/1/2, `--json` | LLM endpoint (mock + fake LLM for hermetic runs) |
| `fake_llm.py` | OpenAI-compatible fake LLM server (canned skeletons) — hermetic pipeline testing | Nothing — localhost |
| `mock_server.py` | Robust mock-site HTTP server (concurrent Playwright-safe) | Nothing — localhost |
| `ci_action_selftest.py` | Local Docker self-test for the Phase 7 CI action (build + generate/run/cache/comment/adapt gates, GitHub + GitLab mock APIs) | Docker |
| `ci_gitlab_real_project_test.py` | Real GitLab.com gate for the Phase 7c template (push pipeline → junit → MR note idempotency). Needs `GITLAB_TOKEN` (api scope) in `.env` | GitLab.com + API |
| `ci_slash_commands.py` | Slash-command core (`/adapt`, `/ignore`) — parse comments, render reply payloads | Nothing — offline |
| `export_gate.py` | Export gate — exports flat+POM, validates artifacts, runs the exported suites | Browser (golden: localhost only) |
| `gate_full.py` | Full gate chain — smoke → unit → eval-static → verify_production → export_gate | `--offline` = nothing; full = Browser + LLM |
| `maintenance/project_sanitizer.py` | Project housekeeping (CI) | Nothing |
| `maintenance/cli_e2e_validation.py` | CLI pipeline syntax validation | Browser + LLM |
| `eval/eval_harness.py` | Eval harness — regression detection vs. golden keys | Nothing (static) / Browser (full) |
| `eval/learning_impact.py` | AI-059 sidecar metrics and controlled cold/warm store comparison | Nothing (metrics) / deterministic mock runner (baseline) |
| `map_3d/*.py` | 3D documentation map generation | Nothing |

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

### AI-059 learning-impact metrics

The metric path is read-only and consumes existing evidence sidecars. Ratios
are `0.0..1.0`; false positives require a manual-review annotation:

```bash
python scripts/eval/learning_impact.py metrics --evidence-dir evidence
```

The controlled baseline path runs the same command against independently
restored cold/warm snapshots, disables auto-learning with
`AI059_DISABLE_AUTO_LEARN=1`, and writes one metrics file per leg:

```bash
python scripts/eval/learning_impact.py baseline \\
  --cold-snapshot lab/stores/golden.db \\
  --warm-positive-snapshot lab/stores/golden-positive.db \\
  --store-target evidence/rag_store.db \\
  --pipeline linear --temperature 0 --thinking off \\
  --provider openai-local \\
  --command python -m pytest generated_tests/{leg}
```

---

## debug/ — Targeted Debug Scripts

These remain as specialized tools for specific scenarios:

| Script | Purpose |
|--------|---------|
| `debug_pipeline.py` | Full pipeline trace with stage-by-stage diagnostics |
| `debug_cli_interactive.py` | CLI interactive walkthrough debugger |
| `debug_saucedemo_inventory.py` | Scrape SauceDemo inventory + test resolution |
| `debug_saucedemo_login.py` | Login to SauceDemo → scrape inventory → test resolution |
| `cdp_attach.py` | Attach to a CDP-enabled browser (port 9222) and dump the accessibility tree of the Streamlit tab — co-working bridge (`tabs` / `ax` / `eval`) |

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

## ci_action_selftest.py — Local Docker Self-Test for the CI Action

Exercises the Phase 7 Docker action (`Dockerfile.action` + `action/entrypoint.sh`)
exactly the way `.github/workflows/ci-cd-action.yml` does on GitHub, but locally:
builds the image, then runs it with GitHub's Docker-action env surface
(`INPUT_*`, `GITHUB_WORKSPACE`, `GITHUB_OUTPUT`), the repo mounted at
`/github/workspace`, and a **mock GitHub API on the host** so comment posting is
verified against real HTTP traffic (`host.docker.internal` — Docker Desktop NAT):

1. **generate-only** + `self-test: true` — hermetic mock site + fake LLM inside
   the container → driver JSON contract, persisted package.
2. **run-existing** + `self-test: true` — pytest `--junitxml` + AI-028 evidence
   JUnit + report against the generated package → JUnit well-formedness, report
   payload shape, referee exit code.
3. **generate-and-run (cache miss)** — generates, seeds `actions/cache`-shaped
   package cache, pytest, §6 comment payload, idempotent POST to the mock API.
4. **generate-and-run (cache hit)** — reuses the cached package (no
   regeneration), comment EDITED not duplicated.
5. **slash-command /adapt** — sabotages a locator, runs verified adaptation
   (locator-only patch → re-run → assertion gate → keep), reply POSTED.
6. **slash-command /ignore** — reply renders the `.ai-test-ignore.yml` entry.
7. **gitlab generate-and-run** — Phase 7c parity: `INPUT_PLATFORM=gitlab` posts
   the §6 payload as an **MR note** to a host-side mock GitLab API (notes
   endpoint, `PRIVATE-TOKEN`, URL-encoded project path); the cache-hit reuses
   the GitHub miss gate's seeded package (no duplicate ~2.5 min generation).
8. **gitlab slash-command /adapt** — sabotages the CACHED package, verified
   adaptation fixes it, reply posted as an MR note.
9. **gitlab slash-command /ignore** — reply posted as an MR note.

The GitLab gates assert the REST shapes that differ from GitHub: MR notes live
under `/projects/:id/merge_requests/:iid/notes`, edits are **PUT** (not
PATCH), auth is `PRIVATE-TOKEN`.

```bash
python scripts/ci_action_selftest.py            # build + run + assert (39 gates, ~15 min cold)
python scripts/ci_action_selftest.py --skip-build   # ~10 min; refused when the image is stale
python scripts/ci_action_selftest.py --keep     # keep .ai-test-workspace/ on pass
```

Exit codes: `0` all green, `1` a gate failed, `2` usage/build error.

## ci_slash_commands.py — Slash-Command Loop Core

Parses PR-thread `/adapt <test>` and `/ignore <test>` comments and renders the
reply payloads the slash-command workflow posts (via `ci/platform/github.py`).
Platform-neutral — no GitHub imports, fully offline-testable:

- `/adapt` — reply from an `adaptation.json` (kept/reverted summary).
- `/ignore` — the exact `.ai-test-ignore.yml` entry to commit (reason required —
  the anti-rug rule), with a suggested `match` regex from the failure message.
