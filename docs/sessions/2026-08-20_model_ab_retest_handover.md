# HANDOVER — Qwen3.6-vs-3.8 A/B re-test with new quantization + corrected config (2026-08-20)

> **Purpose:** the newly-downloaded Qwen3.8 quant (arriving from a reputable
> source) is a MATCHED-PRECISION file. This document gives a fresh-context
> session everything it needs to re-run the model A/B CORRECTLY, with the
> config changes the community + our investigation flagged, and to finally
> land a defensible answer to **AI-046**.
>
> **Continue from (read first):**
> - `docs/sessions/2026-08-18_llm_model_ab_investigation.md` (mistakes catalogue §14)
> - `docs/sessions/2026-08-19_thinking_collapse_and_ab.md` (the thinking fix + handover)
> - `docs/sessions/2026-08-19_external_benchmark_and_thinking_on_ab.md` (this A/B + correction)
> - Evidence: `/c/Users/l_a_c/code/llm-benchmarks/evidence/model-ab-2026-08-20/`

---

## 0. The one-line truth

The previous "3.6 ≥ 3.8" result is **REAL for the files tested but NOT a model
verdict**: the 3.8 GGUF we ran is a ~3.3 bpw under-quantization (38% of tensors
at Q2_K) while the 3.6 is ~6.7 bpw — so we compared a 3.3-bpw model to a
6.7-bpw one. **Do not conclude 3.6 wins.** The new matched-precision 3.8 quant
fixes the confound; re-run and *then* decide. External GSM8K ties (0.82 vs 0.81).

**Added 2026-08-20 afternoon — MTP ON does NOT change the accuracy gap.** Ran leg J
(3.8, thinking ON, MTP ON, draft n-max 3): all 8 stories completed (0 failures;
eval-005 that timed out under MTP OFF now completes), 2.0x decode speedup
(11.5->22.5 t/s), but resolution excl-eval-005 is 63.5% vs 62.4% (MTP off) —
within noise. So MTP is a speed/feasibility win, NOT a quality fix; the ~13pt 3.8
deficit persists and still needs a matched-precision file to judge. A 3.6 MTP-ON
leg was not run (MTP output == MTP-off output, so 3.6 stays ~73%). See
`llm-benchmarks/evidence/model-ab-2026-08-20/leg_J_mtpon_results.md`.

---

## 1. Previous findings — validated numbers (files as-tested)

Servers: build **b10483-27e345b57**, ctx 156160, spec OFF (no MTP),
`temp=0.0` pinned, thinking recorded per leg. 8 stories, harness
`--mode full --regenerate`. Leg manifests: `manifest_thinkingon_{36,38}.json`.

| Condition | 3.6 | 3.8 (under-quantized) | leg |
|---|---|---|---|
| thinking OFF | 76.1% (83/109) | 62.4% (68/109) | F / G |
| thinking ON (raw) | 73.4% | 48.6% | H / I |
| thinking ON (excl. eval-005 timeout) | 75.3% | 62.4% | H / I |
| External lm-eval GSM8K (thinking ON, n=100) | 0.82 | 0.81 (tie) | |

Key caveats baked in:
- **3.8 thinking-ON empty-content failure** on eval-005 (lv_insurance): skeleton
  returned `length=0` after 1447.89s (all 16384 max_tokens in reasoning, content
  empty → got=0). 3.6 had ZERO such events. Corroborated by a Reddit user's 3.8
  run that "spent 23 min thinking before writing code."
- This session found the whole comparison is **model-file confounded** at the
  GGUF level (`gguf_quantization_confound.md`).

---

## 2. ⚠️ The two confounds the re-test MUST eliminate

1. **Model-file precision mismatch (now fixed by the new quant).** Verify the new
   file's bpw FIRST with the script below — it must be **≈6.5–6.7 bpw** to be
   apples-to-apples with the 3.6 file (6.71 bpw). Anything ≤4 bpw is still
   under-quantized and useless for a fair A/B.
