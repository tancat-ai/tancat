# Session — 2026-08-18: Model A/B validity investigation (Qwen3.6 vs 3.8)

> **Purpose / how to read this:** this is a *fresh-context* record of a long,
> assumption-heavy investigation that ended without a valid conclusion. Every
> run is logged, every conclusion that was drawn-and-then-revoked is itemised
> with *why* it was wrong, and the open problems are stated so a clean session
> can pick this up without re-deriving anything. If you're continuing this
> work, read §"What's needed to do it properly" first, then the mistakes
> catalogue (§14) so you don't repeat them.

---

## 1. What we were aiming to do

Determine, with trustworthy data, whether **Qwen3.6-27B** or **Qwen3.8-27B**
(the two local llama.cpp models available on `:8080`) generates better
Playwright test skeletons — measured by the eval harness's **resolution
accuracy**. This started as BACKLOG **AI-046** ("Qwen3.8 skeleton/resolution
regression vs 3.6"), from a 2026-08-17 A/B that concluded "3.8 is worse; use
qwen3.6". The whole session was the discovery that **that conclusion — and
every subsequent one — was confounded**, and the hunt for the actual confound.

Sub-goals that emerged:
- Is the **sampling temperature** the confound? (→ linear path sent no temp)
- Is **RAG on/off** tracked and does it matter?
- Is the **model actually loaded** the one the config names? (misnaming check)
- Is the **eval infra** (resolution step) silently corrupting numbers?

---

## 2. Environment (fixed facts, verified 2026-08-18)

- Eval: `python scripts/eval/eval_harness.py run --mode full --regenerate` (persist ON → writes `evidence/run_results.sqlite` / `eval_runs`).
- LLM endpoint: `http://localhost:8080` (llama.cpp server). Current model file paths:
  - `C:\Users\l_a_c\.lmstudio\models\unsloth\Qwen3.6-27B-MTP-GGUF\Qwen3.6-27B-UD-Q4_K_XL.gguf` (17,909,097,600 bytes)
  - `C:\Users\l_a_c\.lmstudio\models\unsloth\Qwen3.8-27B-GGUF\Qwen3.8-27B-UD-Q4_K_XL.gguf` (17,923,394,624 bytes)
- **Proven server config is `launch_windows.ps1`**, which equals `llm-benchmarks/configs/qwen{36,38}-27b-eval.yaml`:
  ctx 156072, `--flash-attn on`, `--spec-type draft-mtp`, `--spec-draft-n-max 4`, `--spec-draft-p-min 0.0`, `--ctx-checkpoints 0`, batch 1024/1024, `--jinja`, `--reasoning-preserve`, cache k/v f16.
- Server build (this session's 3.8 launch): `build_info b10483-27e345b57`.
- Test deadlock rule: never run the eval harness and the pytest suite at the same time — the mock server / Milvus ports interact.

---

## 3. Timeline of the runs (ALL of these are what we did)

| # | Name / log | Model | Server config | Temp | RAG | Outcome |
|---|---|---|---|---|---|---|
| A | `/tmp/eval_full_regenerate_fixed.log` | 3.8 | unknown (earlier) | 1.0 (server default) | off | **55.0%** (post mock-fix) |
| B | `/tmp/eval_pinned_38.log` | **3.8** | **user manual = 262k ctx** | **0.0 (pinned)** | off | **61.5%**, 0 gen retries |
| C | `/tmp/eval_pinned_36.log` | **3.6** | **controlled 156k** | 0.0 | off | **44.0%**, 7 gen retries, 27 resolve timeouts |
| D | `/tmp/eval_38_ragon.log` | 3.8 | controlled 156k | 0.0 | **on** | ABORTED — 12 retries, 0/8, stuck |
| E | `/tmp/eval_38_156k_ragon.log` | **3.8** | **controlled 156k** | 0.0 | off | **26.6%**, 10 gen retries, 7 resolve timeouts |

Mistake #0 (the seed of all of it): **runs B, C, D, E were not on the same
server config.** B used the user's manual 262k server (I had not captured its
flags before killing it); C/D/E used the "controlled" 156k eval config. So any
B-vs-C/D/E comparison conflates **model** with **server config**.

---

## 4. What "resolution accuracy" measures (and what it hides)

`resolution_accuracy = correct_resolutions / total_placeholders`, from
`eval_runs.resolution_accuracy`. Each placeholder (action + human description
e.g. "username") is resolved to a `generated_locator`; it counts if it matches
the golden key (with tolerance selectors). `test_pass_rate` / `false_positive_rate`
come from actually executing the generated tests.

**The hidden failure mode (the big one):** when the resolution LLM call does
not produce a candidate, `generated_locator = None` and the placeholder scores
0 — silently. A site where *all* placeholders get `None` scores a flat **0%**
with no distinguishing log. This is what produced the "multiple zeros" we kept
misreading.

---

## 5. Discovery 1 — the sampling temperature was unrecorded (fixed)

- The **linear** pipeline (UI / CLI / eval / verify_production) called
  `LLMClient.generate()` with `temperature=None`, so providers omitted the
  field → the **server's own default** (1.0 on llama.cpp) silently governed
  sampling. The **LangGraph** agents pin `temperature=0` (commit `69e5d9a`,
  2026-07-30: skeleton self-consistency 55.6%→100%).
- So graph = deterministic, linear = server-default entropy; model A/Bs through
  the linear path compared two *launch configs*, not two models.
- **Fix shipped:** `AITEST_LLM_TEMPERATURE` (default `0.0`) in
  `src/llm_client.py::llm_temperature_default()`; `_complete_sync` substitutes
  it for `None`; `eval_runs` now records `temperature_sent` +
  `server_defaults`. All verified calls now log `temp=0.0`.

## 6. Discovery 2 — `/props` ≠ serving config (the `/slots` trap)

- `/props` → `default_generation_settings.params.speculative.types: "none"`
  looks like "no speculative decoding". **Wrong** — that's the *per-request
  override default*. The serving reality is in `/slots`.
- `/slots` → slot 0: `speculative: True`, `n_ctx: <actual>`.
- Lesson: never infer launch flags from `/props`; read `/slots` (or the launch
  command).

## 7. Discovery 3 — the model configs are NOT misnamed

- The two configs point at distinct, real GGUF files (differ by ~14 MB).
- `/v1/models` reports exactly the config-named model file. Confirmed.

## 8. Discovery 4 — RAG on/off was mis-tracked (fixed)

- Different defaults for the same env var: resolver gate
  (`os.getenv("RAG_ENABLED","")=="1"`, default off) vs runner persist gate
  (`os.getenv("RAG_ENABLED","1")=="1"`, default on). So `eval_runs.rag_enabled`
  recorded "1" while resolution actually ran RAG-off.
- **Fix:** runner now uses the resolver gate (inline opt-in, default off).
- The orchestrator's **generation** RAG is *always-on* by default
  (`RAG_ENABLED=0` opts out) and loads the ~80 MB embedder + Milvus on every
  run — a real, unnoticed system load that can push the 45s resolution timeout
  over the edge.

## 9. Discovery 5 — the 156k "proven" config makes generation retry-loop

- Run C (3.6@156k, RAG off) and E (3.8@156k, RAG off) both produced repeated
  `[WARNING] Zero placeholders found / Journey count mismatch: expected=N, got=0 → Retrying with stricter prompt`.
- Run B (3.8@262k) had **zero** such retries. So the 156k flag set (ctx size?
  draft-mtp? pmin?) degrades skeleton generation into `got=0` failure→retry
  loops for **3.8 specifically** (3.6 tolerates it → completes). Still not
  isolated to a single flag.

## 10. Discovery 6 — the real cause of the "multiple zeros": resolution timeouts

The user's correct push-back: *config tweaks give slight variation, not flat
zeros — so it's a timeout/connection, go find the actual failure.* True:

- Every failing placeholder on the 0% sites had `generated_locator: None`.
- The resolution LLM call has a hard **`timeout=45`** in
  `src/semantic_candidate_ranker.py:93` and `:161`.
- Run E (3.8@156k) had **7** resolution timeouts; run C (3.6@156k) had **27**.
- So C and E are both polluted by resolution-timeout noise to *different
  degrees* — neither is a valid model comparison, and the 0% sites are
  outright failures, not tuning or model skill.

---

## 11. When the misleading "conclusions" happened (and were revoked)

1. **"3.8 is worse; use 3.6" (AI-046, 2026-08-17)** — base run had the AI-047
   mock-serving bug + different server-default temps. **Revoked.**
2. **"temp pin helps; 3.8 = 61.5% @ temp 0" (run B)** — real pin effect, but B
   is the only 262k run; can't compare to C/E.
3. **"3.8 beats 3.6 (61.5 vs 44)"** — **Revoked**: B vs C differ in server
   config (262k vs 156k).
4. **"RAG-on breaks generation / D thrashed because of RAG"** — **Revoked**:
   D's thrash was the 156k-config generation loop (C/E show it with RAG off);
   the `Error occurred in event listener` tracebacks were Playwright request
   handlers, and faiss "failed" only on the AVX512/AVX2 slots then loaded fine.
   The "38 vs 2 RAG log lines" was literally the word "Garage".
5. **"At 156k, 3.6 (44%) beats 3.8 (26.6%)"** — **Invalid**: both runs are
   resolution-timeout-polluted (C had 27, E had 7), so the delta is timeout
   amount, not model.

**Net: there is no valid model A/B conclusion yet.** The only solid, useful
facts are the infra bugs found ($§5–10).

---

## 12. What's now actually fixed vs still open

**Fixed this session (code, tests green):**
- Linear pipeline temp pin (`AITEST_LLM_TEMPERATURE`, default 0.0) — delivered temp now explicit.
- `eval_runs` records `temperature_sent` + `server_defaults` — now a **self-describing manifest** (`model_path`, `build_info`, `slot_n_ctx`, `speculative`, sampling defaults) mirroring llm-benchmarks' `bench_manifest.py`.
- RAG default-mismatch fixed (runner records resolver reality).
- 7 new tests (`test_llm_client.py`, `test_eval_runner_mocks.py`).

**Still open (the actual TO-DO for a fresh session):**
- The **resolution `timeout=45`** in `semantic_candidate_ranker.py` makes eval numbers silently unreliable on a loaded server. Needs to be configurable/higher (env default ~120s) and should **log** when it times out so `None`-→0% isn't silent.
- **Isolate the config flag** that causes the `got=0` generation retry-loop on 156k (ctx 156k vs 262k, or draft-mtp/pmin). This is the real "what collapses generation" question (separate from resolution timeouts).
- **A genuine model A/B**: pick ONE server config (probably fix the collapse first), capture manifest before every leg, server not concurrently loaded, then run 3.6 and 3.8. Only then can AI-046 be re-answered.
- BACKLOG items owed: AI-046 revoke/reframe; resolution-timeout reliability; eval-should-log-server-config (done); `llm-benchmarks/llmctl.py` flash-attn YAML bug (see §13).

---

## 13. Side bug found while switching models — llmctl flash-attn

`llm-benchmarks/llmctl.py` loads config YAML with PyYAML, which parses
`flash-attn: on` as boolean `True` → `to_argv()` emits bare `--flash-attn`.
This llama.cpp build requires `--flash-attn on|off|auto`, so **every server
launched via `llmctl start` died instantly on the argument error** (I hit it
repeatedly; worked around by spawning llama-server directly with the corrected
flag). Deserves a fix + a note.

---

## 14. Mistakes & assumptions catalogue (the meta-lesson — read this)

1. **Assumed server config was constant across runs.** It wasn't (262k manual
   vs 156k eval config, draft-mtp on/off). "Ran the same command" ≠ "same
   server". Must capture `/props`+`/slots` before every leg.
