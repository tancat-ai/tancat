# AI-059 — Learning-impact isolation — Session 1

> **Date:** 2026-08-27  
> **Goal:** capture a controlled cold/warm-positive baseline before AI-058.  
> **Plan:** `docs/plans/AI-059_learning_impact_plan.md`

## Outcome

The metric extractor and runner were exercised against regenerated tests on the
deterministic ecommerce mock. The run proves store restoration, auto-learning
isolation, RAG retrieval diagnostics, per-leg evidence, and snapshot hashing.
It does **not** justify AI-058 yet.

## Controlled setup

- Site: `mock_sites/ecommerce`, served at `http://localhost:8781`
- Pipeline: linear `TestOrchestrator.run_pipeline()`
- Mode: flat (`pom_mode=False`), not LangGraph/POM
- Evaluation: regenerate (fixed story/criteria, fresh skeleton and resolution)
- Provider/model: `openai-local`, LM Studio Qwen3.8-27B GGUF
- Sampling: temperature `0.0`, thinking off
- Auto-learning: disabled (`AI059_DISABLE_AUTO_LEARN=1`)
- Bundled auto-seed: disabled during measurement
- Cold store: empty snapshot
- Warm store: curated ecommerce-only positive snapshot (six accepted patterns)
- Same command, mock site, story/criteria, and model settings per leg

## Multi-story matrix

Three fixed stories were regenerated in each leg:

1. Add a product and verify the cart
2. Browse products and open product detail
3. Complete checkout and verify confirmation

The runner initially exposed a collection issue because all temporary packages
used `test_generated.py`; the execution was repeated with pytest's
`--import-mode=importlib` so duplicate module names could not mask results.
Auto-learning was disabled during the recovered execution.

## Results

| Leg | Tests | Passed | Mean pass depth | First-pass green | Reviewed false-positive rate |
|---|---:|---:|---:|---:|---:|
| Cold | 14 | 13 | 1.000 | 0.929 | 0.286 |
| Warm-positive | 14 | 13 | 1.000 | 0.929 | 0.286 |

The one failure in each leg was the same product-detail test: the generated
journey clicked the Products navigation link twice and asserted the wrong URL.
Several passing tests were manually marked invalid because they used broad
assertions or did not complete the intended checkout action.

The sidecar metric reports `mean_pass_depth=1.0` even for the product-detail
failure because the failing `expect(page).to_have_url(...)` assertion is not
recorded as an EvidenceTracker step. This is a measurement gap: the current
sidecar schema cannot classify failures outside tracker calls.

## Retrieval diagnostics

| Leg | RAG queries | Non-empty queries | Retrieved patterns |
|---|---:|---:|---:|
| Cold | 46 | 0 | 0 |
| Warm-positive | 46 | 11 | 16 |

Warm results were all learned and site-scoped. The exact positive product-detail
pattern was retrieved, but the generated output still chose the wrong route.
The warm and cold generated files were otherwise byte-identical for this
matrix. This points to journey discovery/candidate availability or model
planning—not missing positive-store data—as the current bottleneck.

## Artifacts

All generated artifacts are intentionally under ignored `scratch/` paths:

```text
scratch/ai059_multi_curated/
  results/baseline_report.json
  results/cold/rag_diagnostics.jsonl
  results/warm-positive/rag_diagnostics.jsonl
  results/cold/reviewed_metrics.json
  results/warm-positive/reviewed_metrics.json
```

The clean single-story diagnostic run is also retained under
`scratch/ai059_generation_clean/` for comparison.

## Decision

- AI-059 harness: **working, with an evidence-integrity gap**.
- Positive retrieval: **confirmed active**.
- Warm-positive improvement: **not observed** (`0.000` delta).
- AI-058 negative learning: **blocked**.
- LangGraph replacement: **not implicated by this run**; the run was linear.

Next session should trace retrieved selectors through page scope and candidate
scoring, capture external pytest assertion failures in evidence, pin server
sampling metadata, and rerun the same matrix. Do not add negative penalties.
