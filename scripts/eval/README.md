# Evaluation Harness — Usage Guide

## Three evaluation modes, three purposes

The eval harness has **three distinct modes** — use the right one for your question:

| Mode | Command | Tests | Deterministic? |
|------|---------|-------|----------------|
| **static** | `--mode static` | Captured code vs golden keys — **code regression gate** | ✅ Yes |
| **resolver** | `--mode resolver` | Resolution accuracy in isolation — **RAG on/off benchmark** | ✅ Yes |
| **full** | `--mode full` | Static validation + pytest execution — **end-to-end** | ❌ Live sites |

> ⚠️ **`--regenerate`** runs the full pipeline from scratch (LLM → scrape → resolve).
> Results vary run-to-run due to LLM nondeterminism. Use only for E2E pipeline debugging.

---

## Quick Start

```bash
# CI gate — what pre-commit runs (fast, offline, deterministic)
python scripts/eval/eval_harness.py run --mode static --min-accuracy 79 --no-persist

# Resolver benchmark — compare RAG on/off
python scripts/eval/eval_resolver.py --mode static
RAG_ENABLED=1 python scripts/eval/eval_resolver.py --mode static

# Full E2E — needs running servers
python scripts/eval/eval_harness.py run --mode full

# AI-059: read-only learning-impact metrics from existing sidecars
python scripts/eval/learning_impact.py metrics --evidence-dir evidence

# Save / compare baseline
python scripts/eval/eval_harness.py baseline --save
python scripts/eval/eval_harness.py compare

# Validate golden keys
python scripts/eval/eval_harness.py dataset --validate
```

---

## AI-059 Learning-Impact Harness

`learning_impact.py metrics` computes golden-free metrics from evidence sidecars:
`mean_pass_depth`, `first_pass_green_rate`, `false_positive_rate`, and the
locator/assertion/navigation/infrastructure-timeout breakdown. Ratios are
`0.0..1.0`; false positives require an explicit manual-review annotation.

The `baseline` command runs one fixed command per store leg (cold,
`warm-positive`, and optionally `warm-positive-negative`), restores each
snapshot first, disables auto-learning with `AI059_DISABLE_AUTO_LEARN=1`, and
writes independent `metrics.json` files plus `baseline_report.json`. Optional
CLI metadata flags record pipeline/mode/provider/model/temperature/thinking. Each leg
also records opt-in retrieval details in `rag_diagnostics.jsonl`. RAG reads
remain enabled for warm legs. Use deterministic mock-site commands and have
the fixture honor `AI059_EVIDENCE_DIR` (or use the `{evidence_dir}` token) to
route sidecars to the current leg.

### Negative-learning A/B tooling (AI-058 / AI-063 / AI-064)

The contrastive learned-store work (record `learned_negative` entries, apply a
step-scoped penalty at resolve time) is measured by deterministic drivers that
**do not touch the eval gate or any committed dataset**:

| Script | Purpose | Isolation |
|--------|---------|-----------|
| `scripts/ai058_ab_mock_run.py` | Live 3-leg cold/warm/warm+neg A/B against a real mock | Own temp dir + `AITEST_STORAGE_ROOT`, auto-learn off |
| `scripts/ai058_seeded_ab.py` | Seed ONE known negative into a temp store; verify round-trip + step-scoped score | Same hermetic discipline |
| `scripts/ai058_resolver_ab.py` | **Deterministic** resolver flip on the frozen `scraped_pages/` pool (no LLM, no mock server) — the strongest proof | Reads gitignored `scraped_pages/`; skips cleanly if absent (CI) |

Key finding (2026-08-29): the step-scoped negative is proven at the scorer and
resolver level (wrong pick down-weighted on its own step, never leaks to other
steps), but a *generation-level* `mean_pass_depth` lift cannot be forced on any
clean mock — the observed-trail page scoping (AI-052) plus container/prose
penalties (AI-064) make the resolver pick the correct element before the
negative ever matters, except in the historical cross-page context where the
correct page wasn't in the pool. See `docs/sessions/2026-08-29_ai058_slice2_negatives_handoff.md` §8.

---

## Mode: `static` — CI Regression Gate

**Purpose:** Catch code changes that break parsing, extraction, or captured output format.
**Runs:** Fast (<2s). No browser, no LLM, no scraping.

Validates pre-captured pipeline outputs (`scripts/eval/captures/*_code.py`) against golden
answer keys. If your code change breaks locator extraction, skeleton parsing, or evidence
tracker format, this catches it immediately.

```bash
python scripts/eval/eval_harness.py run --mode static --min-accuracy 79
```

**When to run:** Every commit (pre-commit hook). Never skip this.

---

## Mode: `resolver` — Resolution Accuracy (RAG Benchmark)

**Purpose:** Measure how accurately the resolver picks locators from scraped elements.
Isolates resolution from LLM skeleton generation.

