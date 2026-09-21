# Agent-Callable Run & Compare — "check nothing broke, for $0 in LLM tokens"

**Created:** 2026-09-20
**Status:** Spec — decisions D1–D14 drafted, **not yet locked**. Implementation not started.
**Priority:** Future — post-launch. Next up among the Tier 6 expansions.
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` → **Tier 6 → FC-07** (canonical tracker)
**Related (BACKLOG-owned, tactical):** B-073 (cost/turn metrics), B-074 (AXI CLI principles), B-075 (MCP research prototype)
**Baseline precedent to mirror:** `scripts/verify_production_baseline.json` (version / `recorded` / `recorded_commit` / note) + the eval harness `baseline --save` / `compare` pair

**Gate (narrow).** This feature **reports** trust; it does not need it. The run path never
touches the resolver, so it is **not** gated on the known-red ASSERT class. It is gated on
three things: (1) skips must be visible — a 30%-skipped suite must never read as "all
verified"; (2) flaky vs regression must be right; (3) baseline selection must be right.
**Depends on:** existing, stable modules only — `src/pipeline_run_service.py`, `src/run_result_persistence.py`, `src/pytest_output_parser.py`, `src/run_history_cli.py`. **No protected files.** The work is additive.

---

## 1. What This Is

A developer works with a coding agent. The agent writes the unit tests, as it does
when we develop this repo. The user then says:

> *"Check nothing has broken."*

The agent re-runs **tancat's existing generated tests** — the durable artefacts from
a previous generation — compares the result to the previous run, and answers. Three
properties make this worth more than asking the agent to poke at the app itself:

1. **Cheap.** A re-run is `pytest`. It costs **zero LLM tokens**. An ad-hoc
   "does it still work?" exploration costs tokens every single time.
2. **Comparable by construction.** The previous run is stored, so the answer is a
   *delta* — what changed — not a fresh subjective opinion. Two ad-hoc explorations
   are not comparable, because they exercise different things each time.
3. **Auditable.** The run leaves evidence artifacts and a persisted run record. An
   agent's chat summary leaves nothing.

The selling point is the pair: **the agent checks once; tancat makes it permanent.**
An agent alone explores and moves on. tancat turns that moment of verification into
a re-runnable regression suite.

**What this is NOT:**

- **Not generation.** Generation stays a separate, expensive verb (§3, D1).
- **Not a new test runner.** It reuses `PipelineRunService.run_saved_test` (§2).
- **Not a replacement for the human UI.** Same run record, a second renderer
  (`src/ui/ui_run_comparison.py` keeps working unchanged).
- **Not a cloud service.** Local, and the local LLM path stays the default.
- **Not a gatekeeper.** It reports; it never blocks a merge by itself.
- **Not a self-healing trigger.** Self-heal stays opt-in (§14, D10).

---

## 2. Architecture Findings (code + graphify audit, 2026-09-20)

The important finding: **most of this already exists.** It is a wiring job, not new
machinery. Everything below was verified against the code, not against docs.

### 2.1 What exists today

| Capability | Where it lives |
|---|---|
| Execute a saved suite + parse output | `src/pipeline_run_service.py` → `PipelineRunService.run_saved_test()` (L97) → `PipelineExecutionResult` (L85) |
| Build the pytest command | `src/run_utils.py` → `build_pytest_run_command()` (L54), `get_failed_nodeids()` (L19) |
| Failed-only re-run | `run_saved_test(rerun_failed_only=True, previous_run=…)`, `merge_rerun_results()` (L55) |
| Parse pytest output | `src/pytest_output_parser.py` → `parse_pytest_output()` (L113) → `RunResult` (L67); display formatter (L304) |
| Persist a run | `src/run_result_persistence.py` → `persist_run_result()` (L100) → `run_results.sqlite` |
| **Regression delta** | `RunComparison` (L301): `improved`, `regressed`, `new_failures`; `compare_runs()` (L311) |
| Compare last two runs | `compare_latest_runs()` (L346) — returns `None` when fewer than two runs exist |
| **Flaky detection** | `get_flaky_tests()` (L247) |
| Run history + stats | `compute_run_history()` (L206), `run_stats_by_package()` (L191), `load_all_run_results()` (L179) |
| Human ASCII views | `src/run_history_cli.py` → `format_run_history_table()` (L23), `format_flaky_tests_table()` (L71), `format_run_comparison()` (L112), `format_full_history_summary()` (L179) |
| Human chart view | `src/run_history_chart.py` → `build_run_history_chart()` (L84) |
| Headless precedent | `scripts/ci_generate.py` — argparse, `--json`, exit codes `EXIT_OK=0` / `EXIT_GENERATION_ERROR=1` / `EXIT_CONFIG_ERROR=2`, workspace isolation, danger-zone allow-list |
| Free-tier run metering | `src/usage_meter.py` → `UsageMeter.assert_run_allowed()` already gates `run_saved_test` |

`RunComparison.regressed` **is** the answer to "did anything break". It is computed,
stored, and unit-tested (`tests/test_run_result_persistence.py::TestCompareRuns`).

### 2.2 The gaps — this is the actual work

1. **There is no `run` verb.** Generation has one (`scripts/ci_generate.py`). Running
   is reachable only through the Streamlit UI, the interactive CLI
   (`src/cli/pipeline_runner.py`), and the CI entrypoint. There is no non-interactive,
   agent-callable command.
2. **There is no JSON envelope.** `RunComparison` is a dataclass with ASCII renderers
   only. `PersistedRunResult.to_dict()` (L377) is a *storage* shape, not an agent
   contract — it is not versioned and not minimal.
3. **There is no `verdict`.** No single field answers the question. The agent must
   currently reconstruct it from three lists.
4. **No baseline policy.** `compare_latest_runs()` compares the globally last two runs.
   The agent needs "this suite's previous run", with an explicit override and a defined
   answer when no baseline exists.
5. **No exit-code contract for runs.** `ci_generate.py` defines 0/1/2 for *generation*.
   Runs need their own, and must distinguish a regression from an infrastructure error.
6. **No MCP wrapper.**
7. **Metering is unconsidered for agent use.** `run_saved_test` already calls
   `UsageMeter().assert_run_allowed()`. An agent that polls would spend the free-tier
   budget. This needs a decision (§14, Q1).

### 2.3 Token cost of the current path (why the envelope matters)

`format_pytest_output_for_display()` caps at `max_lines=80`. A failing suite produces a
long log. A comparison produces three lists. The agent needs the three lists, sized
small, plus one line per failure — not the log.

---

## 3. The Verb Contract

Two verbs, **always separate** (D1).

```
tancat generate --story <file> --url <url> [--json]     # LLM, minutes, costs tokens
tancat run [--suite <path>] [--baseline <run_id>] [--json]   # pytest, no LLM tokens
```

`tancat run` must expose the existing options that already exist on
`run_saved_test()`: `--failed-only` (`rerun_failed_only`), and a suite/package path.
It must be flag-complete: **zero prompts, zero menus.**

### 3.1 Exit codes

| Code | Meaning |
|---|---|
| 0 | `clean` or `improved` — nothing broke |
| 1 | `regression` — `regressed` or `new_failures` is non-empty |
| 2 | config/setup error — bad path, no suite found, unusable arguments |
| 3 | `error` — run infrastructure failure: pytest timeout, crash, unparseable output |

**Code 3 is the load-bearing one.** A timeout that exits 0 is the worst possible
failure mode: the agent reports "nothing broke" when nothing was actually tested.
An infrastructure failure must never read as clean (D9). Where the comparison cannot
be made, the tool says so loudly.

### 3.2 `verdict` enum

| Verdict | Condition |
|---|---|
| `clean` | Baseline exists; no regressions, no new failures |
| `improved` | `improved` non-empty; no regressions |
| `regression` | `regressed` or `new_failures` non-empty |
| `error` | The run itself failed (see code 3) |
| `unknown` | No baseline available — nothing to compare against |

Note `clean` does **not** mean "all tests pass". A suite with three long-standing red
tests that were red in the baseline is `clean` — nothing *new* broke. The pre-existing
failures are still visible in `summary.failed` and in `failures`. This distinction is
the point: the agent's question is about *change*.

---

## 4. The JSON Envelope

```
{
  "schema_version": 1,
  "verdict": "regression",
  "run_id": "2026-09-20T14-03-11",
  "baseline_run_id": "2026-09-19T09-12-40",
  "suite": "generated_tests/test_pkg_20260919_2215",
  "summary": { "total": 48, "passed": 43, "failed": 3, "skipped": 2, "errors": 0 },
  "delta": {
    "regressed": ["test_tc01_14_apply_discount_code"],
    "new_failures": [],
    "improved": ["test_tc01_09_remove_item"],
    "resolved": []
  },
  "flaky": ["test_tc02_03_session_timeout"],
  "failures": [
    { "test": "test_tc01_14_apply_discount_code",
      "class": "locator",
      "detail": "Timeout waiting for #discount-apply" }
  ],
  "evidence_dir": "generated_tests/evidence/2026-09-20_140311",
  "duration_s": 93.5,
  "usage": { "llm_tokens": 0, "runs_used": 1 }
}
```

Design rules:

- **`verdict` first.** A shell agent can read one field, or none (§3.1 exit code).
- **Delta, not absolute.** `regressed` answers the question; `summary` is context.
- **`flaky` is a sibling of the delta, never inside it** (D5, §5).
- **`failures` is classified and capped.** One line each, class from
  `src/failure_classifier.py`. Raw logs are opt-in via `--full` / `--log`.
- **`usage.llm_tokens: 0`** for a plain run. This is the selling point stated in the
  payload, where an agent can repeat it.
- **`schema_version` is mandatory** and golden-fixture tested (§11, D8).

Sizing: default output should stay under ~40 lines for a realistic suite. Provide
`--fields` (select keys) and `--compact` (drop `failures` detail), per B-074.

---

## 5. Baseline, Flaky, and Coverage Semantics

### 5.1 What a baseline actually is

Six real situations, and **only one of them** uses "the previous run":

| # | Situation | Correct baseline | Why "previous run" fails |
|---|---|---|---|
| **S1** | Feature branch: run at start, run at end | The run pinned at branch start | Mid-work runs sit between. Comparing to the last one compares to 20 minutes ago, not to pre-work |
| **S2** | Release / acceptance regression (sprint end, wide suite, daily or weekly) | The last **accepted** run on that environment | The previous run may itself be red, and the baseline must survive a week of unrelated runs |
| **S3** | Iterate loop: change something, re-run, "did I just break it?" | The previous run, minutes ago | This is the **only** case where "previous" is right — and it is the most frequent, which is why it is the tempting default |
| **S4** | CI on a pull request | The target branch's latest green run (`main`) | The PR's own runs are all suspect by definition |
| **S5** | Same suite, different targets (local / staging / prod-smoke) | Same environment only | Cross-environment comparison is meaningless |
| **S6** | First run, or the suite changed since the baseline | `unknown` / partial | Nothing to compare; added tests already land in `new_failures` |

**Therefore: a baseline is not a position, it is a labelled record.**

```
tancat run --baseline save:before-work    # tag this run as a baseline
tancat run --baseline before-work         # compare against that tag
```

Scope — suite and environment — is a **property of the tag**, not of the comparison.

Resolution order when `--baseline` is not given (D6):

1. a labelled baseline for this suite + environment, else
2. the previous run of this suite, else
3. `unknown`

**`unknown` is a first-class answer.** No baseline is not a failure, and must not be
reported as `clean`.

### 5.2 The user must know what they are comparing to

The user must always be able to see **what the baseline is**. This is the same principle as
running the eval harness against a previous baseline — but stricter, because the eval
harness prints only "BASELINE COMPARISON" without naming the baseline's date or commit.

Mirror `scripts/verify_production_baseline.json`, which already carries provenance:

| Field | Purpose |
|---|---|
| `version` | Format version — an old baseline is readable or rejected explicitly |
| `recorded` | Date — tells the user how stale the baseline is |
| `recorded_commit` | The exact code state the baseline was taken from |
| `note` | Why it was recorded, and when it should be re-recorded |

A baseline with no provenance is untrustworthy: the user cannot tell whether they are
comparing against yesterday's work or against something from three months ago. So the
baseline's identity is rendered in **both** outputs:

```
baseline: "before-work"  (2026-09-20, commit 4f2a1c9, recorded by user)
baseline_verdict: clean
```

Recording a baseline must also be re-recordable — a documented `--save-baseline`-style path,
as `verify_production.py` has, so baselines are refreshed deliberately and not silently
drifted.

### 5.3 Flaky is not a regression

`get_flaky_tests()` already identifies tests that have both passed and failed across
history. Rule: **a known-flaky test must not be reported as `regression`.** It goes in
the `flaky` bucket.

Rationale: this is the trust-critical field. If a known-flaky test is reported as a
regression, the agent tells the user something broke when nothing did. The user stops
trusting the tool after two or three false alarms, and the whole feature is dead.

Escalation (open question, Q5): a flaky test that fails N consecutive runs should
probably graduate to `regressed`. Left undefined in v1.

### 5.4 `removed` is a missing bucket

`RunComparison` computes `improved`, `regressed`, and `new_failures`. It does **not**
compute `removed`. A test that existed in the baseline and is now gone produces **no
signal at all** — including a test that was *failing* and has been deleted.

Consequence: a suite can be gutted and the envelope still says `clean`. This is worst in
S2, where the suite legitimately changes between releases and where a "clean" verdict is an
acceptance gate. Add a `removed` bucket to `delta`, so coverage loss is never silent.

### 5.5 If the baseline is red, say so

"No new regressions" against a baseline that was itself failing is misleading. The envelope
must report the baseline's own state:

- `baseline_verdict: clean | failing | error | unknown`
- When the baseline is not clean, both the human output and the JSON must say so, and the
top-level `verdict` must not be read as a clean bill of health.

Same family as D9: never let a bad state look like a good one.

---

## 6. Metering and Cost Reality

- A plain run consumes **0 LLM tokens**. This is verifiable, not marketing — the run
  path is `subprocess` → pytest → text parse.
- Self-heal would consume tokens. It is **not** invoked by `tancat run` (D10).
- `UsageMeter.assert_run_allowed()` already gates runs. Two consequences:
  1. An agent that re-runs on every commit will spend the free-tier run budget.
  2. The envelope must report `usage.runs_used` so the agent can see the cost it is
     incurring. Silence here would be dishonest.
- Decision needed (Q1): does an agent-triggered run count against the free tier, or is
  agent usage exempt/separately metered?

---

## 7. The MCP Wrapper (second, and thinner)

Only after the CLI exists and is proven (D2 in B-075's own gates).

```
tancat mcp --stdio
```

- Exposes **at most 3 tools**: `generate_test`, `run_tests`, `run_status`.
- **Shells out to the CLI.** It must never import pipeline internals directly. That is
  how MCP wrappers drift from the product and quietly bypass guard rails.
- Precedent already in this repo: `zg server --stdio` (see `AGENTS.md` §12c).

### 7.1 Why MCP at all, given it costs more

AXI measured MCP at $0.100/task and 6.2 turns vs a principled CLI at $0.074/task and
4.5 turns. MCP loses on cost. It wins on **discovery**: the agent is handed the tool
descriptions, so it knows the tool exists without being told.

The cost scales with **tool count** — AXI's comparison used a ~30-tool browser server
with ~185K input tokens/task vs 79K for the CLI. A 3-tool server's schema overhead is
small. So this is a much cheaper MCP than the benchmark's, and worth it for discovery.

### 7.2 The long-running problem

Generation takes minutes. A synchronous tool call will hit client timeouts. Therefore:

- `tancat run --async` → returns a `job_id` immediately.
- `tancat run-status <job_id> --json` → returns the envelope, or `{"state": "running"}`.
- MCP's `run_tests` returns the handle; the agent polls or is notified.

A suite run can also take minutes, so the same handle pattern covers both verbs.
This is the design decision worth making early (Q3).

---

## 8. Guard Rails (must not regress)

These already exist and must apply to **every** entry point, including MCP:

- **Danger-zone allow-list** — `ci_generate.py`'s `localhost` / `*.staging.*` /
  `*-dev` / `*.test.*` rules and `--danger-zone` override.
- **Consent handling** — unchanged.
- **Credential redaction** — `src/credential_redaction.py` stays in the evidence path.
- **Free-tier metering** — never bypassed.
- **Workspace isolation** — `--workspace` behaves as it does for generation.

A new front end is the easiest place to accidentally bypass a guard. §11's tests must
prove the guard fires through the new verb.

---

## 9. What We Deliberately Will NOT Do

- **Merge generate and run.** If "check nothing broke" can silently trigger
  generation, the cheap path stops being cheap and the pitch collapses.
- **Auto-generate on regression.**
- **Auto self-heal.** Costs tokens; must be an explicit flag and an explicit user act.
- **Emit raw pytest logs by default.**
- **Make Streamlit agent-facing.** It stays the human interface.
- **Build a second data path.** One `run_results.sqlite` record; CLI renderer, chart,
  UI, and JSON envelope are all views over it.

---

## 10. Surfaces (in value order)

1. **`tancat run --json` + exit codes** — the whole feature. Everything else is in
   service of this.
2. **`tancat status` / async handle** — makes multi-minute work survivable.
3. **MCP wrapper** — discovery, once the above is trusted.
4. **Skill/agent instruction file** — tells an agent *when* to call tancat. Harness
   specific, so lowest portability, but cheapest to write.

---

## 11. Quality Gates & Process

- `ruff` → `mypy` → `pytest` → `scripts/verify_production.py`.
- **Eval harness: not required.** This is a surface change, not a pipeline/resolver
  change. Run it only if `src/failure_classifier.py` is touched.
- New tests:
  - `tests/test_cli_run.py` — the verb, both modes, both target shapes.
  - **Exit-code matrix test** — one case per code 0/1/2/3. Code 3 is the one that
    matters most; a timeout must not exit 0.
  - **Golden envelope fixture** — pins `schema_version: 1` so the contract cannot drift
    silently. An agent's parser breaks when this changes without a version bump.
  - Baseline-selection tests — same-suite scoping, `--baseline`, `--baseline none`.
  - Flaky-not-regression test.
  - Guard-rail tests — danger-zone refusal through the new verb, metering enforced.
- **Smoke gate** — add an offline envelope-shape check to `scripts/smoke.py` if cheap.

---

## 12. Dependencies & Session Estimates

| Phase | Scope | Sessions |
|---|---|---|
| **FC-07a** | `tancat run` verb, JSON envelope, exit codes, failure classification | 1–2 |
| **FC-07b** | Baseline scoping (per suite), flaky separation, `unknown` handling | 0.5–1 |
| **FC-07c** | MCP wrapper (`--stdio`, ≤3 tools, subprocess only) | 0.5–1 |
| **FC-07d** | Async job handle (`--async`, `tancat status`) | 0.5–1 |

Total **2.5–5 sessions**. FC-07a alone delivers most of the value; b/c/d are separable.

---

## 13. Decision Log (D1–D14)

| # | Decision | Rationale |
|---|---|---|
| D1 | Generate and run are **always** separate verbs | Keeps the re-run path LLM-free — the core of the pitch |
| D2 | Exit codes 0 clean/improved, 1 regression, 2 config, 3 error | Lets a shell agent answer with zero tokens |
| D3 | `verdict` enum: clean / improved / regression / error / unknown | One field answers the question |
| D4 | Delta over absolute; `regressed` + `new_failures` are primary | Absolute counts don't answer "did anything break" |
| D5 | Flaky is a sibling bucket, never reported as regression | False alarms destroy trust fastest |
| D6 | **Baselines are labelled records, not positions** — `--baseline <tag>`, with suite + environment as properties of the tag. Resolution cascade: tagged baseline → same-suite previous run → `unknown` | §5.1 shows 5 of 6 real situations are wrong under "previous run". `compare_latest_runs()` is also broken with >1 package in the DB |
| D7 | `usage.llm_tokens` is always reported | Honest cost reporting; it is also the sales argument |
| D8 | `schema_version` mandatory + golden-fixture tested | A silent contract change breaks every agent parser |
| D9 | Infrastructure failure must never exit 0 | A false "clean" is worse than a loud error |
| D10 | `tancat run` never triggers self-heal | Self-heal costs tokens; must be opt-in |
| D11 | **A `removed` bucket is added** to `delta` | §5.4 — today a deleted test (even a failing one) produces no signal, so a gutted suite reports `clean` |
| D12 | **Baseline provenance is mandatory and always rendered** — `label`, `recorded`, `recorded_commit`, `note`, `version`; plus a documented `--save-baseline` path | §5.2 — the user must know what they are comparing to. Mirrors `verify_production_baseline.json` |
| D13 | **`baseline_verdict` is reported**; a non-clean baseline must not read as reassurance | §5.5 — "no new regressions" against a red baseline is misleading |
| D14 | **`tancat run` takes a suite path only — never a story or URL** | Enforces D1 at the CLI surface: "check nothing broke" can never silently cost LLM tokens |

## 14. Open Questions (need a decision before FC-07a)

| # | Question | Recommendation |
|---|---|---|
| Q1 | Does an agent-triggered run consume free-tier metering? | Report it; count it in v1 (simpler and honest), revisit if it hurts adoption |
| Q2 | v1 baseline model — one named baseline per suite, or arbitrary tags? | Arbitrary tags plus one conventional `latest-accepted`. The *scope* question is now answered by §5.1 (scope is a property of the tag) |
| Q3 | Async handle in v1, or synchronous with a long timeout? | Synchronous for `run` (usually short); async required for `generate` |
| Q5 | When does a flaky test graduate to `regressed`? | Undefined in v1; an N-consecutive-failures rule in v2 |

*(The former Q4 — "does `tancat run` accept a story?" — is now D14, a decision rather than a
question: suite path only.)*

---

*Spec author's note: the code audit for §2 was done with `graphify` (query on
`compare_runs` / `run_result_persistence`) plus direct reads of
`src/pipeline_run_service.py` and `src/run_result_persistence.py`. The graph is a view,
not truth — every file and line reference above was confirmed against the source.*

*Audit finding on the precedent: the two baseline mechanisms in this repo are inconsistent.
`scripts/verify_production_baseline.json` records `version`, `recorded`, `recorded_commit`,
and `note`. `scripts/eval/baseline.json` records **none of those** — only `stories` — and the
eval `compare` output names no baseline identity. So "like the eval baseline" is the weaker
precedent; §5.2 follows the `verify_production` shape instead. Bringing the eval baseline up
to the same standard is a separate, small backlog item — out of scope here.*
