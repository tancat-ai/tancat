# Session — 2026-08-18: Linear-pipeline sampling config pin (AI-048)

> **Superseded for the full model-A/B picture** by
> `docs/sessions/2026-08-18_llm_model_ab_investigation.md` (the authoritative,
> fresh-context record of the whole 3.6-vs-3.8 investigation, mistakes incl.).
> This doc remains the detail record of the temperature-pin change itself.

> **Purpose of this doc: the data point.** This investigation cost a day+ of
> 3.6-vs-3.8 model A/B work that was confounded by an unrecorded sampling
> config. Everything learned is recorded here so it is never re-derived.

## TL;DR

The **linear pipeline** (default UI / CLI / eval / `verify_production`) called
`LLMClient.generate()` with `temperature=None`. Providers omit the temperature
field when it's `None`, so **the model server's own default sampling governed
generation** — on the llama.cpp launch under test, that was
`temperature=1.0` (max entropy), `top_p=0.95`, `top_k=20`. The LangGraph
agents pin `temperature=0` (proven deterministic — 100% byte-for-byte
identical skeletons since 2026-07-31, commit `69e5d9a`). So:

- Graph path = deterministic (temp 0 at every LLM call site).
- Linear path = server-default entropy — and the server default varies per
  launch and was never recorded.

**Consequence:** the AI-046 model A/B (Qwen3.8 vs Qwen3.6) compared each
launch's *default sampling*, not two models under identical conditions. We only
captured 3.8's defaults (temp 1.0). 3.6's were never snapshotted.

## What was actually delivered (code read, not guesswork)

`src/llm_providers/__init__.py` — all three OpenAI-compatible providers +
Ollama build the payload as:

```
{model, messages, stream: false, max_tokens: <generation_max_tokens()>}
# temperature only included when `temperature is not None`
```

`max_tokens=4096` **is** always delivered (a real override). Temperature is
delivered **only when set**.

### Who sets a temperature, who doesn't

| Call site | Temperature |
|---|---|
| `agents/planner.py` | `0` (explicit) |
| `agents/generator.py` | `0` (explicit) |
| `agents/ingestion.py` | `0` (explicit) |
| `agents/synthesizer.py` | → reuses SkeletonGraph (Planner+Generator) → `0` |
| `agents/validator.py` | no LLM calls (rule-based) |
| `agents/director.py` | no LLM calls ("reserved for future") |
| **Linear path** (`test_generator`, `orchestrator`, `prompt_builder`, `semantic_candidate_ranker`) | **None → server default** (1.0) |

Appeared in ONE commit (`69e5d9a`) as the "deterministic skeletons" fix,
never changed since. No per-agent/per-stage temperature configuration ever
existed (grep of all history for per-stage maps: nothing). The multi-provider
spec (AI-010) §13 Q4 ("per-provider temperature/top_p, or centralized?") stayed
an **open question**; the implementation went centralized. Model selection is
also session-level (`LLMClient._session_model` / `set_session_provider`) —
no per-stage model selection either.

## Server-config reading lesson (the `/props` trap)

- `/props` → `default_generation_settings.params.speculative.types: "none"`
  — this is the **per-request override default**, NOT the serving config.
- `/slots` → the truth: slot 0 reported `speculative: True`, `n_ctx: 262144`
  on the Qwen3.8 launch (2026-08-18).

`/props` is still useful for the *sampling defaults* (temperature/top_p/top_k/
seed) the server would apply — which is why the eval now snapshots it.
But never infer launch flags (speculative decoding, draft model, batch) from
`/props`; read `/slots` (or the launch command) for those.

## Speed-vs-quality split

- **Speed (3.6: ~33 t/s vs 3.8: ~25 t/s)** — config suspects: different GGUF
  families (3.6 = `-MTP` variant), quant mixes (Q4 vs Q6 rows), both launches
  reporting `speculative: True` at slot level. Not model-quality evidence.
- **Quality (3.6 resolution 75% vs 3.8 35% on saucedemo, eval linear path)**
  — confounded: both runs at each launch's server-default temperature; 3.8's
  default is 1.0, 3.6's unknown. Open until the controlled re-run.

## The fix (shipped this session)

