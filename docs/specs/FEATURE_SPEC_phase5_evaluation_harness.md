# Feature Spec — Phase 5: Automated Evaluation Harness

**Feature ID:** Phase 5
**Created:** 2026-07-13
**Status:** Draft — ready for implementation
**Priority:** High (Tier 3 — Infrastructure)
**Depends on:** AI-012 SQLite Persistence (shipped), AI-011 Run History (shipped)

---

## 1. Problem Statement

With 1300+ tests and a complex resolver pipeline (Pass 1 text, Pass 2 structural, Pass 3 scoring + LLM), prompt changes, model swaps, or resolver tweaks can silently degrade generated test quality. No quantitative quality gate exists to detect regressions before they reach `main`.

The existing `scripts/uat/uat_automationexercise.py` validates two stories against live sites but lacks:
- A frozen, version-controlled dataset with golden answer keys
- Structured metrics (resolution accuracy, false positive rate, etc.)
- Baseline comparison over time
- CI integration as an optional quality gate

---

## 2. Goals

| Goal | Criteria |
|------|----------|
| Frozen dataset | Version-controlled JSON stories with hand-validated golden resolutions |
| Golden answer keys | Each placeholder maps to an expected locator, with tolerance selectors |
| Metric tracking | Resolution accuracy, test pass rate, false positive rate, skeleton completeness |
| Regression comparison | Current run vs. saved baseline in SQLite (`evidence/runs.sqlite`) |
| Human-readable output | Summary report with pass/fail per placeholder, regression alerts |
| CI-friendly | Optional `workflow_dispatch` job — gate, not break |
| Two-track architecture | Track A (sequential pipeline) now; Track B (LangGraph multi-agent) later |
| Reuses existing code | Builds on `scripts/uat/uat_automationexercise.py`, `src/sqlite_persistence.py`, `src/orchestrator.py` |

---

## 3. Non-Goals (MVP)

- Dual-tier (free/paid) support — added when Phase 1 multi-agent exists (Track B)
- RAG integration — deferred to Phase 3
- Real-time dashboards — CLI + console output only
- Local mock site evaluation — deferred, future task

---

## 4. Architecture

### 4.1 Two-Track Design

```
┌───────────────────── eval_harness.py (CLI entry) ─────────────────────┐
│                                                                        │
│  Track A (now)          Track B (Phase 1, later)                      │
│  ┌──────────────┐        ┌─────────────────────┐                      │
│  │ EvalRunner   │        │ LangGraphRunner     │                      │
│  │ (sequential) │        │ (multi-agent)       │                      │
│  └──────┬───────┘        └─────────┬───────────┘                      │
│         │                          │                                  │
│         ▼                          ▼                                  │
│  ┌──────────────┐        ┌─────────────────────┐                      │
│  │ TestOrchestr │        │ AgentPipeline       │                      │
│  │ ator         │        │ (LangGraph state)   │                      │
│  └──────────────┘        └─────────────────────┘                      │
│         │                          │                                  │
│         └──────────┬───────────────┘                                  │
│                    ▼                                                   │
│            ┌──────────────────┐                                       │
│            │ EvalMetrics      │ ← same metrics, both tracks          │
│            │ (comparison)     │                                       │
│            └────────┬─────────┘                                       │
│                     ▼                                                  │
│            ┌──────────────────┐                                       │
│            │ SQLite Store     │ ← baselines + run history             │
│            │ (runs.sqlite)    │                                       │
│            └──────────────────┘                                       │
└────────────────────────────────────────────────────────────────────────┘
```

Both tracks share the same frozen dataset, golden keys, and metrics module. Only the execution engine differs.

### 4.2 Module Layout

