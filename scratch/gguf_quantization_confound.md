# ⚠️ MODEL-FILE CONFOUND — 3.6 and 3.8 GGUFs are NOT equivalent quantizations

NOTE: This INVALIDATES the A/B as a pure 3.6-vs-3.8 model comparison. The two
GGUF files, despite both being named "UD-Q4_K_XL", use materially different
weight precision. Verified by reading tensor metadata via gguf.GGUFReader.

## Measured (per-tensor, both = 866 tensors, 27.32B params each)

| Metric | Qwen3.6-27B | Qwen3.8-27B |
|---|---|---|
| File size | 17.91 GB | 17.92 GB |
| Overall weighted bpw | **6.71** | **3.30** |
| attn_qkv.weight bpw | **6.285 (Q3_K)** | **2.562 (Q2_K)** |
| Q2_K tensors | 70 / 866 (8%) | **325 / 866 (38%)** |
| block-0 ffn_down/up | Q3_K / Q8_1 | Q2_K / Q2_K |
| block-0 ffn_gate | Q8_1 | IQ4_NL |
| block-0 ssm_out | Q4_0 | Q2_K |

## Conclusion
3.8 is a MUCH lower-precision quantization (~3.3 bpw, ~38% Q2_K) than 3.6
(~6.7 bpw, Q3_K/Q4_0/Q8_1 mix). This is a fundamental model-FILE confound that
NONE of my infra controls could remove: same flags, same temp 0.0, same thinking,
same stories — but the underlying weights are not equivalent quality.

So "3.8 scores same-or-worse" is partly (mostly) a quantization artifact, NOT a
clean verdict that the Qwen3.8 ARCHITECTURE is worse at Playwright resolution.
The card's 3.8>3.6 claims (WebArena/LiveCodeBench/SWE-bench) are on fp16/official
checkpoints and remain untested here.

## What a valid re-test needs
- A 3.8 GGUF at MATCHED precision (same bpw recipe as 3.6, ideally both Q4_K or
  both ~6.7bpw), OR
- Re-run both at a comparable quantization level before drawing any model verdict.

## Reframe of AI-046
The correct conclusion for THIS evidence set is NOT "3.6 wins, keep 3.6".
It is: **the local 3.8 GGUF is too aggressively quantized (~3.3bpw) to be a fair
opponent; no model-architecture verdict is possible from this data.** AI-046 stays
QUANTIFICATION-CONFOUNDED until a matched-precision 3.8 is tested.
