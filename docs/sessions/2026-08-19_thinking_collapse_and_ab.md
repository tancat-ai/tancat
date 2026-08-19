# Session — 2026-08-19: Thinking-budget collapse found; A/B re-run (spec OFF)

> **Continues** `docs/sessions/2026-08-18_llm_model_ab_investigation.md`.
> Read that doc's §14 (mistakes catalogue) first if you're cold. This doc
> records: the two fixes shipped on top of it, the *real* root cause of the
> `got=0` collapse, and the definitive A/B design now executing.

---

## 1. Starting state (carried over, uncommitted)

Previous session's fixes were uncommitted in the working tree: temp pin
(`AITEST_LLM_TEMPERATURE`, default 0.0), eval manifest (`temperature_sent` +
`server_defaults`), RAG-gate mismatch fix. Decision this session: **evidence
before commits** — nothing gets committed until a clean run shows the failure
modes gone. (Checkpoint-branch idea floated; user opted to carry uncommitted —
isolation work touches no `src/` so no entanglement risk.)

## 2. Evidence steps (in order)

1. **Temp pin delivery proven** — `scratch/determinism_check.py` run 1:
   both calls logged `temp=0.0`. But gen2 returned **0 chars** (235s, no
   error) → the collapse reproduced at the level of ONE bare LLM call: no
   orchestrator, no eval harness, no retry logic.
2. **Raw-response probe** (`scratch/raw_probe.py`): the response had
   `reasoning_content` ~16.9k chars and `content=''`, `finish_reason=length`,
   `completion_tokens=4096`. **The thinking phase ate the whole max_tokens
   budget.** Provider only reads `message.content` → all thinking discarded.
3. **Fix candidates** (`scratch/thinking_fix_probe.py`, 3.8):
   - `chat_template_kwargs={"enable_thinking": False}` → **18.2s/18.1s,
     reasoning=0, content every time** ← winner, per-request, llama.cpp honors it
   - `/no_think` in-band → model ignores it (still 160–185s of thinking)
   - max_tokens 16384 → works, 313s (17× slower)
4. **3.6 fairness probe** (`scratch/probe_36.py`, byte-identical prompt):
   3.6 is ALSO a thinking model — default calls collapsed **2/2**
   (162s/156s, `content=0`); thinking-off = 16.3s/16.3s byte-stable.
   → Run C's "3.6 tolerates the 156k config" was retry luck. The collapse
   was NEVER a server-config flag. Both models equalized by thinking-off.
5. **Determinism** (`scratch/determinism_check.py` post-fix): thinking off +
   temp 0 + spec ON → still not byte-identical (naming jitter:
   `test_02_fill_username` vs `..._field`) → **draft-MTP spec decode is the
   residual non-determinism source**. Server relaunched without spec flags →
   **byte-identical**, 32.4s/gen (vs 14.8s with spec). User decision:
   **A/B runs spec OFF**.

## 3. Design rule from the user (important)

> "Shouldn't it be a user decision? If we override the user's config and it
> performs well but they don't know we have overridden it then couldn't it
> lead to misinformation?"

Consequences (implemented):
- **No silent overrides anywhere.** `enable_thinking=None` sends NOTHING in
  the payload; the model/server default governs unless a caller opts out
  explicitly (the two proven-broken structured call sites: skeleton
  generation, resolution ranking).
- **Everything delivered is logged + recorded**: per-call debug line
  `temp=… thinking=off|on|default`; `eval_runs.thinking` column
  (linear=`off`, graph=`model-default`) joins `temperature_sent`.
- **Per-stage choices later**: LangGraph stages keep the model default until
  measured; per-stage opt-in/out is explicit future work.
- Same spirit as the timeout fix: no env var, no CLI flag — sane default
  everywhere, constant-in-code so A/B legs can't drift on it.

## 4. Fixes shipped this session (uncommitted, all gates green)

**AI-049 — resolution timeout (2026-08-18 doc §10 fix target):**
`DEFAULT_RESOLUTION_TIMEOUT=120.0` + keyword-only `timeout` on
`SemanticCandidateRanker`; `_is_timeout_error()` walks the cause chain
(`LLMClient.generate` wraps provider errors in `RuntimeError`); both call
sites log WARNINGs naming timeout, elapsed-vs-limit, action/description(s).
Plumbed keyword-only through `ElementMatcher` → `PlaceholderOrchestrator` →
`TestOrchestrator`; `eval_runner.py` passes it explicitly at both
orchestrator constructions. 8 tests.

**AI-050 — thinking switch:** `LLMProvider.complete(..., enable_thinking)`
(OpenAI-compatible providers emit `chat_template_kwargs`; Ollama
accepts-and-ignores); `LLMClient` threads + logs it; skeleton single-call and
ranker opt out explicitly; `eval_runs.thinking` column. 14 tests.
**Protected files touched (flagged for review):** `src/llm_providers/__init__.py`,
`src/llm_client.py`, `src/test_generator.py`.