```
scripts/eval/
├── eval_harness.py        # CLI entry point (argparse), orchestrates full run
├── eval_runner.py         # Track A: sequential pipeline execution (TestOrchestrator)
├── eval_metrics.py        # Metric computation, baseline comparison, report rendering
├── golden_validator.py    # Validates generated code against golden answer keys
└── dataset/
    ├── eval-001_saucedemo_login.json
    ├── eval-002_saucedemo_checkout.json
    ├── eval-003_automationexercise_browse.json
    ├── eval-004_automationexercise_cart.json
    ├── eval-005_demoqa_forms.json
    ├── eval-006_theinternet_modals.json
    └── ...
```

### 4.3 Golden Answer Key Schema

Each file in `dataset/` is a JSON document:

```jsonc
{
  "id": "eval-001",
  "site": "saucedemo",
  "base_url": "https://www.saucedemo.com",
  "title": "Login and add to cart",
  "user_story": "As a user, I want to log in and add items to my cart...",
  "conditions": [
    "1. Log in with username standard_user and password secret_sauce",
    "2. Add the Sauce Labs Backpack to the cart",
    "3. Click the cart link to view the cart"
  ],
  "golden_resolutions": [
    {
      "criterion_index": 0,
      "placeholders": [
        {
          "action": "FILL",
          "description": "username",
          "expected_locator": "#user-name",
          "tolerance_selectors": ["input[name=\"user-name\"]"],
          "expected_page": "https://www.saucedemo.com"
        },
        {
          "action": "FILL",
          "description": "password",
          "expected_locator": "#password",
          "tolerance_selectors": ["input[name=\"password\"]"],
          "expected_page": "https://www.saucedemo.com"
        },
        {
          "action": "CLICK",
          "description": "login button",
          "expected_locator": "#login-button",
          "tolerance_selectors": [],
          "expected_page": "https://www.saucedemo.com"
        }
      ]
    }
  ],
  "expected_test_count": 3,
  "validated_by": "human",
  "validated_at": "2026-07-13"
}
```

**Field notes:**
- `expected_locator`: CSS selector that should appear in generated code
- `tolerance_selectors`: alternate valid selectors for the same element
- `expected_page`: URL where the element is expected to be found
- `criterion_index`: 0-based index into `conditions[]`

### 4.4 Test Sites

| Site | URL | Purpose |
|------|-----|---------|
| SauceDemo | `https://www.saucedemo.com` | Auth, products, cart, checkout flow |
| AutomationExercise | `https://automationexercise.com` | E-commerce browsing, consent banners, categories |
| DemoQA | `https://demoqa.com` | Form widgets (dropdowns, radios, checkboxes, date pickers) |
| The Internet | `https://the-internet.herokuapp.com` | Structural patterns (modals, iframes, drag-drop) |

All four sites are purpose-built for automation testing — no licensing concerns.

---

## 5. Metrics

### 5.1 Placeholder Resolution Accuracy

```
correct = count(placeholders where generated_locator in [expected_locator, *tolerance_selectors])
accuracy = correct / total_placeholders * 100
```

### 5.2 Generated Test Pass Rate

After running generated tests against the real site via pytest:

```
pass_rate = tests_passed / tests_executed * 100
```

### 5.3 False Positive Rate

Tests that pass but use incorrect locators (resolved to wrong element by chance):

```
false_positives = tests_passed WHERE generated_locator NOT IN [expected_locator, *tolerance_selectors]
false_positive_rate = false_positives / tests_executed * 100
```

### 5.4 Skeleton Generation Completeness

Percentage of user story criteria that produced a skeleton test function with placeholders:

```
completeness = criteria_with_skeleton_functions / total_criteria * 100
```

### 5.5 Generation Duration

Wall-clock time for the full pipeline (skeleton → scrape → resolve → codegen) per story, in seconds.

---

## 6. Implementation Phases

### Phase 1 — Metrics Module (Track A, offline)
- [ ] `scripts/eval/eval_metrics.py` — metric computation functions
- [ ] `scripts/eval/golden_validator.py` — parse generated code, extract locators, compare against golden keys
- [ ] Unit tests for both modules (no browser/LLM needed)
- [ ] Uses regex on generated Python code to extract `evidence_tracker.click(selector)`, `page.locator(selector)`, etc.

