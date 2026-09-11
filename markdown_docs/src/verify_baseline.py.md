# `src/verify_baseline.py`

## High-Level Purpose

Expected-red baseline for the production verification gate (B-058).
`scripts/verify_production.py` has been continuously RED since 2026-08-01:
each verified site fails exactly two gates — `Pipeline resolved all
placeholders` and `No pytest.skip` — because ASSERT targets cannot be
resolved and the pipeline emits honest `pytest.skip()` lines instead. Without
a recorded baseline, every session re-litigates "is this a regression?" from
scratch.

This module records that known-red state (`scripts/verify_production_baseline.json`)
and compares a fresh run against it:

- a gate that fails and is **not** in the known set → regression (exit 1)
- a known-failing gate that now passes → improvement (reported, exit 0)
- the unresolved-placeholder count exceeding the recorded budget → regression

The logic is pure (JSON load + comparison) so it is unit-tested in
`tests/test_verify_baseline.py`; `scripts/verify_production.py` stays thin.

## Module Metadata

- **Lines:** ~231
- **Imports:** `json`, `re`, `dataclasses`, `pathlib`, `typing.Any`

## Key Concepts

- **Stable gate key** — gate names embed per-run values (`"Test execution
  (44.1s)"`, `"LLM connected (openai-local/qwen)"`). `stable_gate_key()`
  strips a trailing parenthesised suffix so a baseline recorded on one
  machine matches a run on another.
- **Expected-red baseline** — the checked-in record of which gates are
  *known* to fail; it is data, not a test.
- **Unresolved ceiling** — the number of emitted `pytest.skip` lines the
  baseline tolerates per site. It is a *variance ceiling* (2x the observed
  historical max), not an exact count: LLM variance moves it run to run
  (0–4 across 67 historical runs). More than the ceiling is a regression
  even if the gate names look the same.

## Constants

- `_DYNAMIC_SUFFIX` — `re.compile(r"\s*\([^()]*\)\s*$")`. Strips only a
  trailing parenthesised group, so `"Test functions >= 5"` is untouched.

## Dataclasses

### `SiteBaseline`
Recorded expected-red state for one site: `known_failing_gates`
(normalised), `max_unresolved_placeholders` (variance ceiling),
`known_unresolved_placeholders` (informational), `expected_failing_tests`
(short-name prefixes of ASSERT-heavy criteria that sometimes resolve-but-wrong
instead of skipping — e.g. `test_07`), `expected_min_tests`. Frozen.

### `VerifyBaseline`
The whole baseline: `version`, `recorded`, `recorded_commit`, `sites`,
`note`. Frozen.

### `SiteComparison`
Outcome for one site: `new_failures`, `tolerated_failures`, `fixed_gates`,
`new_failed_tests`, `tolerated_failed_tests`, `unresolved_count`,
`unresolved_budget`. Properties:
- `unresolved_over_budget` — `max(0, count - budget)`
- `regressed` — a new gate failure, a new failing test, or the unresolved
  count is over budget
- `improved` — a known-red gate now passes with no regression

### `BaselineComparison`
Aggregate across sites; `regressed` is True if any site regressed. Flattens
`new_failures` / `tolerated_failures` / `fixed_gates` / `new_failed_tests` as
`"<site>: <name>"`.

## Functions

### `stable_gate_key(name: str) -> str`
Returns the machine-stable identity of a gate name.

### `short_test_name(node_id: str) -> str`
Returns the parameter-free short name of a pytest node id
(`test_a.py::test_07_example[chromium]` → `test_07_example`).

### `load_baseline(path: Path) -> VerifyBaseline`
Reads and parses a baseline JSON file. Raises `FileNotFoundError` if absent,
`ValueError` if malformed or missing required keys.

### `parse_baseline(data: Any, source: str = "<inline>") -> VerifyBaseline`
Validates a parsed mapping and converts it into a `VerifyBaseline`.
Normalises every `known_failing_gates` entry through `stable_gate_key()`.

### `compare_site(site_id, gates, unresolved_placeholders, baseline, failed_tests=None) -> SiteComparison`
Compares one site's fresh run against its baseline entry. `gates` is a list
of `(gate_name, passed)` pairs. Unresolved placeholders are the emitted
`pytest.skip` lines. A failing test that matches no
`expected_failing_tests` prefix is a regression; the `Test execution` gate
is tolerated only when *every* failing test is expected.

### `compare_run(baseline, runs) -> BaselineComparison`
Compares every site in `runs` (`site_id -> (gates, unresolved, failed_tests)`)
against the baseline. A site absent from the baseline is compared against an
empty `SiteBaseline`, so any failure there is a regression.

## How It Works (internals)
### `stable_gate_key(name)` — gate-name normalisation
- `_DYNAMIC_SUFFIX` — `re.compile(r"\s*\([^()]*\)\s*$")`; strips only a trailing parenthesised group, so duration/provider suffixes drop while static names like `Test functions >= 5` survive.

### `compare_site(...)` — per-site verdict
- `_matches_expected(test_name, expected_prefixes)` — prefix match against the baseline's `expected_failing_tests`, so `test_07_example` matches the recorded `test_07` even though the LLM names the test differently each run.

### Internal flow
1. `load_baseline` / `parse_baseline` validate the JSON and normalise gate keys.
2. `short_test_name` maps pytest node ids to bare names.
3. `compare_site` splits failing tests into tolerated vs new, then walks the gates: known-red → tolerated, `Test execution` failing with only expected test failures → tolerated, everything else failing → new failure.
4. `compare_run` aggregates sites; a site missing from the baseline is compared against an empty `SiteBaseline` so any failure is a regression.

## Consumers

- `scripts/verify_production.py` — `--baseline` (regression verdict),
  `--save-baseline` (record), `--check-baseline` (offline CI validation).
- `tests/test_verify_baseline.py` — 24 unit tests, including one that loads
  the committed `scripts/verify_production_baseline.json`.
