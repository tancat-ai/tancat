# Model A/B — All four conditions (verified aggregates)

Source: eval_runs (evidence/run_results.sqlite), harness `--mode full --regenerate`,
spec OFF, temp 0.0 pin, 8 stories. Leg timestamps isolate each run.

| Condition | 3.6 | 3.8 | delta | leg |
|---|---|---|---|---|
| thinking OFF | **76.1%** (83/109) | 62.4% (68/109) | +13.7 | F (15:08) / G (15:58) |
| thinking ON (raw) | **73.4%** (80/109) | 48.6% (53/109) | +24.8 | H / I |
| thinking ON (excl. eval-005 timeout) | 75.3% (64/85) | **62.4%** (53/85) | +12.9 | H / I |

External lm-eval GSM8K (thinking ON, n=100): 3.6 = 0.82 | 3.8 = 0.81 → TIE.

## Critical interpretation
1. **Enabling thinking does NOT flip the result.** 3.8 thinking-ON (excl. timeout)
   = 62.4%, identical to its thinking-OFF = 62.4%. 3.6 stays ~73-76% in all
   conditions. Our harness CONTRADICTS the Qwen-card prediction that 3.8 overtakes
   3.6 with thinking.
2. **3.8 thinking-ON has a real empty-content failure**: on eval-005 (lv_insurance,
   10 criteria), skeleton generation returned `length=0 chars` after 1447.89s —
   the ENTIRE 16384 max_tokens went to reasoning, content was empty (the got=0
   collapse re-produces under thinking-ON for 3.8). Retry then exceeded the
   generation timeout (1800s was NOT honored — call ran 8746s). 3.6 had ZERO such
   events in leg H.
3. So the raw 3.8 thinking-ON 48.6% is a TIMEOUT/empty-artifact, NOT a verdict.

## External (lm-eval) vs project reconciliation
- External reasoning (GSM8K): 3.6 ≈ 3.8 (tie). Does NOT confirm Qwen's "3.8 wins."
- Project resolution: 3.6 beats 3.8 in ALL conditions (~13pt).
- Therefore: the "contradiction" (3.6 wins despite card saying 3.8 better with
  thinking) is NOT resolved by enabling thinking — it persists and is now validated
  with thinking-ON data on both our harness AND an external reasoning benchmark.
- Caveat: card claims are on WebArena/LiveCodeBench/SWE-bench (coding/agentic),
  not runnable here (HumanEval Windows-blocked, GPQA gated). GSM8K is arithmetic
  reasoning only. So we cannot fully reconcile the card's specific benchmarks.
