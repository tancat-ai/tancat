# External lm-eval GSM8K (limit 100, thinking ON via model default, temp 0, max_tokens 2048)

Backend: local-chat-completions -> live llama-server build b10483, ctx 156160, spec OFF.
Same 100-question subset, identical flags both legs. Captured manifests:
scratch/manifest_relaunch_{36,38}_specoff.json.

| Model | n | flexible-extract | strict-match | leg log |
|-------|---|------------------|--------------|---------|
| Qwen3.8-27B | 100 | 0.81 | 0.77 | scratch/lmeval_ext_38_gsm8k.log |
| Qwen3.6-27B | 100 | **0.82** | **0.82** | scratch/lmeval_ext_36_gsm8k.log |

## Interpretation (external ground truth, reasoning, thinking ON)
- **Tie / 3.6 marginally ahead on strict-match.** External GSM8K does NOT
  reproduce a 3.8-vs-3.6 gap in the direction of Qwen's card. GSM8K is
  arithmetic reasoning; the card's 3.8>3.6 claims are on WebArena/LiveCodeBench/
  SWE-bench (coding/agentic), which are not runnable on this box (HumanEval
  code_eval is Windows-blocked; GPQA gated).
- 3.6 was ~2.5x slower per item (more reasoning tokens: ~619 vs ~202) yet not
  more accurate. In a 2048-token budget both fit; 3.6 spends more on reasoning
  for equal/slightly-better strict correctness.

NOTE: limit=100 is a subset (13% of GSM8K test). Directional, not the full
1319-item benchmark. But it is an apples-to-apples same-config external signal.
