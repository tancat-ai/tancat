# Session — 2026-08-19 (part 2): External benchmark feasibility + thinking-ON threading

> **Continues** `docs/sessions/2026-08-19_thinking_collapse_and_ab.md` (the
> authoritative handover) and `docs/sessions/2026-08-18_llm_model_ab_investigation.md`
> (§14 mistakes catalogue). This doc records WORK IN PROGRESS: the external
> lm-eval benchmark pipeline brought up on this box, the hard constraints found,
> and the thinking-ON switch threaded through the harness. **Not yet a model
> verdict** — AI-046 stays OPEN until the external ground truth + thinking-ON
> project A/B both complete and reconcile.

---

## 1. Environment reality check (Step 1 gate — measured)

Before anything: the box is an **AMD Strix Halo APU (Radeon 8060S) with 64 GB
unified LPDDR5X** (8×8 GB modules, confirmed via WMI). ~48 GB is carved out for
GPU/VRAM; Windows exposes only ~16 GB as system-visible RAM. **Correction (2026-08-20):**
my earlier note said "~15.8 GB total / only ~3.8 GB free → memory-starved, can't
load 2nd model" — that was the *system-RAM slice*, NOT the full 64 GB pool. The
box is NOT memory-starved; the 48 GB VRAM allocation is what llama.cpp uses.

| Item | Measured | Consequence |
|---|---|---|
| Physical RAM | **64 GB unified LPDDR5X** (8×8 GB modules) | Full pool is large — NOT memory-starved (my earlier 15.8 GB read was the system-RAM slice) |
| GPU | AMD Radeon 8060S (Strix Halo APU) | **No CUDA** → `torch.cuda.is_available()==False` |
| VRAM carve-out | ~48 GB (Windows sees ~16 GB system RAM) | llama.cpp/Vulkan uses the 48 GB allocation |
| torch | 2.13.0+cpu | transformers/llama-cpp GPU backends unavailable |
| llama-server | build **b10483-27e345b57** (Vulkan) | The proven leg-F/G binary (9216-byte loader + DLLs) |
| HH token | cached (`hf_…`) | GPQA is **gated** — token lacks access |
| Disk | 178 GB free | Plenty for venv+datasets |

**Decision:** lm-eval pointed **at the live llama-server** via the OpenAI-compatible chat-completions backend. (Loading a second GGUF copy was possible given 64 GB, but pointing at the live server was simpler and avoided holding two copies resident.)

### Installed + validated
- Separate venv at `C:\Users\l_a_c\code\lm-eval-bench\.venv` (Python 3.13.14).
- `lm-eval 0.4.12` + `lm-eval[api]` (tenacity).
- Backend: `--model local-chat-completions
  --model_args base_url=http://localhost:8080/v1/chat/completions`.
- **Full path proven**: gsm8k limit=2 → scored `exact_match 1.0` (both cases),
  real API calls + JSON persisted. `scratch/lmeval_smoke/`.
- Model default IS thinking-ON for Qwen3.8 (default call returned 202 reasoning
  tokens + content) → chat path gets thinking for free, matching the model card.

### Step-1 benchmark availability (measured — the important find)
Of the four proposed, only **GSM8K** runs cleanly on this box:

| Benchmark | Status | Blocker |
|---|---|---|
| GPQA Diamond | ❌ gated | HF `Idavidrein/gpqa` needs dataset access; token lacks it |
| HumanEval | ❌ Windows | `code_eval` metric raises `NotImplementedError: not supported on Windows` |
| MMLU / ARC (standard) | ⚠️ loglikelihood | `multiple_choice` needs logprobs; chat API refuses |
| **GSM8K** (generative) | ✅ **Runnable** | `generate_until`, non-gated |
| arc_challenge_chat | ✅ Runnable | generative variant exists (not yet run) |

→ External ground truth on this box = **GSM8K (reasoning)** + optionally
`arc_challenge_chat`. LiveCodeBench not present in this lm-eval build by default.

## 2. Server relaunch (was down) — proven leg-G config

The box had rebooted / server was gone (connection refused). Relaunched 3.8 with
the exact proven spec-OFF config from the handover §5, spawn directly (not
llmctl — flash-attn bool bug):
```
<llama.cpp build b10483>\llama-server.exe --model <3.8 GGUF> --port 8080
  --host 0.0.0.0 --ctx-size 156072 --n-gpu-layers 999 --flash-attn on --jinja
  --cache-type-k f16 --cache-type-v f16 --batch-size 1024 --ubatch-size 1024
  --parallel 1 --cont-batching --reasoning-preserve --cache-ram 0
  --ctx-checkpoints 0
```
Verified: `/v1/models` = 3.8 GGUF, `/slots` `n_ctx=156160 speculative=False`,
build b10483. Manifest: `scratch/manifest_relaunch_38_specoff.json`.

