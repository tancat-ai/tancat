---
purpose: >
  Per-deployment usage meter + free-tier cap (Phase 6e, spec §5.5). Counts runs from the existing
  evidence/run_results.sqlite (30-day window), evidence exports from a local ledger, and storage
  used from the workspace; enforces the free tier (25 runs / 10 exports per month by default)
  with an upgrade prompt. Local only — no telemetry, no network.
lines: ~352
created: "2026-09-05"
---

# `src/usage_meter.py`

## High-Level Purpose

A "run" = one pytest execution of a generated package (the value moment). The meter reads the
existing `evidence/run_results.sqlite` (runs are already persisted there) plus a small local
ledger for evidence exports (which had no persisted record), and computes storage used on
demand. LLM tokens are reported as `None` (a provider may not report `usage` — spec §9 Q6
accepts unknown).

Free tier: N runs + M evidence exports per 30 days. At the limit, new **runs** block with an
upgrade prompt; paid tiers are unlimited. Config, all local: `AITEST_FREE_TIER_RUNS` (25),
`AITEST_FREE_TIER_EXPORTS` (10), `AITEST_ENFORCE_FREE_TIER=0` (self-hoster override).
The gate never fires for paid tiers (a valid license's tier has no caps).

## Public API

### `class UsageMeter(*, run_db_path=None, ledger_path=None, storage_root=None, now=None, env=None)`
Resolves storage paths lazily (defaults to `get_storage()`), accepts injectable paths + a clock
+ env for hermetic tests.

- **Counters**
  - `count_runs_this_month(now=None) -> int` — `SELECT COUNT(*) FROM runs WHERE created_at >= ?`
    on the 30-day window (read-only URI connection).
  - `count_exports_this_month(now=None) -> int` — ledger entries within the window.
  - `storage_bytes() -> int` — walk `generated_tests/` + `evidence/` under the storage root.
- **Limits & enforcement**
  - `runs_limit` / `exports_limit` — `None` for paid tiers; env-overridable free caps otherwise.
  - `enforcement_on` — `AITEST_ENFORCE_FREE_TIER != "0"`.
  - `assert_run_allowed()` — raises `FreeTierLimitError` when a free run is beyond the cap.
  - `assert_export_allowed(format_name)` — caps only the Jira export on the free tier (core
    CSV/NDJSON/JUnit/HTML stay free — the free tier's own claims).
- **Bookkeeping**
  - `record_export(format_name, output_path)` — appends to the ledger (idempotent).
  - `summary() -> UsageSummary` — one view: tier, license status, window, runs/exports
    used/limit/remaining, storage bytes, enforcement flag.
- **Ledger** — `evidence/.usage_ledger.json` (atomic tmp+replace), migration-tolerant.

### `class UsageSummary`
`tier`, `license_status`, `windows_start/end`, `runs_used/limit/remaining`,
`exports_used/limit/remaining`, `storage_bytes`, `llm_tokens`, `enforcement_on`;
`to_dict()` → the `--json` usage section shape used by the UI panel + `ci_generate`.

### `class FreeTierLimitError(RuntimeError)`
`run_remaining` / `export_remaining` + `upgrade_prompt` ("hit the free-tier limit — upgrade to a
paid tier..."). Raised by the gates; `PipelineRunService.run_saved_test` re-raises with the
self-hoster env hint.

### Module helpers
- `monthly_window(now=None) -> (start_iso, end_iso)` — the current 30-day UTC window.

## How It Works (internals)

### `UsageMeter.count_runs_this_month(now)` — the run count
Opens `run_db_path` read-only (`file:...?mode=ro`, 5s busy timeout) and counts `runs` rows whose
ISO `created_at` is inside the window. A missing/corrupt DB degrades to 0 (never raises — the
meter must not break generation).

### `UsageMeter._load_ledger()/_save_ledger()` — the export ledger
`{exports: [{format, output, at}]}`; `at` is ISO and window-filtered; save is atomic
(tmp + `os.replace`). `record_export` is append-only and idempotent.

### `UsageMeter.runs_limit/exports_limit/_int_env` — config resolution
`effective_tier()` (from the license layer) decides paid vs free; free caps come from
`limit_for("free", ...)` overridden by `AITEST_FREE_TIER_RUNS`/`_EXPORTS`.

### Internal utilities
- `_parse_iso(value)` — tolerant ISO parse, naive → UTC.
- `_epoch(now)` — datetime → epoch int for the license layer's clock override.
- `_UPGRADE_PROMPT` — module-level constant shared by the error and the gates.