1. **`src/llm_client.py`**
   - `llm_temperature_default()` — reads `AITEST_LLM_TEMPERATURE` (default
     `0.0`, clamped 0–2.0, invalid → warn + 0.0). Default matches the graph
     agents' proven determinism.
   - `_complete_sync()` substitutes the pin when `temperature is None` —
     every linear call now delivers a *deliberate* temperature. Graph agents
     pass `0` explicitly → unchanged. Explicit temperatures always win.
   - `generate_test()` gained a `temperature` pass-through (was the one entry
     point without it).
2. **`scripts/eval/eval_runner.py`**
   - `eval_runs` gains `temperature_sent REAL` + `server_defaults TEXT`
     (ALTER-migrated for existing DBs; legacy rows stay `NULL` = honestly
     unknown).
   - `_sampling_identity(use_graph)` records the resolved delivered
     temperature (graph → 0.0; linear → env-or-0.0) + a best-effort `/props`
     snapshot (temperature/top_p/top_k/seed/repeat_penalty/n_ctx).
3. **`.env.example`** — `AITEST_LLM_TEMPERATURE` documented.

## Gates (all green)

- Full suite: **2668 passed / 1 skipped** (PyMuPDF extra not installed — pre-existing)
- Smoke Gate 0: 39/39
- ruff check + format: clean
- mypy: clean on checked files (`src/llm_client.py`, tests). `eval_runner.py`
  has 5 **pre-existing** mypy notes but lives in the hook-excluded `scripts/`
  dir (mypy hook `exclude: ^(scripts/|fixtures/)`); unchanged by this work.
- 7 new tests (`tests/test_llm_client.py` x5, `tests/test_eval_runner_mocks.py` x2)

## Numbers context (temp 1.0 era — will shift)

| Run | Model | Result |
|---|---|---|
| full eval pre-fix | qwen3.8 | 31.2% |
| full eval pre-fix | qwen3.6 | 45.9% |
| full eval post-mock-fix | qwen3.8 | 55.0% |
| mock-only post-mock-fix | qwen3.6 | 81% |
| eval static (captured) | — | 97.9% |

All of these were at **server-default temperature** (1.0 on the 3.8 launch).
The pinned pipeline re-baselines below that; the eval-accuracy gate
(`--min-accuracy`) is the guard.

### ✓ 2026-08-18 controlled A/B — Leg 1 (Qwen3.8 @ temp 0.0 pinned)

Same code, `--mode full --regenerate`, persist ON. `eval_runs` now records
`temperature_sent=0.0` + the live `/props` snapshot per run.

| metric | @ temp 1.0 (old, server default) | @ temp 0.0 (pinned) |
|---|---|---|
| Resolution accuracy | 55.0% | **61.5%** |
| Correct resolutions | 60/109 | 67/109 |
| Test pass rate | — | 58.8% |

Per-site (pinned): saucedemo 35.0%, automationexercise 75.0%, demoqa 75.0%,
theinternet 71.4%, lv_insurance 41.7%, ecommerce_mock 68.75%, banking_mock 84.6% ×2.

**Read: same model, +6.5 pts purely from sampling config** — substantial
support for the config-confound hypothesis: part of AI-046's "3.8 regression"
was the server-default temperature, not the model. (sauceredemo's 35% URL-
assert failures are invariant across temp — a deterministic skeleton defect,
AGENTS.md §13 class.)

## Next steps

1. **Re-run the model A/B with the pin** — same `AITEST_LLM_TEMPERATURE` for
   both launches (or `.env` default). Now it measures models, not config.
   Record `/props`+`/slots` for BOTH launches (one line each) this time —
   `eval_runs` will capture the delivered side automatically.
2. Decide the product default: 0.0 (deterministic, provable self-consistency)
   vs a small non-zero value if the fixed-run spread shows some stories need
   exploration. Tune via `AITEST_LLM_TEMPERATURE`, then update
   `.env.example`/docs.
3. Long-term consistency item (not this session): `verify_production`/eval
   validate the **linear** path while the product ships the **graph** path —
   worth a BACKLOG item (validate-what-you-ship).

## Files touched

- `src/llm_client.py` (temp pin + `generate_test` temp param)
- `scripts/eval/eval_runner.py` (schema + `_sampling_identity`)
- `.env.example`
- `tests/test_llm_client.py`, `tests/test_eval_runner_mocks.py`
- `BACKLOG.md` (AI-048), `CHANGELOG.md`, this doc
</content>