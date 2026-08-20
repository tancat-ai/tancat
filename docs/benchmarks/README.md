# Benchmark Documentation — AI-Playwright-Test-Generator

## Recommended Production Configuration (Qwen3.8-27B, 5.21 bpw)

| Component | Setting |
|-----------|---------|
| **Model** | `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf` (5.21 bpw, attn_qkv 6.12 bpw) |
| **Location** | `C:\Users\l_a_c\.lmstudio\models\unsloth\Qwen3.8-27B-GGUF\Qwen3.8-27B-UD-Q4_K_XL_v2.gguf` |
| **Server** | llama.cpp b10483 (vulkan, MTP ON) |
| **MTP (Speculative Decoding)** | **ON** — `--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.0` |
| **Thinking** | **ON** (`AITEST_ENABLE_THINKING=1`) |
| **Temperature** | 0.0 (deterministic) |
| **Max tokens** | 16384 (`LLM_MAX_TOKENS=16384`) |
| **Context** | 156,072 tokens (`--ctx-size 156072`) |
| **GPU layers** | All (`--n-gpu-layers 999`) |
| **Flash attention** | ON |
| **KV cache** | f16 (`--cache-type-k f16 --cache-type-v f16`) |
| **Batch** | 1024 (`--batch-size 1024 --ubatch-size 1024`) |
| **Reasoning preserve** | ON (`--reasoning-preserve`) |
| **Timeouts** | `AITEST_RESOLUTION_TIMEOUT=300`, `AITEST_GENERATION_TIMEOUT=1800` |

### Launch Command (llama-server)
```bash
llama-server.exe \
  --model "C:\Users\l_a_c\.lmstudio\models\unsloth\Qwen3.8-27B-GGUF\Qwen3.8-27B-UD-Q4_K_XL_v2.gguf" \
  --port 8080 --host 0.0.0.0 \
  --ctx-size 156072 --n-gpu-layers 999 \
  --flash-attn on --jinja \
  --cache-type-k f16 --cache-type-v f16 \
  --batch-size 1024 --ubatch-size 1024 --parallel 1 \
  --cont-batching --reasoning-preserve \
  --cache-ram 0 --ctx-checkpoints 0 \
  --spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.0
```

### Why MTP ON?
- **2.0× decode speedup** (11.5 → 22.5 t/s measured)
- Fixes timeout/empty-content failures (eval-005 completes)
- **Zero quality loss** — llama.cpp verifies every draft token, output is byte-identical
- Acceptance rate 60–64%, mean draft length ~2.8 tokens

## Benchmark Scripts

### `scripts/benchmarks/bench_speed.py`
Quick throughput test against a live llama-server. Measures:
- Structured skeleton-style prompt (512 tokens)
- Prose prompt (256 tokens)
- Reports wall time and tokens/sec

**Usage:**
```bash
python scripts/benchmarks/bench_speed.py
```

### External lm-eval harness
Located at `llm-eval-bench/` (separate repo). Runs GSM8K, MMLU, etc.

```bash
cd ../llm-eval-bench
uv run lm_eval \
  --model local-chat-completions \
  --model_args base_url=http://localhost:8080/v1/chat/completions,model=Qwen3.8-27B-GGUF,num_concurrent=1 \
  --tasks gsm8k \
  --batch_size 1
```

## Model Precision Comparison

| Model | Overall bpw | attn_qkv bpw | Q2_K tensors | Notes |
|-------|-------------|--------------|--------------|-------|
| **Qwen3.8-27B (new v2)** | **5.21** | **6.12** | 191/866 | Recommended — near-matched QKV |
| Qwen3.8-27B (old) | 3.30 | 2.56 | 325/866 | Under-quantized — deprecated |
| Qwen3.6-27B-MTP (reference) | 6.71 | 6.29 | 70/866 | Higher precision baseline |

> **Key finding:** The new 5.21 bpw quant has near-matched QKV weights (6.12 vs 6.29 bpw) to the 3.6 reference. The remaining gap is in FFN/SSM tensors, which affect quality less.

## Project Evaluation Results (Leg K — MTP ON, Thinking ON)

| Metric | Value |
|--------|-------|
| Resolution accuracy (excl eval-005) | 63.5% |
| eval-005 (lv_insurance) | 1/24 (4%) — completes, no timeout |
| All 8 stories regenerated | 0 failures |
| Decode throughput | ~22.5 t/s |

## Directory Layout

```
scripts/benchmarks/       # Project-specific benchmark scripts
├── bench_speed.py        # Throughput test vs live server
docs/benchmarks/          # This documentation
llm-eval-bench/           # External lm-eval harness (separate clone)
scratch/                  # Ephemeral debug/one-off scripts (not committed)
```

## Cleanup Notes (2026-08-20)
- Removed deprecated under-quantized 3.8 file (3.30 bpw)
- Consolidated benchmark scripts into `scripts/benchmarks/`
- External benchmarks moved to dedicated `llm-eval-bench/` repo