2. **Spec/MTP OFF was the regime most unflattering to 3.8.** All community
   benchmarks run Qwen3.8 *with* MTP. Our spec-OFF config stripped 3.8's main
   accelerator. For fairness, run the re-test with **MTP ON for BOTH models**
   (our build b10483 supports `--spec-draft-n-max`/`--spec-draft-p-min`).

---

## 3. Verify the new quant (do this first — gate the whole re-test)

```bash
cd /c/Users/l_a_c/code && /c/Users/l_a_c/code/lm-eval-bench/.venv/Scripts/python -c "
import gguf
bpp={0:32.0,1:16.0,3:8.5,8:4.5,12:8.5,13:2.5625,14:3.4375,15:4.5,17:6.5625,23:4.5,26:4.25}
r=gguf.GGUFReader(r'<NEW_3.8_GGUF_ABS_PATH>')
tot=0; el=0
from collections import Counter
c=Counter()
for t in r.tensors:
    tot+=bpp.get(int(t.tensor_type),32)*t.n_elements; el+=t.n_elements
    c[int(t.tensor_type)]+=1
print(f'overall bpw = {tot/el:.3f}  (target ~6.5-6.7 to match 3.6)')
print('Q2_K tensors:', c.get(13,0), '/', len(r.tensors))
"
```
Compare with the 3.6 reference: `gguf_quantization_confound.md` (3.6 = 6.71 bpw,
attn_qkv 6.29). **Abort if the new file is <5 bpw.**

(Generate the 3.6 side profile with the same script on
`C:\Users\l_a_c\.lmstudio\models\unsloth\Qwen3.6-27B-MTP-GGUF\Qwen3.6-27B-UD-Q4_K_XL.gguf`.)

---

## 4. Exact re-run plan (corrected config)

**Server launch — the key change vs before is MTP ON (for BOTH legs), plus the
community-consensus draft settings.** Verified our build (b10483) supports all flags.

```bash
# Launch llama-server DIRECTLY (llmctl still has the flash-attn bool bug).
# Use the proven binary:
BIN="/c/Users/l_a_c/llama.ccp config/vulkan/llama-server.exe"
# 3.6 leg: MODEL=.../Qwen3.6-27B-MTP-GGUF/Qwen3.6-27B-UD-Q4_K_XL.gguf
# 3.8 leg: MODEL=<NEW matched-precision 3.8 gguf>
"$BIN" --model "$MODEL" --port 8080 --host 0.0.0.0 --ctx-size 156072 \
  --n-gpu-layers 999 --flash-attn on --jinja --cache-type-k f16 --cache-type-v f16 \
  --batch-size 1024 --ubatch-size 1024 --parallel 1 --cont-batching \
  --reasoning-preserve --cache-ram 0 --ctx-checkpoints 0 \
  --spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.0
```

**Important:** the ONLY intended difference between the two legs is the model
file. Verify both via `/v1/models` + `/slots` (never `/props` alone) and capture
the manifest BEFORE each leg with `scratch/capture_manifest.py`. Check `/slots`
shows `speculative=True` this time.

**Eval leg (same for both models):**
```bash
# thinking ON, big budget, fair timeouts (all env-driven, no silent drift)
AITEST_ENABLE_THINKING=1 LLM_MAX_TOKENS=16384 \
AITEST_RESOLUTION_TIMEOUT=300 AITEST_GENERATION_TIMEOUT=1800 \
python scripts/eval/eval_harness.py run --mode full --regenerate
```
(These env knobs were added 2026-08-20 — see §6. Never run pytest concurrently with the harness.)

**Manifest + logging:** before each leg run `python scratch/capture_manifest.py scratch/manifest_rX_<model>.json`. Logs → `scratch/eval_<leg>_<model>.log`.

