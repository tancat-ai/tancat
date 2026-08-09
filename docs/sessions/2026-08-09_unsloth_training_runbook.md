# Unsloth Studio Training Runbook (2026-08-09)

**Status:** model downloading, training not yet started
**Machine:** AMD Ryzen AI MAX+ 395 / Radeon 8060S (Strix Halo), 64 GB unified
memory (BIOS carves ~48 GB as UMA VRAM; Windows sees ~17 GB system RAM).

---

## 1. Hardware / capability summary (verified)

| Item | Value |
|---|---|
| CPU/GPU | AMD Ryzen AI MAX+ 395, Radeon 8060S (Strix Halo, gfx1151) |
| Unified memory | 64 GB total; ~48 GB dedicated UMA VRAM (dxdiag) |
| Unsloth AMD support | ✅ **Full** — RDNA 3.5 Strix Halo: Windows + WSL + Linux |
| Training method | **bitsandbytes-based QLoRA** (4-bit) — the AMD-supported path |
| Inference runtime | llama.cpp (Vulkan) on :8080 — GGUF files |
| LLM endpoint | http://localhost:8080/v1/models (auto-detected by pipeline) |

**Key constraint:** Studio **cannot train GGUF** ("GGUF format models are
excluded from training — inference only"). Training needs **safetensors**.

---

## 2. Model selection (the confusing part, resolved)

**DO NOT use `unsloth/Qwen3.6-27B-NVFP4`** — NVFP4 is NVIDIA's FP4 format
(benchmarked on NVIDIA B200), no AMD support.

**The two bnb-4bit repos don't exist yet** (`Qwen3.6-27B-bnb-4bit`,
`Qwen3.6-27B-Instruct-bnb-4bit` — both 401 on HF).

**The trainable option for AMD right now:** the **full-precision safetensors**
model. Studio quantizes it to 4-bit in-memory via bitsandbytes QLoRA.

| Model | Format | Trainable on AMD? | Size |
|---|---|---|---|
| `Qwen/Qwen3.6-27B` (official) | safetensors BF16 | ✅ YES | 55.6 GB |
| `unsloth/Qwen3.6-27B` | safetensors BF16 | ✅ YES | 55.6 GB |
| `unsloth/Qwen3.6-27B-NVFP4` | NVIDIA FP4 | ❌ | ~17 GB |
| `nvidia/Qwen3.6-27B-NVFP4` | NVIDIA FP4 | ❌ | — |
| `Qwen/Qwen3.6-27B-FP8` | FP8 | ❌ (needs NVIDIA) | — |
| `Qwen3.6-27B-*-GGUF` | GGUF | ❌ (inference only) | — |
| `mlx-community/Qwen3.6-27B-*` | MLX | ❌ (Apple only) | — |

**Smaller first-run options (download fast, AMD-trainable):**
- `unsloth/Qwen2.5-7B-bnb-4bit` — 5.5 GB (~3-4 h at ~0.4 MB/s)
- `unsloth/Qwen3-8B-bnb-4bit` — 6.1 GB
- `unsloth/Qwen2.5-3B-bnb-4bit` — 2.1 GB (~1.5 h)

---

## 3. Download speed reality

At current network speed (~0.4 MB/s to HF), the 55.6 GB model takes ~39 h.
The Studio download was seen at 0 B/s initially, then sped up (~30 min ETA
per the user). If it stalls: cancel and use the `hf` CLI which resumes:

```bash
hf download Qwen/Qwen3.6-27B --local-dir ~/.unsloth/studio/models/Qwen3.6-27B
```

---

## 4. Studio settings (the run)

1. **Model:** Type `Qwen/Qwen3.6-27B` (or `unsloth/Qwen3.6-27B`) — format
   **safetensor** (NOT gguf/mlx)
2. **Method:** `QLoRA` (4-bit, AMD-supported)
3. **Model Type:** `Text`
4. **Dataset:** Local tab → upload `training_data/playwright_skeleton_alpaca.jsonl`
   → format `alpaca` → Eval split ~10%
5. **Hyperparameters:**

