# `scripts/verify_production.py` — Production Verification

## Purpose
End-to-end product verification: runs the full generation → resolution → execution → evidence pipeline against known demo sites and emits a PASS/FAIL verdict via gate checks. The single source of truth for "does the product work?" (AGENTS.md §12).

## Usage
```bash
python scripts/verify_production.py saucedemo          # one site
python scripts/verify_production.py --all-sites        # saucedemo + automationexercise
python scripts/verify_production.py --flat             # flat mode (default is POM)

# B-058 — expected-red baseline (see below)
python scripts/verify_production.py --baseline                 # verdict vs scripts/verify_production_baseline.json
python scripts/verify_production.py --save-baseline            # re-record the expected-red state
python scripts/verify_production.py --check-baseline           # offline validate (CI job)
```

## Sites
| site | URL | Story |
|------|-----|-------|
| `saucedemo` | https://www.saucedemo.com | login → add to cart → checkout (5+ tests) |
| `automationexercise` | https://automationexercise.com | browse → add to cart → checkout (5+ tests) |

## Gates (13 per site)
LLM connected → Pipeline generation → No unresolved placeholders → Test function count → Evidence tracker calls → `@pytest.mark.evidence` decorators → POM imports → Pipeline unresolved → Execution (runs the generated tests) → Evidence JSON → Evidence steps → (verdict).

## Key Logic
- **Credentials (2026-08-03):** saucedemo gets a `CredentialProfile` (env-overridable `SAUCEDEMO_USERNAME`/`SAUCEDEMO_PASSWORD`, default `standard_user`/`secret_sauce`, matching `scripts/eval/eval_resolver.py`) passed to `TestOrchestrator` — without it the stateful scraper captures the login wall, not the cart
- LLM provider from `LLM_PROVIDER` env (defaults to the `.env` openai-local config); avoids auto-detect which can pick the wrong provider when LM Studio is shared
- Generates tests to `generated_tests/verify_<site>_<timestamp>/`, executes with a generated conftest (evidence tracker fixture), and validates evidence JSON + step counts
- **Cleanup (B-058):** a run is deleted when it is *expected-red* (baseline PASS) and kept only when it regressed or `--keep` is passed — this stops the old `verify_*` dir pile-up (65 dirs before).
- **Execution timeout:** `max(120, min(600, n_tests * 60))` — the old `30s/test, cap 300s` failed a healthy automationexercise suite (7 tests > 210s while passing/skipping). The timeout detail counts only tests with a terminal evidence status.

## Expected-red baseline (B-058)
`verify_production` is permanently RED with the known ASSERT-resolution class, so its raw verdict carries no signal. The baseline records the expected-red state and turns the verdict into "regression or not":

- **File:** `scripts/verify_production_baseline.json` — per site: `known_failing_gates` (`Pipeline resolved all placeholders`, `No pytest.skip`), `max_unresolved_placeholders` (variance *ceiling*, not the exact count), `known_unresolved_placeholders`, `expected_failing_tests` (ASSERT-heavy criteria that sometimes resolve-but-wrong).
- **Comparator:** `src/verify_baseline.py` (`compare_run`) — hard regression = NEW gate failure, NEW failing test, or unresolved count over the ceiling. Known-red gates and expected-failing tests are tolerated and reported; a known-red gate that now passes is reported as an improvement.
- **`--baseline`** prints the comparison and exits 0 when only known-red state is present; **`--save-baseline`** records the current run (2x headroom on the skip ceiling); **`--check-baseline`** validates the file offline (no LLM/browser) — this is the CI `verify-baseline` job.

## How It Works (internals)
### Baseline CLI helpers (B-058)
- `_check_baseline(path)` — offline validation: loads the file, rejects unknown site ids, warns on missing entries
- `_parse_failed_tests(stdout)` — pulls short test names from pytest's `FAILED <path>::<name>` short-summary lines (dedupes, strips `[...]` params)
- `_unresolved_descriptions(skip_lines)` — extracts the quoted placeholder descriptions from emitted `pytest.skip(...)` lines
- `_recorded_commit()` — `git rev-parse --short HEAD`, or `"unknown"` outside a checkout
- `_write_baseline(path, results)` — serialises the run (failing gate keys, 2x skip ceiling, unresolved names, failing tests) to baseline JSON
- `_run_pairs(site_result)` — `[(gate name, passed)]` for the comparator
- `_print_baseline_comparison(comparison)` — renders tolerated failures, unresolved count vs ceiling, improvements, and NEW failures per site

## Related
- `src/orchestrator.py` — `TestOrchestrator.run_pipeline()`
- `src/llm_client.py` — LLM client
- `src/verify_baseline.py` — expected-red baseline comparator (`--baseline`)
- `scripts/verify_production_baseline.json` — recorded expected-red state
- `scripts/eval/eval_harness.py` — static resolution accuracy (pre-commit quality gate)

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `SiteConfig` (class): Per-site configuration for the verification run.
- `Gate` (class)
- `Gate.key` (method of `Gate`): `Gate.key() -> str` - Stable identity - strips the dynamic duration/provider suffix.
- `SiteVerification` (class)
- `SiteVerification.total` (method of `SiteVerification`): `SiteVerification.total() -> int`
- `verify_site` (function): `verify_site(site_id: str, url: str, user_story: str, conditions: str, expected_min_tests: int, expected_min_evidence_steps: int, verbose: bool = False, pom_mode: bool = True) -> SiteVerification` - Run the full verification pipeline for one site.
- `parse_args` (function): `parse_args() -> Any`
- `main` (function): `main() -> int`
- `PROJECT_ROOT` (constant): `PROJECT_ROOT = Path(__file__).resolve().parent.parent`
- `DEFAULT_BASELINE_PATH` (constant): `DEFAULT_BASELINE_PATH = PROJECT_ROOT / 'scripts' / 'verify_production_baseline.json'`
- `SAUCEDEMO_STORY` (constant): `SAUCEDEMO_STORY = 'As a user, I want to log in to the shopping site, add it...`
- `SAUCEDEMO_CONDITIONS` (constant): `SAUCEDEMO_CONDITIONS = '1. Log in with username standard_user and password secre...`
- `AUTOMATIONEXERCISE_STORY` (constant): `AUTOMATIONEXERCISE_STORY = 'As a customer, I want to browse products on the website...`
- `AUTOMATIONEXERCISE_CONDITIONS` (constant): `AUTOMATIONEXERCISE_CONDITIONS = "1. Navigate to the automationexercise.com home page and...`
- `SITES` (constant): `SITES = {'saucedemo': {'url': 'https://www.saucedemo.com', 'user_...`
- `CONFTEST_TEMPLATE` (constant): `CONFTEST_TEMPLATE = textwrap.dedent(' """Conftest for production verification...`
