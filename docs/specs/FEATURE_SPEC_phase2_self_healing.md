# Feature Spec — Phase 2 Self-Healing Reflection Loops

**Created:** 2026-07-20
**Status:** Complete — Core loop + Streamlit + CLI shipped 2026-07-20
**Priority:** Medium (portfolio) — "Self-healing AI automation" marketing message
**Depends on:** `src/failure_classifier.py`, `src/pytest_output_parser.py`, `src/llm_client.py`
**Roadmap ref:** Phase 2, Tier 4

---

## 1. Problem Statement

When generated tests fail, the user must manually diagnose and fix each failure.
The tool already generates tests, but doesn't close the loop: if a generated
locator is wrong, the test just fails with no automatic recovery.

The existing `locator_repair.py` requires a human to open a headed browser and
click the correct element (interactive codegen). This is useful but doesn't
scale — a batch of 50 tests with 5 failures still requires manual intervention.

## 2. Solution: Automated Self-Healing Loop

### Core Loop

```
run_tests() → parse_output() → classify_failures()
  → for each fixable failure:
      → feed failure context to LLM reviewer
      → get suggested code patch
      → apply patch to test file
  → re-run failed tests
  → repeat until max_iterations or all pass
```

### What the LLM reviewer receives

For each failed test, the reviewer gets:
1. The test function source code
2. The error message (from pytest)
3. The scraped page data (element list) for the URL where it failed
4. The previous test run's results (for context)

### What the LLM reviewer returns

A JSON patch with:
- `fixable`: boolean — whether this failure can be auto-fixed
- `diagnosis`: string — what went wrong
- `action`: "replace_locator" | "add_navigation" | "add_wait" | "skip_test" | "none"
- `patch`: the exact code replacement (old_text → new_text) or null

### Fix Strategies

| Failure Category | Strategy | Example |
|---|---|---|
| `locator_timeout` | Replace locator with a more robust one from scraped data | `.click('#old-btn')` → `.click('[data-test="submit"]')` |
| `strict_violation` | Add `.first` to locator or use more specific selector | `get_by_label("Name")` → `page.locator("#firstName")` |
| `assertion_failure` | Replace with correct expected value or skip | `to_have_text("Wrong")` → `to_have_text("Correct")` |
| `navigation_error` | Add explicit `page.goto()` before the failing step | Insert navigation step |

### Non-Fixable Cases

- Logic errors (test reaches wrong page due to missing prerequisite steps)
- Site is down or unreachable
- Authentication failures
- Tests that pass inconsistently (flaky due to timing)

---

## 3. Implementation Plan

### Phase 2a — Core Automated Loop (this session)

**`src/self_healing.py`** — new module:

```python
class SelfHealingRunner:
    def __init__(self, llm_client, max_iterations=3)
    async def heal(test_file: str | Path) -> HealingReport
```

**HealingReport** dataclass:
- `total_failures: int` — initial failure count
- `fixed: int` — how many were fixed
- `remaining: int` — still failing after max iterations
- `iterations: int` — how many loops ran
- `patches: list[AppliedPatch]` — what was changed

**Loop internals:**
1. `_run_pytest(test_file, test_names=None)` → `RunResult`
2. `_classify_failures(run_result)` → `list[ClassifiedFailure]`
3. `_build_reviewer_prompt(failure, test_source, scraped_data)` → prompt string
4. `_get_reviewer_response(prompt)` → `ReviewerResponse`
5. `_apply_patch(test_file, patch)` → bool
6. Loop until no fixable failures or max iterations

**Integration:**
- `streamlit_app.py`: "🩹 Self-Heal Failed Tests" button in test results
- `src/ui/ui_run_results.py`: `_render_self_healing_results()` — metrics + diff display
- `src/cli/pipeline_runner.py`: `self_heal_cli()` — menu-driven CLI integration
- `src/cli/main.py`: "Self-Heal Failed Tests" menu item

**Tests:** `tests/test_self_healing.py` — 15+ unit tests for classification, prompt building, patch application

### Phase 2b — Interactive Repair Merge (future session)

Merge automated self-healing with existing interactive codegen locator repair.
When automated repair fails, offer the interactive repair as fallback.

---

## 4. Files Changed

| File | Change |
|---|---|
| `src/self_healing.py` | **New** — SelfHealingRunner, HealingReport, repair strategies |
| `src/ui/ui_run_results.py` | Healing results display |
| `streamlit_app.py` | Self-heal button integration |
| `tests/test_self_healing.py` | **New** — unit tests |

## 5. Acceptance Criteria

1. `SelfHealingRunner.heal()` runs pytest, classifies failures, applies LLM-suggested fixes, re-runs
2. Max iterations ceiling enforced (default 3)
3. Non-fixable failures are reported as remaining, not stuck in infinite loop
4. Each patch is logged with before/after code diff
5. Healing report shows: failures → fixed → remaining → patches applied
6. All existing tests pass (ruff clean, mypy clean, pytest zero regressions)

---

*Last updated: 2026-07-20*
