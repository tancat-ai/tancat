# Strix Halo (Windows) + Unsloth: Training a 27B with QLoRA — Field Guide

**Date:** 2026-08-10 · **Machine:** Ryzen AI MAX+ 395 / Radeon 8060S (Strix Halo, gfx1151), 64 GB LPDDR5X unified
**Result:** ⚠️ **FAILED EXPERIMENT (closed 2026-08-11).** Training ✅ (4-bit QLoRA, completion-only, fused CE, final loss 0.081) — but the GGUF **export never completed**, so no usable fine-tuned model was produced and all artifacts were deleted. Read this doc to learn what works and which walls can't be climbed on a 64 GB Windows box.
**Companion doc:** `docs/sessions/2026-08-09_unsloth_training_runbook.md` (the original plan; this doc records what actually worked and where it ended).

---

## TL;DR — the working recipe

```bash
# Use the Studio venv (it has the gfx1151 ROCm build: torch 2.11.0+rocm7.13.0)
UNSLOTH_MOE_BACKEND=native_torch \
  ~/.unsloth/studio/unsloth_studio/Scripts/python.exe scripts/train_27b_qlora.py
```

**Three things are non-negotiable:**
1. `UNSLOTH_MOE_BACKEND=native_torch` — prevents the `torch._grouped_mm` MoE probe from **segfaulting** on ROCm (Qwen3.6-27B is MoE).
2. **4-bit QLoRA** — the model must be 4-bit (~19 GB) or it will not fit (16-bit = 55.6 GB > ~44 GB usable pool).
3. **`scripts/train_27b_qlora.py`** — the direct Unsloth path, NOT Studio's Train UI (see "Why not Studio" below).

Working config (runbook §4 adapted for 64 GB): context **1024** (not 2048), batch **4** × grad-accum **8** = effective 32, LoRA 16/32/0.05 all modules, 3 epochs, lr 2e-4, AdamW 8-bit, linear warmup 5, completion-only masking via `train_on_responses_only`.

---

## Why not Unsloth Studio's Train UI

Studio silently **flips QLoRA 4-bit → 16-bit** for "brand-new" architectures (Qwen3.6 routes to a latest-transformers sidecar where 4-bit is disabled). A 16-bit 27B (55.6 GB) cannot fit the ~44 GB usable pool → layers spill to CPU → the fused cross-entropy dies with:

```
Unsloth: No or negligible GPU memory available for fused cross entropy.
```

Env var `UNSLOTH_STUDIO_NO_LATEST_TRANSFORMERS=1` did **not** reliably disable the flip. The direct script path sidesteps all of it: same model, same hyperparams, but 4-bit actually loads and trains.

---

## What DIDN'T work (the rabbit holes — read before retrying)

| Attempt | Result | Why it failed |
|---|---|---|
| Studio Train UI, 16-bit (its default for Qwen3.6) | ❌ fused-CE crash | 55.6 GB > pool; CE found 0 free GPU memory |
| BIOS: 48 GB dedicated VRAM / 16 GB system | ❌ model load crashed (0xC0000005) | host-RAM streaming of 55.6 GB can't fit 16 GB system RAM |
| BIOS: "everything to shared pool" | ⚠️ pool grew to ~47.6 GB (Task Manager) but HIP reports 36–38 GB | unified-memory reporting is unstable (HIP allocates 44–46 GB despite reporting 38.6) |
| Reducing page file | ❌ (rejected — would hard-OOM) | page file is a symptom absorber, not the bottleneck |
| `PYTORCH_HIP_ALLOC_CONF=expandable_segments:True` | 💥 native crash at startup | unsupported/broken on this torch+ROCm build |
| Direct `load_in_4bit=True` (raw from_pretrained) | 💥 flaky native crashes | bnb 4-bit path crashes intermittently on this stack — retry usually works (the working script calls it once, cleanly) |
| 8-bit (`load_in_8bit`) | ❌ `Qwen3_5ForCausalLM` missing | default transformers 5.5.0 lacks the class; Studio has no 8-bit training option |
| Studio + `UNSLOTH_STUDIO_NO_LATEST_TRANSFORMERS=1` | ❌ still 16-bit / CE crash | the flip isn't reliably gated by the env var |
| batch 4 @ ctx 2048 | ⚠️ step 1 OK (loss 0.94), **OOM at step 2** | 19 GB model + batch-4 activations fill the pool |
| batch 2 @ ctx 2048 | ❌ page-file thrash, no step in 22 min | 44 GB model+activations near 64 GB physical limit |
| batch 1 @ ctx 2048 (full corpus) | ❌ compile thrash | 158 unique sample lengths → huge Triton compile + memory pressure |
| **batch 4 @ ctx 1024** | ✅ **works** | activations halved, model fits, kernels compile in ~10 min |

---

## Key technical findings