Gates after both: ruff+format ✅, mypy src/ cli/ ✅ (143 files), smoke 39/39,
full suite **2691 passed / 1 skipped**, eval static 97.9% exit 0.

## 5. The definitive A/B (in progress)

**Config (both legs identical, spec OFF):**
```
llama-server --model <gguf> --port 8080 --host 0.0.0.0 --ctx-size 156072
  --n-gpu-layers 999 --flash-attn on --jinja --cache-type-k f16
  --cache-type-v f16 --batch-size 1024 --ubatch-size 1024 --parallel 1
  --cont-batching --reasoning-preserve --cache-ram 0 --ctx-checkpoints 0
```
(no `--spec-*` flags). Models:
- 3.6: `C:\Users\l_a_c\.lmstudio\models\unsloth\Qwen3.6-27B-MTP-GGUF\Qwen3.6-27B-UD-Q4_K_XL.gguf`
- 3.8: `C:\Users\l_a_c\.lmstudio\models\unsloth\Qwen3.8-27B-GGUF\Qwen3.8-27B-UD-Q4_K_XL.gguf`

**Per-leg protocol:** capture manifest BEFORE the run
(`scratch/manifest_<model>.json` ← /v1/models + /slots + /props), verify
model path + n_ctx + `speculative=False`, then
`python scripts/eval/eval_harness.py run --mode full --regenerate`
(persist ON → eval_runs records model, temperature_sent=0.0, thinking=off,
server_defaults). Never run pytest concurrently (deadlock rule).

- Leg F (3.6, spec off): log `scratch/eval_F_36_specoff.log` — **DONE**
- Leg G (3.8, spec off): log `scratch/eval_G_38_specoff.log` — **DONE**

**Validity conditions finally all true:** same flags both legs; temp pinned +
recorded; thinking off + recorded; timeouts non-silent at 120s; generation
byte-deterministic; model verified via /v1/models per leg. Both runs: **8/8
skeletons, 0 `got=0`, 0 timeouts, 0 retry loops.** `eval_runs` rows confirm
both legs `pipeline=linear, temp=0.0, thinking=off, rag=0, regenerated`.

## 5b. A/B results (thinking OFF, spec OFF) — DONE but NOT a model verdict

| Metric | **3.6 (leg F)** | **3.8 (leg G)** |
|---|---|---|
| **Resolution accuracy** | **76.1%** (83/109) | **62.4%** (68/109) |
| Test pass rate | 55.6% (25/45) | 57.8% (26/45) |
| False positive rate | 24.4% | 26.7% |
| Skeleton completeness | 100% | 100% |
| Mean gen duration | 223.8s | 249.8s |

Per-story resolution: 3.6 leads or ties 6/8. Biggest deltas: saucedemo 75% vs
40% (20 ph), ecommerce_mock 94% vs 69%, lv_insurance 62% vs 42%. (lv_insurance
tests passed 0 in *both* legs — a site/evidence issue, not a model difference.)

## 6. ⚠️ THE CONTRADICTION — why this is NOT a model verdict (READ FIRST)