## 3. Thinking-ON switch threaded (Step 2 prep) — done, green

Added `AITEST_ENABLE_THINKING` (default off, constant-in-code — mirror of the
temperature pin) + `enable_thinking_default()` in `src/llm_client.py`. Wired
through:
- `src/test_generator.py` `_generate_skeleton_single_call` → `enable_thinking_default()`
- `src/orchestrator.py` `TestOrchestrator(..., enable_thinking=None)` → resolves
  to env default when unset
- `src/placeholder_orchestrator.py` `PlaceholderOrchestrator(..., enable_thinking)`
  → passes to `SemanticCandidateRanker(..., enable_thinking=...)`
- `scripts/eval/eval_runner.py` `_sampling_identity` → records `thinking="on"`
  when env default is truthy (was hardcoded `"off"`)
- `src/semantic_candidate_ranker.py` keeps `enable_thinking=None` = send-nothing
  contract intact (test-guaranteed); explicit `True`/`False` wins.

Gates: ruff ✅, smoke 39/39 ✅, targeted pytest **93 passed** ✅ (ranker, llm_client,
eval_runner_mocks, openai providers, skeleton prompt, orchestrator).

Log: `scratch/llama_38_specoff_new.{log,err.log}`.

## 4. External benchmark runs (in progress)

- **gsm8k / 3.8 / limit 100 / thinking-ON(default) / max_tokens 2048**: running
  → `scratch/lmeval_ext_38_gsm8k.{log, …}`. ~40s/item → ~60 min for 100. Started
  22:03.
- Next: swap server to 3.6, run identical gsm8k leg → `scratch/lmeval_ext_36_gsm8k`.
- Then: thinking-ON project A/B (`eval_harness.py run --mode full --regenerate`,
  `AITEST_ENABLE_THINKING=1 LLM_MAX_TOKENS=16384`) per model, manifest captured
  per leg. **Never run harness + pytest concurrently (deadlock rule); harness
  also waits for lm-eval runs to finish (same server/port).**

## 5. Known remaining work (ordered)

1. Finish external gsm8k for 3.8, then 3.6. Optionally arc_challenge_chat.
2. Thinking-ON project A/B per model (threading above is ready).
3. Reconcile external vs project vs Qwen card.
4. Re-answer AI-046 in BACKLOG with valid numbers only.

**One-line:** infr now honest; external benchmark pipeline is proven on a box
that can only support the live-server path, and of the proposed external tasks
only GSM8K (reasoning) is runnable here — GPQA gated, HumanEval Windows-blocked.
Thinking-ON is threaded and green; the model verdict is still pending valid runs.

---

## 6. RESULTS (complete) - the thinking-ON A/B ran, but see the CONFOUND caveat

> ⚠️ **READ FIRST (2026-08-20 correction):** the numbers below are REAL for the
> FILES tested, but the two GGUFs are **not equivalent-precision quantizations**
> (3.6 = 6.71 bpw, 3.8 = 3.30 bpw) - so this is NOT a clean architecture
> comparison and does NOT support a "3.6 wins" or "3.8 is worse" verdict.
> See §7 CORRECTION. Evidence: `llm-benchmarks/evidence/model-ab-2026-08-20/`.

## 6 (original). Thinking-ON A/B results (files as-tested, per-condition)

Both thinking-ON legs ran to completion (H=3.6, I=3.8). Full verified table:

| Condition | 3.6 | 3.8 | delta |||
|---|---|---|---|---|---|
| thinking OFF (legs F/G) | **76.1%** | 62.4% | +13.7 | 15:08 / 15:58 |
| thinking ON raw (legs H/I) | **73.4%** | 48.6% | +24.8 | |
| thinking ON excl. eval-005 timeout | 75.3% | **62.4%** | +12.9 | |
| External lm-eval GSM8K (thinking ON, n=100) | **0.82** | 0.81 | TIE | |

### Key findings
1. **Enabling thinking does NOT flip the result.** 3.8 thinking-ON (excl. the
   timed-out story) = 62.4%, the SAME as its thinking-OFF = 62.4%. 3.6 stays
   ~73-76% in every condition. Contradicts the Qwen-card prediction that 3.8
   overtakes 3.6 with thinking ON.
2. **3.8 thinking-ON empty-content failure (real, model-specific):** on eval-005
   (lv_insurance, 10 criteria) the skeleton call returned `length=0 chars` after
   1447.89s — ALL 16384 max_tokens went to reasoning, content empty (the got=0
   collapse from the 08-18 doc re-produces, under thinking-ON, for 3.8). The retry
   then exceeded the generation timeout. 3.6 had ZERO such events in leg H.
