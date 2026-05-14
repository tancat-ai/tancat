# Session 3: UAT Validation

**UAT Fix Series — Session 3 of 3**  
**Created:** 2026-05-13  
**Depends on:** Session 1 (LLM disambiguation) + Session 2 (ASSERT refinement)  
**No code changes** — execution and measurement only.

---

## Goal

Run the full UAT pipeline against automationexercise.com to measure whether Session 1 and Session 2 improvements increase the test pass rate from the baseline of 4/6.

**Baseline** (from AGENTS.md, documented 2026-05-05):
- **4/6 tests pass** on automationexercise.com
- **test_04 fails**: ASSERT placeholder for "confirmation message" resolves to `.cart_quantity_delete` (delete button) instead of confirmation popup
- **test_06 fails**: Same pattern — ASSERT resolves to wrong element

**Expected after fixes:**
- Session 2 (ASSERT refinement) should make "confirmation message" descriptions more specific → resolver has better input
- Session 1 (LLM disambiguation) should handle any remaining tied candidates → LLM picks correct element
- **Target: 5/6 or 6/6 pass rate**

---

## Execution Steps

### Step 1: Verify prerequisites

```bash
# Confirm Sessions 1 + 2 code is merged and passing
pytest tests/ -v
# All tests green before proceeding
```

### Step 2: Run UAT with LM Studio (avoid GPU VRAM contention)

```bash
# Per AGENTS.md: use LM Studio when Cline is running
.venv\Scripts\python.exe scripts\uat\uat_automationexercise.py --provider lm-studio
```

**Why LM Studio:** Per AGENTS.md §9 — "When running through Cline, use LM Studio with the same model Cline is already using. Loading a second model causes VRAM contention → 500 errors or truncated responses."

### Step 3: Capture results

Save output to `docs/uat_results_post_fixes.md`:

```markdown
# UAT Results — Post UAT Fix Sessions

**Date:** 2026-05-13
**Provider:** lm-studio (qwen3.6-27b)
**Baseline:** 4/6 pass (pre-fix)

## Results

| Test | Status | Notes |
|------|--------|-------|
| test_01 | ✅/❌ | |
| test_02 | ✅/❌ | |
| test_03 | ✅/❌ | |
| test_04 | ✅/❌ | ASSERT confirmation message — was failing |
| test_05 | ✅/❌ | |
| test_06 | ✅/❌ | ASSERT confirmation message — was failing |

## Summary

Pass rate: X/6 (was 4/6)

## Key Observations

- ASSERT refinement: vague descriptions rewritten to specific? (check skeleton output)
- LLM disambiguation: triggered on tied candidates? (check logs)
- Any new failures introduced? (regression check)
```

### Step 4: Analyze failures

If test_04 or test_06 still fail:

1. Check the generated test code — what locator was resolved for the ASSERT?
2. Check the evidence JSON — was the correct element available in the scraped data?
3. Check refinement logs — was the ASSERT description refined? To what?
4. Check disambiguation logs — was there a tie? Did the LLM pick correctly?

This analysis informs whether:
- **Session 2 worked but Session 1 needed**: Description was refined but candidates were still tied → disambiguation should have caught it
- **Session 2 didn't trigger**: Description wasn't detected as vague → refine `is_vague_assert()` patterns
- **New problem**: Different failure mode entirely → document in BACKLOG.md

### Step 5: Update documentation

1. Update `BACKLOG.md` — mark Session 1, 2, 3 as completed with results
2. Update `AGENTS.md` §9 — update "Known results" section with new pass rate
3. If new issues found, add to `BACKLOG.md` Test Generation Quality Fixes section

---

## What to look for in logs

### ASSERT Refinement logs (Session 2)

```
[assert_refiner] Vague ASSERT detected: "button visible"
[assert_refiner] Refined to: "product added to cart confirmation message"
```

If vague ASSERTs are NOT being detected, check `VAGUE_ASSERT_PATTERNS` in `assert_refiner.py`.

### LLM Disambiguation logs (Session 1)

```
[placeholder_resolver] Near-tie detected: top=105, second=102 (threshold=5)
[placeholder_resolver] LLM disambiguation triggered for: CLICK "Products link"
[placeholder_resolver] LLM selected: option 1 (#nav-products-link)
```

If disambiguation is NOT triggering, check `DISAMBIGUATION_THRESHOLD` value.

---

## Rules (from AGENTS.md)

- **One feature per session** — This session is validation only. No code changes.
- **Run end-to-end** — Don't declare improvements done without running the full UAT.
- **Document results** — Save output, update BACKLOG.md.

---

## Files Modified

| File | Change |
|------|--------|
| `docs/uat_results_post_fixes.md` | NEW — UAT results report |
| `BACKLOG.md` | Update session statuses |
| `AGENTS.md` | Update §9 Known results section |

---

## Success Criteria

- UAT pass rate ≥ 5/6 (improvement from 4/6 baseline)
- No regressions — previously passing tests still pass
- All failures documented with root cause analysis
- BACKLOG.md and AGENTS.md updated with results