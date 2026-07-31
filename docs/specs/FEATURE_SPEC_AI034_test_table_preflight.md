# AI-034 — Test Table Generation

**Created:** 2026-07-26  
**Updated:** 2026-07-31 (stripped pre-flight — resolver already serves this role)  
**Status:** Draft  
**Branch:** TBD

## Problem

The pipeline generates one skeleton function per condition regardless of how many
distinct test scenarios that condition describes.

**Example:** A Living Test Plan condition like `"filters — A-Z, Z-A, price low-high,
price high-low"` generates **one** skeleton function that tries to test all four
filters. The tester expected **four** separate test functions.

**Root cause:** There's no intermediate expansion layer between conditions (Living
Test Plan) and skeleton code. The skeleton generator treats each condition as atomic.

## Solution

Add a **Test Table** between the Living Test Plan and skeleton generation. The LLM
expands each condition into one or more concrete test rows, giving the tester
visibility into what will be generated and a chance to refine before skeleton
generation.

## Pipeline

```
Requirements → Living Test Plan → Test Table → Skeleton → Resolution
  (user)        (conditions)     (all tests)  (one per  (adapt to site)
                                                row)
```

The resolver already serves as the de facto pre-flight — unresolvable placeholders
produce `pytest.skip()` with diagnostic messages. Resolution failures are surfaced
in the evidence viewer (AI-028) and self-healing loop (Phase 2). No separate
pre-flight pass is needed.

## Phases

### Phase 1: Test Table Data Model

Build `src/test_table.py` with the data model and LLM expansion logic.

**Data model:**
```python
@dataclass
class TestRow:
    id: str  # "T01"
    condition_ref: str  # "TC01.03"
    intent: str  # "Verify Name A-Z produces ascending name order"
    expected_action: str  # "SELECT" | "CLICK" | "FILL" | "ASSERT"
    expected_target: str  # e.g., "sort dropdown, option 'Name A-Z'"
    row_index: int  # display order
```

**LLM expansion:**
- Input: each condition from the Living Test Plan
- Prompt: "This condition describes N distinct test scenarios. Expand into one
  test row per scenario."
- Output: list of `TestRow` objects
- Constraint: max 10 rows per condition (configurable)
- Example: `"filters — A-Z, Z-A, price low-high, price high-low"` → 4 rows

**Editable:** Tester can add, remove, edit, and split rows. Same editorial workflow
as Living Test Plan: AI proposes, human refines, sign off.

### Phase 2: Living Test Plan Enhancement

Add a `tests_count` property to each condition showing how many test rows it
produces. Displayed as a "Tests" column in the Living Test Plan UI.

```
TC01.03  "filters — A-Z, Z-A, price low-high, price high-low"  →  4 tests
TC01.04  "product details visible"                              →  1 test
```

### Phase 3: One Skeleton Per Row

Each confirmed `TestRow` produces exactly one skeleton function with placeholders
that reflect the row's intent and expected action. The existing skeleton generator
(linear or graph) already supports per-condition generation — this phase hooks
the Test Table into that path.

Rows the tester removes or edits don't produce skeletons. Edits flow back
into the Living Test Plan as modified conditions.

## Files Affected

| File | Change |
|------|--------|
| `src/test_table.py` | **NEW** — TestRow dataclass, LLM expansion, CRUD operations |
| `src/test_plan.py` | Add `tests_count` property to conditions |
| `src/ui_pipeline.py` | Wire Test Table into pipeline between LTP and skeleton |
| `streamlit_app.py` | Test Table editor UI (mirrors living test plan pattern) |
| `tests/test_test_table.py` | **NEW** — unit tests (expansion, CRUD, limits) |

## Success Criteria

1. Condition `"filters — 4 types"` produces 4 test rows
2. Condition `"login with valid credentials"` produces 1 test row
3. Tester can add/remove/edit rows before skeleton generation
4. Living Test Plan shows test count per condition
5. One skeleton function generated per confirmed test row
6. No regression when conditions don't need expansion (1 condition → 1 row)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| LLM over-generates test rows | Configurable max (default 10) per condition |
| LLM under-generates (1 row for "4 filters") | Show expansion in UI, tester can split |
| Tester workflow disruption | Mirror Living Test Plan UI pattern — same edit/add/remove flow |
| Skeleton generation per row is slow | Already solved — graph pipeline does per-condition generation efficiently |

## Estimated Sessions

2-3 sessions (data model + expansion, UI + LTP integration, skeleton hook)