3. Raw 3.8 thinking-ON 48.6% is a timeout/empty artifact — NOT a verdict.

### Env/tooling changes made this session (all green)
- `AITEST_ENABLE_THINKING` (default off) + `enable_thinking_default()` in
  `src/llm_client.py`; threaded skeleton + both resolution rankers (orbiter and
  element_matcher) + recorded in `eval_runs.thinking`.
- `AITEST_RESOLUTION_TIMEOUT` (default 120) and `AITEST_GENERATION_TIMEOUT`
  (default 600) env-driven so thinking legs can raise budgets fairly (constant-
  in-code defaults, no silent drift).
- lm-eval 0.4.12 in separate py3.13 venv (`C:\Users\l_a_c\code\lm-eval-bench`),
  local-chat-completions backend → live server.
- Results + logs: scratch/eval_{H,I}_thinkingon*.log, scratch/lmeval_ext_*.log,
  scratch/model_ab_all_conditions.md, manifests manifest_thinkingon_{36,38}.json.

### Handover note for next session
- The 1800s generation timeout was NOT honored on the 3.8 eval-005 retry (call
  ran 8746s). Investigate: server may ignore/override client timeout once in
  flight. Worth a follow-up.
- AI-046 next step: write the validated verdict into BACKLOG (see §7 doc),
  treating the 13pt 3.6 advantage as real for THIS harness on THESE sites, with
  the external caveat that the card's coding/agentic benchmarks couldn't be run.

---

## 7. Reconcile + harness inspection (Step 3) — 3.8's failures are wrong-locator, not tolerance

Compared saucedemo (biggest 3.8 delta) raw_report per condition against the
golden key. Conclusion: **3.8's mis-resolutions are genuine wrong-locator picks,
NOT golden-key tolerance bugs.**

| saucedemo placeholder | golden | 3.8 thinking-ON chose | verdict |
|---|---|---|---|
| CLICK Add-to-cart (Backpack) | `#add-to-cart-sauce-labs-backpack` (tol=[]) | `#item_3_title_link` | WRONG |
| CLICK Cart icon | `.shopping_cart_link[...]` | `#item_3_title_link` | WRONG |
| CLICK checkout / continue / finish | `#checkout`/`#continue`/`#finish` | `#item_3_title_link` | WRONG |
| FILL first / last / zip | `#first-name`/`#last-name`/`#postal-code` | `#user-name` (page-1 anchor) | WRONG |
| ASSERT product list / cart summary | `[data-test=...]` | `expect(page).to_have_url(cart.html)` | wrong URL |

3.8 (esp. thinking-ON) repeatedly **anchors on a single familiar locator**
(`#item_3_title_link` for half the actions, `#user-name` for the checkout
fields) instead of selecting the page-specific element. Golden key has NO
tolerance for `#add-to-cart-sauce-labs-backpack`, and `#item_3_title_link` is
in none of the tolerance lists — so these are plain wrong, not valid-alternate
rejections. This is a resolution-quality difference, not an eval-tolerance bug.

### ⚠️ CORRECTION (2026-08-20): the A/B is MODEL-FILE CONFOUNDED - no verdict

The numbers above (3.6 >= 3.8 across conditions) are REAL for the files tested,
but **the two GGUFs are not equivalent-precision quantizations**, so they are NOT
a clean architecture comparison. Measured via `gguf.GGUFReader`:

| | Qwen3.6-27B | Qwen3.8-27B (Q4_K_XL) | Qwen3.8 (Q6_K_XL) |
|---|---|---|---|
| overall bpw | **6.71** | 3.30 | 4.00 |
| attn_qkv bpw | 6.29 (Q3_K) | 2.56 (Q2_K) | 4.50 |
| Q2_K tensors | 70/866 (8%) | 325/866 (38%) | 96/866 |

So the "3.8 ~/worse" result is largely a **quantization-quality artifact**: a
6.7 bpw model was compared to a 3.3-4.0 bpw model. This is the honest answer to
"why would 3.8 be same or worse" - on this box the 3.8 GGUF is far more
aggressively quantized than the 3.6 one, so the A/B answers "which precision",
not "which model". No matched-precision Qwen3.8 is available to test.

**Corrected bottom line:** AI-046 has NO defensible architecture verdict from
current data. A valid re-test requires a Qwen3.8 at ~6.7 bpw (matching 3.6).
Evidence: `llm-benchmarks/evidence/model-ab-2026-08-20/`.