2. **Drew model conclusions from confounded runs.** Erred toward "model is
   better/worse" instead of first checking infra (config drift, then timeouts).
3. **Killed the 262k server without capturing its flags** — lost the one clean
   config and couldn't reproduce it. (Now impossible to redo, since the process
   is gone.)
4. **Trusted `/props` for serving config** (`speculative.types`) instead of
   `/slots`.
5. **Attributed D's thrash to RAG** before checking whether the config alone
   (C/E) reproduced it. Multi-variable runs need isolation before blame.
6. **Took a substring count at face value** ("38 RAG lines") — it was
   "Garage". Grep counts need context.
7. **Read flat zeros as "config/model"** instead of "failure". The
   user's rule — zeros = failure (timeout/connection), not tuning — was the
   key insight that found the real cause.
8. **Didn't verify the resolution phase health** — the `None`→0% is silent;
   we only found it by reading the persisted `raw_report` for `generated_locator`.
9. **Ran the eval against a loaded server** (generation + resolution + the
   always-on RAG embedder/Milvus) which amplifies the 45s resolution timeout.

### The one-line takeaway

> **Everything that looked like a model or config difference was, in the end,
> an infra artifact (temp unset, server-config drift, resolution timeout). Get
> the infra verifiable (manifest + non-silent timeouts + single-config), then
> measure models — not before.**