Uses pre-scraped page data (`scripts/eval/scraped_pages/*.json`) and golden key
placeholder descriptions. Supports RAG on/off comparison:

```bash
# Baseline (RAG off)
python scripts/eval/eval_resolver.py --mode static

# With RAG
RAG_ENABLED=1 python scripts/eval/eval_resolver.py --mode static

# Refresh scraped page data (run on first use or when sites change)
python scripts/eval/eval_resolver.py --mode live
```

**When to run:**
- Testing RAG effectiveness
- Changing resolver/scorer logic
- Validating new golden keys against actual resolver behavior

> ⚠️ `scraped_pages/` is **gitignored** — these dumps are generated locally.
> In CI they are absent, so tests/scripts that read them must skip cleanly
> when missing (e.g. `scripts/ai058_resolver_ab.py`).

---

## Mode: `full` — Full E2E Validation

**Purpose:** Validate resolution accuracy AND execute generated tests against live sites.

```bash
python scripts/eval/eval_harness.py run --mode full
```

**When to run:** Before releases, after major pipeline changes. Requires live demo sites.

---

## Architecture

```
eval_harness.py (CLI entry point)
├── mode: static → eval_runner.py (load captured code → validate_dataset)
├── mode: resolver → eval_resolver.py (golden descriptions + scraped data → scorer)
└── mode: full → eval_runner.py (static validation + pytest execution)

eval_resolver.py (resolution-only, for RAG comparison)
  ├── Loads golden key placeholders (dataset/)
  ├── Loads pre-scraped page data (scraped_pages/)
  └── Calls ElementMatcher + PlaceholderScorer directly

eval_runner.py (orchestration)
  ├── golden_validator.py (parse code, match locators)
  ├── eval_metrics.py (compute metrics, render reports)
  └── SQLite eval_runs table (persistence)
```

---

## Golden Answer Keys

Stored in `scripts/eval/dataset/*.json`. Each file contains:
- User story and conditions
- Golden resolutions (expected locators with tolerance selectors)

**Adding a new story:**
1. Run the pipeline against the target site
2. Capture generated code in `scripts/eval/captures/`
3. Hand-validate each locator against the live site
4. Write golden key JSON in `scripts/eval/dataset/`
5. Run `python scripts/eval/eval_harness.py dataset --validate`
6. Scrape pages: `python scripts/eval/eval_resolver.py --mode live`

> ⚠️ A new JSON in `dataset/` is globbed by the static gate — it needs a
> matching captured-code file, or the aggregate drops. Keep throwaway A/B
> stories OUT of this directory (inline them in the driver script instead).

---

## Metrics

| Metric | Formula |
|--------|---------|
| Resolution accuracy | correct_placeholders / total_placeholders × 100 |
| Test pass rate | tests_passed / tests_executed × 100 |
| False positive rate | wrong_locator_passes / tests_executed × 100 |
| Skeleton completeness | criteria_with_skeletons / total_criteria × 100 |

---

## CI Integration

- **Pre-commit hook:** `eval-accuracy` runs `--mode static --min-accuracy 79 --no-persist`
- **GitHub Actions:** `eval-harness.yml` runs on `workflow_dispatch` (manual trigger)

---

## Current Baseline

| Metric | Value |
|--------|-------|
| Stories | 8 |
| Placeholders | 96 |
| Resolution accuracy (static — CI gate) | **97.9%** (94/96) |

Per-story (static, RAG-off frozen dumps): saucedemo 20/20, automationexercise 8/8,
demoqa 8/8, theinternet 7/7, lv_insurance 24/24, ecommerce 14/16 (88%), banking 13/13,
banking-eval-008 0/0 (no captured code → counted as 0).

Baseline file: `scripts/eval/baseline.json`

To refresh scraped data: `python scripts/eval/eval_resolver.py --mode pipeline`

---

## Model Baseline Comparison (before/after fine-tuning)

Diff two `eval_model_baseline.py` outputs in one command — the runbook §6
workflow (capture baseline → train → re-capture → compare):

```bash
# after training + model swap, re-capture the 'after' baseline
python scripts/eval/eval_model_baseline.py --save training_data/model_baseline_finetuned.json

# compare (auto-discovers the two model_baseline_*.json files; older = before)
python scripts/eval/compare_model_baselines.py

# explicit paths + machine-readable output
python scripts/eval/compare_model_baselines.py --before A.json --after B.json --json
```

- Matches stories by `story_head`, so regressions/improvements are attributed
  per story, not just as aggregate rates.
- Exit codes: `0` = no regressions, `2` = regressions detected (same
  convention as the eval-harness quality gate), `1` = usage/IO error.
- Aggregates: valid-skeleton rate, criteria-cover rate, hallucinated-login
  rate, skip lines, placeholders, LLM errors.