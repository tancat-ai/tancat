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

## Evidence and the cheap re-score (B-093)

A held-out run is expensive (LLM + scrape + pytest against live sites). Its
**evidence** must survive so the score can be recomputed without another run.

```bash
# 1. Run, and keep the evidence in one known place.
python scripts/eval/eval_harness.py run --regenerate --mode full \
  --evidence-dir scratch/eval_runs/2026-09-30_heldout

# 2. Re-score from that evidence: no model, no browser, no live site.
python scripts/eval/rescore.py --run-dir scratch/eval_runs/2026-09-30_heldout \
  --expect-gate1 82 --expect-gate2 3
```

The evidence directory holds:

| Item | What it is |
|---|---|
| `manifest.json` | metadata + the gate numbers this run recorded |
| `results.json` | the per-placeholder result (`HarnessReport.to_dict`) |
| `emitted/test_eval-001.py` | the emitted test files, one per story |
| `junit/test_eval-001.xml` | the per-test outcomes (pytest `--junitxml`) |
| `pytest/test_eval-001.log` | the raw pytest output, one per story |
| `verification_strength.json` | the product's per-test verdicts (may be absent) |

`rescore.py` recomputes gate 1 statically (emitted code vs golden keys) and
re-applies gate 2 to the kept per-test outcomes, using the same
`eval_metrics.count_false_greens` rule a live run uses. Exit codes: `0` scored,
`2` a number did not match `--expect-*`, `5` evidence missing (the score
**cannot** be recomputed - it is never read as a zero).

The harness exits `4` when a run with `--evidence-dir` fails to keep its
evidence, distinct from `2` (accuracy below threshold) and `3` (partial run).

The last recorded re-score is `scripts/eval/known_gate_scores.json`:
**82/113 gate 1 (72.6%)** and **3 hollow passes**. The run that produced it was
deleted, so the next live held-out run must reproduce it, or explain the
difference. The gates are unchanged: `>=90%` gate 1, zero hollow passes gate 2.

---

## The verification basis, persisted (B-093)

A pass without its basis is what hid the hollow passes once. Every persisted
run now stores, per criterion placeholder, **what its own test verified
against**: the golden locator, a distinctive element, a page arrival, or
nothing. No new database and no parallel pipeline: the `eval_criteria` table
and its three indexes - on `identity` (the compare lookup), `story_id` (the
rollup filter) and `run_id` (loading one run, and the `ON DELETE CASCADE`) -
live beside `eval_runs` in the same SQLite file
(`evidence/run_results.sqlite`).

```bash
# The run that produced a gate number persists it (the harness does this by
# default; --no-persist opts out). Rebuild a row from kept evidence instead:
python scripts/eval/eval_harness.py rebuild --evidence-dir scratch/eval_runs/heldout

# One rollup: per story, per site, over time, plus the miss classes with counts.
python scripts/eval/eval_harness.py report --story eval-007

# Compare the latest two persisted runs by criterion identity.
python scripts/eval/eval_harness.py compare --story eval-007
```

| Item | What it holds |
|---|---|
| `eval_runs.verified_by_element` | golden + element verdict (queryable, no JSON) |
| `eval_runs.verified_by_page` | page-arrival verdicts |
| `eval_runs.unverified` | assertions that proved nothing |
| `eval_criteria` | one row per criterion **placeholder** (a criterion with several placeholders writes several rows): story, criterion id, stable `identity` (story + criterion + placeholder slug), placeholder, page, golden locator, resolved locator, matched, verification, outcome, miss class |

A criterion's `identity` is `story#c<index>#<slug>`. The description is slugged
to `[a-z0-9_]` and truncated to **48 characters**, so two placeholders that
share their first 48 slug characters collide, and editing a placeholder inside
those 48 characters makes the criterion read as new in `compare`.

**Failed, defined once.** A criterion is failed when its golden locator did not
match, or when its own test did not pass (`FAILED`, `ERROR` or `SKIPPED`);
everything else passed. The rollup (`FAILED CRITERIA`, `PASSES BY BASIS`) and
`compare` both use this one definition.

The miss classes (`eval_criteria.miss_class`) are `target_never_captured`,
`page_context_misassigned`, `weakened_to_visible_element`,
`element_instead_of_page_arrival`, `golden_weaker_than_generated` and
`wrong_element`; `eval_criteria.MISS_FIX_HINT` names what a fix would change.
`page_context_misassigned` needs the page a locator was resolved from, which
the harness does not record yet - it is never guessed.

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

**Golden specificity rule (narrower-than-story):** A golden must match what the story fixes,
no more and no less. When a step names a specific target - "add the Sauce Labs Backpack",
"the Male radio", "pay a bill" - the golden may name that element's selector. When the story
leaves the choice open ("add an item", "a product (e.g. Blue Top)", "a radio option (e.g.
Male)", "select an item"), the golden must assert a property of the outcome instead of one
interchangeable element: an item row is present, the cart badge count increased, a confirmation
message appeared. Where the harness cannot express that property as a selector match, the
criterion must be reworded to fix the choice, so the golden and the criterion agree. A specific
golden for an open choice is a false-negative trap: it fails a correct test that made a
different valid choice, and it inflates gate 1 only on the draw that happened to pick the named
element.

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
| Resolution accuracy (static — CI gate) | **94.8%** (91/96) |

Per-story (static, RAG-off frozen dumps): saucedemo 18/20, automationexercise 7/8,
demoqa 8/8, theinternet 7/7, lv_insurance 24/24, ecommerce 14/16 (88%), banking 13/13,
banking-eval-008 0/0 (no captured code → counted as 0).

The static figure fell from 97.9% (94/96) to 94.8% (91/96) after three goldens
were corrected to name what their criterion means (B-101). The eval-001 goldens for
"backpack item in cart" (c3) and "Thank You page" (c5) were strengthened, and the
eval-002 "add to cart confirmation" (c3) primary was changed from the arbitrary
`[data-product-id="11"]` container to the confirmation message (`.text-center`).
The frozen captures still emit the old locators - `scripts/eval/captures/saucedemo_code.py`
holds `.cart_list[data-test="cart-list"]` and `[data-test="title"]`, and
`scripts/eval/captures/automationexercise_code.py` holds `[data-product-id="11"]` -
so those three criteria no longer match. This is the same stale-capture effect in
every case: the figures recover when the captures are regenerated. The **live held-out
gate is the one that improves** (+2 on both kept runs: 81/113 -> 83/113 and
85/113 -> 87/113).

Baseline file: `scripts/eval/baseline.json` (refreshed from a static run against the
corrected goldens).

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