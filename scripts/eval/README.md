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

# Save baseline
python scripts/eval/eval_harness.py baseline --save

# Compare current vs baseline
python scripts/eval/eval_harness.py compare

# Validate golden keys
python scripts/eval/eval_harness.py dataset --validate
```

---

## Mode: `static` — CI Regression Gate

**Purpose:** Catch code changes that break parsing, extraction, or captured output format.
**Runs:** Fast (<1s). No browser, no LLM, no scraping.

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

## Current Baseline (stateful scraped data)

| Metric | Value |
|--------|-------|
| Stories | 4 |
| Placeholders | 43 |
| Resolution accuracy (CI gate, captured code) | 81.4% |
| Resolution accuracy (resolver, RAG off) | 41.9% |
| Resolution accuracy (resolver, RAG on) | **53.5%** |
| RAG improvement | **+11.6pp** |
| Skeleton completeness | 100.0% |

### Per-site breakdown (resolver, RAG on vs off)

| Site | RAG off | RAG on | Δ |
|------|---------|--------|---|
| saucedemo | 45.0% | 55.0% | +10.0pp |
| automationexercise | 25.0% | 37.5% | +12.5pp |
| demoqa | 62.5% | 75.0% | +12.5pp |
| theinternet | 28.6% | 42.9% | +14.3pp |

Baseline file: `scripts/eval/baseline.json`

To refresh scraped data: `python scripts/eval/eval_resolver.py --mode pipeline`
