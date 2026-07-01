# Feature Spec — Phase 5: Automated Evaluation Harness

**Feature ID:** Phase 5
**Created:** 2026-07-01
**Status:** In Progress
**Priority:** High (Tier 3 — Infrastructure)
**Depends on:** AI-012 (SQLite Persistence, shipped), AI-011 (Run History, shipped), existing scripts/uat.py

---

## 1. Problem Statement

Right now, there's no automated way to check if code changes (e.g., prompt updates, resolver tweaks, scraper changes) have regressed the quality of generated tests or placeholder resolution. This means regressions can be introduced accidentally without being noticed!

The existing `scripts/uat.py` is a great starting point, but we need a structured harness that:
- Uses a frozen, version-controlled dataset
- Tracks metrics over time
- Provides clear regression alerts
- Integrates with the existing SQLite persistence layer

---

## 2. Goals

| Goal | Criteria |
|------|----------|
| Frozen dataset | Version-controlled, human-readable dataset of user stories/conditions for 2+ sites |
| Metric tracking | Records placeholder resolution accuracy, test pass rate, generation duration per run |
| Regression comparison | Compares current run against saved SQLite baseline |
| Human-readable output | Clear pass/fail summary, regression alerts |
| CI-friendly | Can be run as a pre-commit check or optional CI job |
| Reuses existing code | Builds on `scripts/uat.py` and `src/sqlite_persistence.py` |

---

## 3. Non-Goals

- Dual‑tier (free/paid) support yet (can add later once we have paid tier architecture)
- RAG integration (deferred to Phase 3)
- Real-time dashboards (keep it simple for MVP)

---

## 4. Architecture

### 4.1 Dataset Storage
- Frozen dataset: `datasets/phase5_frozen.yaml` (YAML for human editability)
- Baseline and run results: `evidence/run_results.sqlite` (reuse existing SQLite DB)

### 4.2 Module Design
New directory: `scripts/eval/`
New script: `scripts/eval/eval_harness.py` (reuses `scripts/uat.py` core logic)

```
├── datasets/
│   └── phase5_frozen.yaml     # Frozen evaluation dataset
└── scripts/
    └── eval/
        └── eval_harness.py    # Evaluation harness entrypoint
```

### 4.3 Metrics to Track
| Metric | Description |
|--------|-------------|
| Placeholder resolution accuracy | % of placeholders that resolve to expected elements |
| Generated test pass rate | % of tests that pass when executed |
| Generation duration | Pipeline runtime per site/story |
| False positives | Tests that pass but have incorrect assertions |
| Skeleton completeness | % of criteria with generated placeholders |

---

## 5. Integration Points
| Module | Change |
|--------|--------|
| `scripts/uat.py` | Extract core logic into reusable functions for `eval_harness.py` |
| `src/sqlite_persistence.py` | No changes needed — reuse existing API |
| `pyproject.toml` | Add `pyyaml` as a dependency for reading frozen dataset |

---

## 6. Implementation Phases

### Phase 1 — MVP (Minimum Viable Product)
- [ ] Add `pyyaml` to pyproject.toml
- [ ] Create `datasets/phase5_frozen.yaml` with existing saucedemo/automationexercise stories
- [ ] Create `scripts/eval/eval_harness.py` that:
  - Loads the frozen dataset
  - Runs pipeline on each story
  - Saves results to SQLite
  - Prints summary
- [ ] Test harness manually

---

## 7. Testing Strategy

- [ ] Unit tests for dataset loading
- [ ] Unit tests for metric calculation
- [ ] Manual end‑to‑end test with both sites

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `pyyaml` adds a dependency | Low | It's a common, lightweight library |
| Harness is too slow | Medium | Limit initial MVP to 2 sites, add parallel runs later |

---

## 9. Dependencies

- **Runtime:** `pyyaml`
- **Build:** `uv sync` to install new dependency
- **Blockers:** None (AI-012 already shipped, SQLite persistence ready)

---

*Last updated: 2026-07-01*
