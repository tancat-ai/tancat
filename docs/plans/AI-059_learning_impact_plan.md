# AI-059 — Learning-impact isolation plan

> Plan of record for the metric-first learning experiment. Keep AI-058
> negative-learning code out of this plan until the decision gate passes.

## 0. Decision context

The objective is to measure whether learned positive patterns improve end-to-end
test progress, not whether they match hand-authored golden selectors. The
independent variable is store state only. Every other input must stay fixed:
stories, mock-site revision, generated-input manifest, model, sampling,
pipeline mode, and execution settings.

The primary KPI is:

```text
mean_pass_depth = mean(passed steps before first failure / total planned steps)
```

Corroborating metrics are first-pass green rate, reviewed false-positive rate,
and failure-class counts for locator, assertion, navigation, and infrastructure
or timeout failures.

## 1. Completed — Session 1: extractor and controlled baseline

- Pure analyzer: `src/learning_metrics.py`
- Controlled runner: `src/learning_impact.py`
- CLI: `scripts/eval/learning_impact.py`
- Opt-in RAG JSONL diagnostics
- Store snapshot restoration and SHA-256 recording
- Auto-learning and bundled auto-seed disabled during measurement
- Session record: `docs/sessions/2026-08-27_ai059_session1_controlled_baseline.md`

Result: positive retrieval was active, but warm-positive did not improve the
three-story linear matrix. The exact product-detail positive was retrieved yet
the generated journey still clicked the Products link twice. Several passing
tests were semantically invalid.

## 2. Next session — evidence integrity and resolver trace

### Goal

Make the observed KPI trustworthy and identify why a retrieved positive does
not change the product-detail choice. This is diagnostic/fix work only; no
negative store entries or penalties.

### Deliverables

1. **External assertion evidence**
   - Extend the generated-test evidence hook so a failed `expect(...)` or raw
     pytest assertion records its error/class in the sidecar.
   - Preserve default behavior and keep the field backward-compatible for old
     sidecars.
   - Ensure untracked assertion failures classify as assertion failures rather
     than appearing as a fully green-depth test.

2. **Resolver candidate trace**
   - Extend the existing AI-059 opt-in diagnostic output with current URL/page
     scope, candidate selectors, selected selector, and RAG bonus/eligibility.
   - For the `Product` case, verify whether the retrieved
     `a[href="/product_details.html?id=1"]` is present in the candidate set.
   - If it is absent, fix journey discovery/page scraping or scope plumbing;
     if present but loses, fix scoring only with a focused regression test.

3. **Reproducibility metadata**
   - Capture model server settings that can affect temperature-0 output:
     server seed, top-p, context size, max tokens, and LM Studio slot settings
     when available.
   - Record the mock-site/content hash and story/criteria manifest hash.

4. **Reviewed target envelope**
   - Keep a small checked-in manifest of accepted/invalid test decisions for
     the lab fixture, without committing generated test output.
   - Calculate reviewed false-positive rate consistently for both legs.

### Tests and gates

- Synthetic sidecars for external assertion failures and partial progress
- Resolver unit test where a retrieved product-detail selector is present and
  wins the correct page-scoped candidate
- Backward compatibility for sidecars without the new error fields
- `ruff` → `mypy` → `pytest`
- `scripts/smoke.py`
- eval static gate if resolver/orchestrator scoring changes

### Definition of done

The product-detail failure has a classified sidecar error, the resolver trace
explains whether RAG affected candidate selection, and the same three-story
matrix can be rerun with a non-ceiling, reviewed metric.

## 3. Follow-up — repeated positive A/B

After Session 2:

1. Use the clean site-scoped positive snapshot built only from reviewed
   accepted patterns.
2. Run at least three fixed stories across `linear+cold` and `linear+warm`.
3. Repeat each leg enough times to separate model noise from store effects.
4. Compare raw and reviewed metrics plus retrieval traces.

Interpretation:

- Warm improves reviewed mean depth → positive learning is worth extending;
  design AI-058 negative-memory experiment.
- Warm retrieves but does not improve → investigate descriptions, page scope,
  and scoring; do not add penalties.
- Results vary materially at fixed settings → pin server seed/settings or revise
  the metric before making a product decision.

## 4. Later architecture experiment — AI-060

Only after AI-059 is trustworthy, compare architecture independently from store
warmth:

```text
linear+cold | linear+warm | graph+cold | graph+warm
```

Use LangGraph for orchestration/checkpoint/retry and retain the linear resolver
as a node or shared seam. This is tracked separately as AI-060 and must not be
mixed into the AI-058 decision gate.