1. **HIP memory reporting is a floor, not a ceiling.** `torch.cuda.mem_get_info()` reports 38.6 GB but allocations of 44–46 GB succeed. Task Manager's "GPU Memory" (~47.6 GB = 0.3 dedicated + 47.3 shared) is the honest number. The shared pool is ~75% of system RAM (driver policy), not "64 GB minus in-use".
2. **16-bit 27B is physically impossible here** — needs ~65–70 GB (weights + optimizer + CE logits). No BIOS, page-file, or allocator setting changes arithmetic.
3. **`UNSLOTH_MOE_BACKEND=native_torch` is mandatory** for Qwen3.6-27B (MoE). Without it: silent hard crash during load.
4. **The fused CE works** with a true 4-bit load (loss 0.43–0.94 on step 1). Its "No or negligible GPU memory" error is the *symptom* of an oversized (16-bit) load, not a CE bug.
5. **`train_on_responses_only` signature:** first arg is the **trainer**, then instruction/response markers:
   ```python
   from unsloth_zoo.dataset_utils import train_on_responses_only

   trainer = train_on_responses_only(trainer, instruction_part="### Instruction:", response_part="### Response:")
   ```
6. **First step is brutal (~10 min):** Triton compiles kernel variants per sample length. Epochs 2–3 are faster (cache reused). Compile cache lives in `~/unsloth_compiled_cache/`.
7. **AMD driver TDR events are survivable** — Windows may pop a "driver stopped responding" notification under sustained ROCm load; the process usually continues. Check the training log/step counter before assuming it died.
8. **bitsandbytes on Windows ROCm needs `BNB_ROCM_VERSION`** — the Studio installer already sets it (714); the DLL warning in logs is expected and benign.

## The export wall — why no GGUF ever came out of this machine

Training is the easy half. The GGUF export needs a **16-bit intermediate** (~55 GB) — and this machine hit **four independent walls**:

| Wall | Detail |
|---|---|
| 1. `merged_16bit` save quirk | `save_pretrained_merged(save_method="merged_16bit")` **writes the adapter, not the merge** — the `merge_and_unload()` call is only wired for `merged_4bit` in this unsloth version |
| 2. Arch lacks merge | `Qwen3_5ForConditionalGeneration` (multimodal/MTP variant) has **no `merge_and_unload`** at all → explicit merge fails with `AttributeError` |
| 3. Memory | Even a working merge needs ~55 GB resident; the usable pool is ~44–46 GB |
| 4. Disk | Merge shards (55 GB) + f16 GGUF (55 GB) ≈ **~110 GB peak**; best available was ~95 GB |

**Also hit along the way:** the llama.cpp converter crashes with `assert opt_num_mtp_layers != 0` because unsloth's export rewrites `config.json` and drops `mtp_num_hidden_layers`. I patched `~/.unsloth/llama.cpp/conversion/qwen.py` to infer MTP from `mtp_use_dedicated_embeddings` (still in place — harmless, and needed if anyone retries). After the patch, the converter then failed with "no tensors were written" because no merge had produced shards.

**Final status (2026-08-11):** experiment closed — trained LoRA checkpoint, merged scratch, failed export dir, and the 52 GB base-model cache were all deleted (~200 GB freed). The 19 GB inference GGUF on :8080 was untouched.

**Bottom line for anyone retrying:** the 27B needs a machine where the 16-bit merge fits (≈110 GB free disk AND ≈55 GB addressable memory, or a Linux/128 GB Strix Halo setup). On a 64 GB Windows box, stop at a **14B bnb-4bit** model — its export fits (~28 GB merge + ~9 GB GGUF) and the whole pipeline completes.

---

## After training — what actually happened

1. ✅ Checkpoint saved to `training_data/lora_checkpoints/qwen36-27b-playwright-skeleton/` (adapter 318 MB, loss 0.94 → 0.081) — **deleted 2026-08-11**
2. ❌ Export GGUF `q4_k_m` — **never completed** (see the export wall above). The baseline comparison was therefore never run — there was no fine-tuned model to deploy to :8080.
3. The intended end-to-end comparison (`eval_model_baseline.py` → `compare_model_baselines.py`) remains valid tooling, just unusable for a model this machine can't export.

---

## If you're on a different machine

- **128 GB Strix Halo (Linux/WSL):** the community path works well — see sleepingrobots.com's guide (TheRock gfx1151 nightlies + bitsandbytes preview wheel + `sitecustomize.py`). LoRA on up to ~70B at 4-bit is feasible there.
- **64 GB, Windows (this guide):** 4-bit QLoRA up to ~27B *trains*, but the **GGUF export caps the usable model at ~14B** (the 16-bit merge doesn't fit). Prefer bnb-4bit repos (`*-bnb-4bit`) which load 4-bit without the brand-new-arch complications.
- **NVIDIA:** none of this applies — Studio just works.

---

## Session artifacts

- Training script: `scripts/train_27b_qlora.py` (config constants at top — context/batch are the memory dials). Kept in the repo as the recipe; the trained checkpoint it produces was deleted.
- Export script: `scripts/export_27b_gguf.py` (documents the merge/convert attempts, incl. the failures)
- Converter patch (still in place, harmless): `~/.unsloth/llama.cpp/conversion/qwen.py` — infers MTP layers from `mtp_use_dedicated_embeddings`
- Original plan: `docs/sessions/2026-08-09_unsloth_training_runbook.md`
- Roadmap: AI-041 (this training run) in `BACKLOG.md` / `docs/plans/ROADMAP_ROADTO_PRODUCTION.md`
