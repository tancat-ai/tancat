# AI-037 — LV Insurance Resolution Gap Optimization

**Created:** 2026-07-30
**Status:** Scoping
**Priority:** Medium (Tier 2 — Resolver Accuracy)
**Depends on:** None (standalone, but complements AI-031 resolver improvements & B-016 synonym matching)
**Roadmap ref:** Tier 2 — Feature Completion (standalone optimisation sprint)

---

## 1. Problem Statement

After the SPA scraper fix (`_reveal_hidden_sections()` in `journey_scraper.py`), LV Insurance resolution jumped from 0% → 54% (linear) / 50% (graph). **46% of placeholders still fail to resolve** — 11 of 24 golden keys return `pytest.skip()`.

The symptom is **description-to-element mismatch**: the skeleton generator says "vehicle registration number" but the DOM element is `#vehicleReg` with label "Registration Number". The resolver's token-matching pipeline cannot bridge this gap.

### Current LV Insurance Scores

| Pipeline | Score | Status |
|----------|-------|--------|
| Static eval (pre-generated) | 100% | ✅ Reference |
| Linear regeneration + RAG | 54% (13/24) | ⚠️ 11 unresolved |
| Graph regeneration + RAG | 50% (12/24) | ⚠️ 12 unresolved |

---

## 2. Diagnostic Analysis (Required)

Before any fix, the first deliverable is a **diagnostic run** that classifies each of the 11 failing placeholders into one of:

| Category | Description | Example |
|----------|-------------|---------|
| **Synonym gap** | Element label exists but token expansion doesn't bridge it | skeleton: "registration" → DOM: "Reg" (short for Registration) |
| **Description mismatch** | Skeleton description uses different phrasing than DOM label | skeleton: "cover start date" → label: "Cover Start Date" (should work — check case/stemming) |
| **Scraper blind spot** | Element exists but scraper doesn't capture it | Hidden aria content, JS-rendered elements |
| **Scoring underflow** | Correct element exists and is captured but scores below threshold | Low structural similarity because ID is short |
| **Page not found** | Element is on a page the journey scraper never reached | SPA section toggle not triggered during journey |

**Tool:** `scripts/debug.py resolve <url> --desc "..."` per failing placeholder, or use `scripts/eval/eval_harness.py run --mode static --site lv_insurance --verbose` with detailed logging.

---

## 3. Product Goals

### 3.1 "Make the resolver smarter about insurance vocabulary"

The current `TOKEN_EXPANSIONS` map in `src/semantic_matcher.py` is heavily biased toward e-commerce vocabulary (cart, basket, checkout, product, add to cart). Insurance-specific terms are missing:

| Term | Missing expansions |
|------|-------------------|
| registration | reg, vehicle reg, VRN, number plate |
| license | licence, driving licence, DL, driver's license |
| occupation | job, employment, profession, role |
| scheme | plan, policy type, cover type |
| start date | cover start, effective date, inception date |
| premium | price, cost, annual premium, quote amount |
| excess | deductible, excess amount, compulsory excess |
| overnight | parking, stored, kept overnight, garaged |
| NCD | no claims discount, no claims bonus, NCB |
| usage | use, mileage, driving purpose, SDP |

### 3.2 "Don't break existing sites"

All fixes must be evaluated against the full eval harness (5 sites, 67 placeholders). No regression below current 100% static / 56.7% regeneration baseline.

### 3.3 "Make the gap measurable"

The diagnostic output should be a structured report (JSON or markdown) that can be tracked across sessions:
- Per-placeholder: status, best candidate score, candidate element, failure reason
- Aggregate: category counts, overall score
- Re-run after each fix to measure improvement

---

## 4. Proposed Approach

### Phase 1: Diagnostic (1 session)

1. **Run verbose resolution** on LV Insurance failing placeholders — capture which elements were candidates, their scores, and why the correct element lost
2. **Classify each failure** into the 5 categories above
3. **Produce a report** (`docs/analysis/lv_insurance_gap_diagnosis.md`)

### Phase 2: Token Expansion (0.5 session)

1. Add insurance-specific terms to `TOKEN_EXPANSIONS` in `src/semantic_matcher.py`
2. Add `_split_camel_case` expansions for IDs like `#vehicleReg` → "vehicle Reg" → "vehicle registration"
3. Re-run LV Insurance eval — measure improvement

### Phase 3: Description Cleanup (0.5 session, if needed)

1. Update skeleton prompt to prefer DOM-aligned descriptions (e.g., "registration number" instead of "vehicle registration number")
2. Or add a post-processing step that normalises skeleton descriptions to match observed DOM patterns

### Phase 4: Scoring Tuning (0.5 session, if needed)

1. If scoring underflow is detected, adjust thresholds or bonuses for insurance-specific patterns
2. If wrong-element wins (false positive), add penalty for mismatched types

**Total estimated sessions:** 1-2

---

## 5. Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| LV Insurance linear resolution | 54% | ≥80% (19/24) |
| LV Insurance graph resolution | 50% | ≥75% (18/24) |
| Static eval (all 5 sites) | 100% | 100% (no regression) |
| Overall linear regeneration | 56.7% | ≥65% |

---

## 6. Files to Modify

| File | Change | Risk |
|------|--------|------|
| `src/semantic_matcher.py` | Add insurance TOKEN_EXPANSIONS | Low — isolated data change |
| `src/semantic_matcher.py` | `_split_camel_case` integration in `get_words()` | Low — pure expansion |
| `src/prompt_utils.py` | Optional: ASSERT specificity guidance | Medium — affects all sites |
| `src/placeholder_scorers.py` | Optional: insurance-specific bonuses | Low-Medium — layered scoring |
| `tests/test_semantic_matcher.py` | New tests for insurance expansions | Low |

---

## 7. Evaluation

```bash
# Before fix: establish baseline
uv run python scripts/eval/eval_harness.py run --mode static --save

# After fix: measure LV Insurance improvement
uv run python scripts/eval/eval_harness.py run --mode static --site lv_insurance --verbose

# Full regression check
uv run python scripts/eval/eval_harness.py run --mode static
uv run python scripts/eval/eval_harness.py compare

# Full regeneration (needs LLM running)
LANGGRAPH_ENABLED=0 RAG_ENABLED=1 uv run python scripts/eval/eval_harness.py run --regenerate --mode full
```

---

## 8. Related References

- **BACKLOG.md B-016** — Synonym-aware matching (foundation for Phase 2)
- **BACKLOG.md AI-031** — Resolver accuracy improvement sprint (previous LV work)
- **BACKLOG.md AI-030** — LV Insurance mock site & eval dataset
- **docs/sessions/2026-07-30_handover.md** — "LV Insurance Resolution Gap (46% unresolved)" section
- **docs/sessions/2026-07-30_scraper_fix_and_pipeline_performance.md** — Open Issues §5
- **scripts/eval/dataset/eval-005_lv_insurance_quote.json** — Golden keys (24 placeholders)
- **generated_tests/mock_insurance_site.html** — 7-step SPA mock site