### Phase 2 — Golden Dataset
- [ ] Run current pipeline against all four sites (llama.cpp on :8080)
- [ ] Capture generated code and resolution logs
- [ ] Build golden answer key JSON files from captures
- [ ] Human validates each golden key against live site
- [ ] Approved keys committed to `scripts/eval/dataset/`

### Phase 3 — Eval Runner (Track A)
- [ ] `scripts/eval/eval_runner.py` — loads dataset, runs `TestOrchestrator` per story
- [ ] Captures generated code, resolution metadata, and timing
- [ ] Calls `eval_metrics.py` to compute scores
- [ ] Persists results to `evidence/runs.sqlite` via existing `src/sqlite_persistence.py`

### Phase 4 — CLI Harness
- [ ] `scripts/eval/eval_harness.py` — argparse CLI with subcommands:
  - `eval run` — full evaluation run
  - `eval baseline` — save current results as baseline
  - `eval compare` — compare latest run against baseline
  - `eval dataset --validate` — validate golden key JSON schema
- [ ] Console report: per-story table with metrics, regression deltas

### Phase 5 — CI Integration
- [ ] `.github/workflows/eval-harness.yml` — `workflow_dispatch` only (manual trigger)
- [ ] Runs against frozen dataset, saves results as artifact
- [ ] Produces markdown summary of pass-rate vs. baseline
- [ ] Gate (warn) not break — marks PR with annotation but doesn't fail

---

## 7. Integration Points

| Module | Change |
|--------|--------|
| `scripts/uat/uat_automationexercise.py` | Reference only — eval harness is independent, doesn't import UAT |
| `src/sqlite_persistence.py` | Reuse existing API for storing eval run results |
| `src/orchestrator.py` | Called directly by `eval_runner.py` — same `TestOrchestrator` |
| `pyproject.toml` | No new dependencies — all stdlib + existing deps |

---

## 8. Testing Strategy

| Module | Test Type | Coverage |
|--------|-----------|----------|
| `eval_metrics.py` | Unit tests | 100% — pure functions |
| `golden_validator.py` | Unit tests with synthetic code | 100% — regex extraction + comparison |
| `eval_runner.py` | Integration tests with mocks | Pipeline flow, error handling |
| `eval_harness.py` | CLI smoke tests | Subcommand dispatch |

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Eval run is slow (LLM + browser per story) | Medium — blocks quick iteration | `--stories N` flag to run subset; cache LLM responses |
| Golden keys stale after site changes | High — false regressions | Validate golden keys quarterly; version in JSON |
| demoqa.com / the-internet.herokuapp.com downtime | Medium — partial dataset unavailable | Graceful skip with warning; 2/4 sites still valid |
| LLM model unavailable (VRAM contention) | High — can't run | `--dry-run` mode validates dataset without pipeline |

---

## 10. Session Plan

| Session | Scope | Deliverable |
|---------|-------|-------------|
| 1 | Metrics module + golden validator | `eval_metrics.py`, `golden_validator.py`, unit tests |
| 2 | Golden dataset capture + human validation | `dataset/*.json` approved |
| 3 | Eval runner (Track A) + CLI harness | `eval_runner.py`, `eval_harness.py` |
| 4 | CI integration + docs | `.github/workflows/eval-harness.yml`, `scripts/eval/README.md` |

**Estimated total:** 3-4 sessions

---

## 11. Rules

1. One phase per session — per AGENTS.md §10
2. `ruff → mypy → pytest` before marking any phase complete
3. Golden keys validated by human before commit
4. No protected files modified — all new code in `scripts/eval/`
5. Results persisted to `evidence/runs.sqlite` — never to `generated_tests/`

---

*Last updated: 2026-07-13*