| Section | Setting | Value |
|---|---|---|
| Main | Context Length | 2048 |
| | Learning Rate | 2e-4 |
| LoRA | Rank / Alpha / Dropout | 16 / 32 / 0.05 |
| | Target Modules | all on |
| Optimization | Epochs | 3 |
| | Batch Size | 4 |
| | Grad Accumulation | 8 |
| | Optimizer | AdamW 8-bit |
| Schedule | LR Scheduler / Warmup | linear / 5 |
| | Gradient Checkpointing | unsloth |
| ⚠️ | **Train on Completions** | **ON** |

6. **Start Training** → watch overlay (blue=download, amber=load, green=train)

---

## 5. After training: export + swap (NO .env edit needed)

1. **Export → GGUF `q4_k_m`** (AMD-aware llama.cpp ROCm prebuilt, auto-matched
   to gfx1151)
2. Save to `~/.lmstudio/models/unsloth/` (alongside current GGUFs)
3. **In LM Studio / llama.cpp on :8080: unload current model, load the
   fine-tuned GGUF**
4. Pipeline auto-detects the loaded model via `/v1/models` — no config change.

**Why no .env change:** the project's `auto_detect_provider()` probes
`:8080/v1/models` and uses whatever is loaded. `.env` `OPENAI_MODEL` is only a
fallback when the server is unreachable at startup (and it's commented out).

---

## 6. Baseline measurement (before/after comparison)

**Baseline captured** `training_data/model_baseline_qwen36_27b_ud_q4_k_xl.json`
with the full reproducibility envelope (model path, n_ctx, temp, git commit):

| Metric | Baseline (current model) |
|---|---|
| Valid skeleton rate | 100% (35/35) |
| Criteria cover rate | 100% (35/35) |
| Hallucinated login | 0% |
| Total placeholders | 1504 |
| Pipeline eval static | 97.9% |

**After training + model swap, re-run:**

```bash
python scripts/eval/eval_model_baseline.py --save training_data/model_baseline_finetuned.json
python scripts/eval/eval_harness.py run --mode static   # pipeline-level
```

Compare the two JSONs — the delta is attributable to training (same runtime,
same codebase commit).

---

## 7. Training dataset state (clean, ready)

| File | Rows | Notes |
|---|---|---|
| `playwright_skeleton_alpaca.jsonl` | 158 | clean, 0 hallucinated login |
| `playwright_resolved_alpaca.jsonl` | 96 | clean (ecommerce regenerated) |
| `playwright_resolution_alpaca.jsonl` | 90 | golden keys, always clean |
| `synthetic_stories.jsonl` | 35 | seed stories |
| `synthetic_skeletons_alpaca.jsonl` | 58 | staging (already merged into 158) |

**Don't load `synthetic_skeletons_alpaca.jsonl` in Studio** — it's the per-run
staging file, already merged into the main skeleton file.

---

## 8. Known caveats

- **RAG learning lock (B-047 follow-up):** `learn_from_evidence` inside pytest
  subprocesses is blocked while the resolve-and-learn parent holds the Milvus
  store (process-lifetime lock). Deferred fix: parent-side sidecar sweep. Not a
  training blocker.
- **Golden-pattern cross-site +20 (residual B-047):** `scoring_bonus_for`
  golden branch doesn't check site_hash. Small; pipeline-level, not data.
- **NVFP4 is NVIDIA-only** — don't be tempted by the smaller download size.
- **bnb-4bit 27B doesn't exist yet** — check HF periodically; when it lands it
  will be the ideal AMD-trainable quant (no 55GB full download needed).

## 8b. Fallback: cloud training (AMD doc)

If local training ever hits a wall (VRAM, download, instability), Unsloth's
AMD doc points at **AMD Developer Cloud** (one-click MI300X notebooks, 192GB
VRAM) and the **AMD AI Developer Program** (free credits). Same unsloth
notebooks, swap in the AMD cloud URL. The corpus + baseline transfer directly
— only the compute moves.

---

## 9. Related commits

- `cc2753f` login URL fix + auth-guard story synth
- `bbc0a08` --clean filter (55 hallucinated-login rows dropped)
- `b4d6709` skeleton prompt DO-NOT-INVENT-AUTH (root cause)
- `f7318b2` ecommerce regen + handoff
- `3a530e6` / `54e7546` model baseline measurement (+ metadata)