The user (correctly) found "3.8 is worse" implausible. Qwen's own model card
(https://huggingface.co/Qwen/Qwen3.8-27B, Aug 2026) shows **3.8 beating 3.6 by
8–20pts with thinking ON**, on skills that map directly to our harness:

| Qwen official (thinking ON) | 3.8 | 3.6 |
|---|---|---|
| **WebArena-Verified (browser use)** | **64.8** | 48.8 |
| OSWorld-Verified (computer use) | 84.3 | 63.9 |
| Terminal Bench 2.1 (agentic terminal) | 73.0 | 63.4 |
| **SWE-bench Pro** | 61.7 | 53.5 |
| **LiveCodeBench v6 (coding)** | 90.3 | 83.9 |

**So our 76.1-vs-62.4 runs OPPOSITE to Qwen's data.** Root cause of the
confound (now understood, not yet re-tested):
- **Both our legs ran `enable_thinking=False`.** The model card says Qwen3.8
  "operates in thinking mode **by default**" and that thinking is where it gains
  on 3.6. We compared the two models with 3.8's headline capability **off**.
- **We gave no reasoning budget.** The card says for agentic work: "Reasoning
  Content: set max output to 262,144 tokens." We capped at 4096.
- **temp 0.0** is below Qwen's recommended 0.7 for non-thinking mode.

**Net: the A/B answers "which model is better at direct non-reasoning
generation", NOT AI-046's question ("which model makes better Playwright
tests").** Do NOT commit a "3.6 wins" conclusion. The model question stays OPEN
until the two validation steps in §7.

## 7. HANDOVER — what the next session must do (in order)

**Goal: validly re-answer AI-046.** Two validation steps, then reconcile.

1. **External benchmark (ground truth, independent of our harness).** Run
   EleutherAI `lm-evaluation-harness` against BOTH GGUFs, **thinking ON with a
   large reasoning budget**, on a cheap subset: GPQA Diamond (198 q),
   LiveCodeBench v6, HumanEval, a MMLU subset. Compare to Qwen's card numbers.
   - First check: is `lm-eval` in the venv / installable via `uv add lm-eval`
     (or run in a separate venv — it's heavy)? How much VRAM do the 27B Q4
     models leave on this box (same GPU as llama-server)? Decide: point lm-eval
     at the live llama-server (OpenAI backend) vs load the GGUF directly.
   - Expectation: if 3.8 beats 3.6 externally (as Qwen reports), our harness
     has a bias to find; the thinking-ON re-run (§2) becomes the *explanation*.

2. **Thinking-ON project A/B.** Re-run `eval_harness.py run --mode full
   --regenerate` per model with `enable_thinking=True` **and** a large
   `max_tokens` (see `LLM_MAX_TOKENS` in `src/llm_providers/__init__.py:
   generation_max_tokens()`, default 4096 — raise, e.g. 16384+, so reasoning
   isn't truncated). Verify no empty-content returns in the logs. Same single
   config, manifest captured per leg. (The `enable_thinking` switch is already
   shipped — thread it through however you prefer; it's logged + recorded.)

3. **Reconcile + inspect the harness.** If (1) and (2) still disagree with (1),
   dig into WHY 3.8 mis-resolved saucedemo (12 placeholders wrong): wrong
   locator, valid-alternate the golden key rejects, or a tolerance bug. The
   per-placeholder `generated_locator` is in `eval_runs.raw_report`.

4. **Then** re-answer AI-046 in BACKLOG with the validated numbers, and only
   then is a model recommendation (if any) legitimate.

**Commands & refs:**
```bash
# Server (spec OFF config above). llmctl has a flash-attn bool bug — spawn directly.
# Verify per leg (never trust /props alone):
python -c "import httpx;print(httpx.get('http://localhost:8080/v1/models',timeout=5).json()['data'][0]['id'])"
python -c "import httpx;print(httpx.get('http://localhost:8080/slots',timeout=5).json()[0])"
# Project A/B leg:
python scripts/eval/eval_harness.py run --mode full --regenerate
# Inspect silent resolution failures:
#   eval_runs.raw_report -> per-placeholder generated_locator (None = miss/timeout)
# Key code:
#   src/llm_providers/__init__.py  enable_thinking -> chat_template_kwargs; generation_max_tokens()
#   src/llm_client.py              temp pin + thinking passthrough/logging
#   src/semantic_candidate_ranker.py  timeout=120 default + thinking=off + loud logs
#   src/test_generator.py          _generate_skeleton_single_call -> enable_thinking=False
#   scripts/eval/eval_runner.py    _sampling_identity (temp+thinking), eval_runs manifest
```

## 8. Server-state + scratch artifacts

Current server at end of session: **3.8, spec OFF** (leg G config). If the box
was rebooted, relaunch with the exact flags in §5 (spawn llama-server directly —
llmctl flash-attn bug still open). Verify `/v1/models` + `/slots` before
trusting anything.

```
scratch/determinism_check.py        # same story twice via linear path, diff
scratch/determinism_run1.log        # BEFORE: 160s ok + 235s EMPTY (the collapse)
scratch/determinism_run2.log        # AFTER thinking-off, spec ON: ~15s, naming jitter
scratch/determinism_run3.log        # AFTER thinking-off, spec OFF: byte-IDENTICAL
scratch/raw_probe.py                # dumps full /v1/chat/completions response
scratch/thinking_fix_probe.py       # 3 fix candidates on 3.8 (enable_thinking wins)
scratch/probe_36.py                 # 3.6 fairness probe (also collapses by default)
scratch/capture_manifest.py         # pre-leg manifest: /v1/models + /slots + /props
scratch/manifest_36_specoff.json    # leg F manifest
scratch/manifest_38_specoff.json    # leg G manifest
scratch/eval_F_36_specoff.log       # leg F full log (76.1%)
scratch/eval_G_38_specoff.log       # leg G full log (62.4%)
scratch/llama_36_server.log / llama_36_nospec.log / llama_38_nospec.log
```

**The one-line takeaway for the next session:** the infra is now honest
(temp pinned, timeouts loud, thinking explicit + recorded, single config,
byte-deterministic) — so the 76.1-vs-62.4 number is *real for the condition it
measured* (thinking off), but that condition is NOT the question. Validate
externally and re-run thinking-on before declaring any model winner.