**Benchmark plan (per model, thinking ON):**
1. **Project A/B** (above) — the primary number: resolution accuracy on 8 stories.
2. **External GSM8K** via lm-eval (venv `C:\Users\l_a_c\code\lm-eval-bench`,
   py3.13, lm-eval 0.4.12) pointed at the live server:
   ```
   cd /c/Users/l_a_c/code/lm-eval-bench
   PYTHONIOENCODING=utf-8 OPENAI_API_KEY=LOCAL ./.venv/Scripts/python -m lm_eval run \
     --model local-chat-completions \
     --model_args base_url=http://localhost:8080/v1/chat/completions \
     --tasks gsm8k --limit 100 --apply_chat_template --gen_kwargs max_tokens=2048 \
     --output_path <scratchlmeval_out>
   ```
   (External arithmetic-reasoning check. GPQA is gated / HumanEval is
   Windows-blocked — documented; don't waste time retrying them.)

---

## 5. Step-3 reconcile (only after both legs + external)

If 3.8 (matched precision, MTP ON) still underperforms, THEN dig into *why*:
- Wrong locator vs valid-alternate the golden key rejects vs tolerance bug.
- Per-placeholder `generated_locator` lives in `eval_runs.raw_report`
  (DB `evidence/run_results.sqlite`, table `eval_runs`).
- Reuse the saucedemo comparison logic from the prior session (3.8 was
  anchoring on `#item_3_title_link` for many actions — that was real, but was
  with the *under-quantized* model; re-check with the good one).

Only after reconcile/reproduction: update AI-046 in BACKLOG.md with the verdict.

---

## 6. Tooling/knobs added this session (2026-08-20) — already committed-registered

Env-drivable switches (all defaults = prior behavior, so no silent drift):
- `AITEST_ENABLE_THINKING=1` → structured skeleton+resolution call thinking-ON
  (`src/llm_client.py::enable_thinking_default`, threaded through orchestrator,
  placeholder_orchestrator, element_matcher; recorded in `eval_runs.thinking`).
- `AITEST_GENERATION_TIMEOUT=1800` → generation timeout (default 600).
- `AITEST_RESOLUTION_TIMEOUT=300` → resolution timeout (default 120).
These are code changes in the working tree (uncommitted) — see `git diff` for
the review. Server currently left as old 3.8 (under-quantized), spec-OFF.

---

## 7. Evidence & references index

**Evidence folder (canonical):**
`/c/Users/l_a_c/code/llm-benchmarks/evidence/model-ab-2026-08-20/`
- `README.md` — provenance + file index
- `gguf_quantization_confound.md` — *read first*: the model-file bpw confound
- `model_ab_all_conditions.md` — the four-condition table
- `reddit_strixhalo_learnings.md` — community benchmark tuning + corroboration
- `manifest_*.json` — per-leg server manifests
- `eval_{H,I}_*.log`, `llama_*_err.log`, `lmeval_ext_*` — raw logs/JSON

**Session docs:** `docs/sessions/2026-08-19_external_benchmark_and_thinking_on_ab.md`,
`docs/sessions/2026-08-19_thinking_collapse_and_ab.md`,
`docs/sessions/2026-08-18_llm_model_ab_investigation.md`.

**BACKLOG:** AI-046 (status: confounded, no verdict — re-run needed).

---

## 8. Rules that burned us before (hold these)

1. Verify `/v1/models` + `/slots` (not `/props`) before every leg — never infer
   serving config from `/props`.
2. Capture the manifest before EVERY leg. Same flags both models (only the GGUF
   differs). MTP now ON for both.
3. Never run the eval harness and pytest concurrently (port/Milvus deadlock).
4. Flat zeros = failure (timeout/empty-content), not model skill. Check infra
   (config drift, timeouts) before blaming the model.
5. 3.8 thinking-ON can return EMPTY content (token budget → reasoning) — catch
   `length=0` in the logs; it's a failure, not a result.
6. lm-eval chat path can't do loglikelihood (MMLU/ARC standard) nor code_eval
   (HumanEval) — use generation tasks (GSM8K, arc_challenge_chat).