---

## 15. Commands & references for the next session

```bash
# Verify what's loaded / serving (before EVERY leg):
python -c "import httpx; print(httpx.get('http://localhost:8080/v1/models',timeout=5).json()['data'][0]['id'])"
python -c "import httpx; print(httpx.get('http://localhost:8080/slots',timeout=5).json()[0])"

# Run an eval leg (RAG resolver off by default):
python scripts/eval/eval_harness.py run --mode full --regenerate

# Inspect silent resolution failures:
#   eval_runs.raw_report -> per-placeholder `generated_locator` (None = resolution miss/timeout)

# Key code:
#   src/llm_client.py            temp pin (AITEST_LLM_TEMPERATURE)
#   scripts/eval/eval_runner.py  _sampling_identity (manifest), persist
#   src/semantic_candidate_ranker.py:93,161   resolution LLM timeout=45  <-- FIX TARGET
#   src/orchestrator.py          _build_rag_retriever (always-on generation RAG)
#   src/agents/*.py              graph agents temp=0
#   llm-benchmarks/llmctl.py     flash-attn bool-coercion bug
#   llm-benchmarks/configs/*.yaml  proven 156k config (== launch_windows.ps1)

# Logs (session artifacts):
#   /tmp/eval_pinned_38.log       B  3.8@262k  61.5%
#   /tmp/eval_pinned_36.log       C  3.6@156k  44.0%  (27 resolve timeouts)
#   /tmp/eval_38_ragon.log        D  3.8@156k RAG-on  aborted
#   /tmp/eval_38_156k_ragon.log   E  3.8@156k  26.6%  (7 resolve timeouts)
```
</content>