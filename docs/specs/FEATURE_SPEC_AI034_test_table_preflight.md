# AI-034 — Test Table Generation & Pre-Flight Resolution Reporting

**Created:** 2026-07-26
**Status:** Draft
**Branch:** TBD

## Problem

The pipeline produces test skeletons with no intermediate visibility into what tests
will actually be generated and whether they can resolve against the target site.

**Symptom 1 — Conditions don't expand to tests**
A Living Test Plan condition like `"filters — A-Z, Z-A, price low-high, price high-low"`
generates **one** skeleton function that tries to test all four filters in a single test.
The tester expected **four** separate test functions, one per filter.

**Symptom 2 — Resolution failures are silent**
When the resolver can't match a placeholder to the site DOM (e.g., the skeleton expects
a quantity input field but the site uses click-to-add), it silently writes `pytest.skip()`.
The tester discovers this only after the tests are generated and reviewed — too late to
adapt the test plan.

**Root cause:** There is no intermediate layer between the Living Test Plan (conditions)
and skeleton code where the tester can review individual test rows and see which ones
will actually resolve.

## Solution

Add a **Test Table** between the Living Test Plan and skeleton generation, with
**pre-flight resolution reporting** that checks each test row against the scraped DOM
before skeleton code is generated.

## New Pipeline

```
Requirements → Living Test Plan → Test Table → Skeleton → DOM Resolution
  (user)        (conditions)     (all tests)  (intent)   (adapt to site)
                                      ↑
                              Pre-flight check:
                              Can each test row resolve?
                              ⚠ if not — tester decides
```

### Phase 1: Test Table Generation

1. **LLM expands conditions into test rows**
   - Input: each condition from the Living Test Plan
   - LLM analyzes condition text and expected field
   - Output: one or more test row definitions per condition
   - Example: `"filters — 4 filters A-Z, Z-A, price low-high, price high-low"` → 4 rows

2. **Test Table data model**
   - Test ID (e.g., `T01`, `T02`)
   - Parent condition ref (e.g., `TC01.03`)
   - Verification intent: what-are-we-testing (e.g., "Name A-Z produces ascending name order")
   - Expected interaction type (e.g., CLICK, SELECT, FILL)
   - Status: `pending` | `resolved` | `⚠ blocked` | `skipped` | `edited`
   - Resolution note (e.g., "No quantity input on site — click-to-add pattern found")

3. **Editable by tester**
   - Tester can add, remove, edit, and split rows
   - Same editorial workflow as Living Test Plan: AI proposes, human refines, sign off

### Phase 2: Living Test Plan Enhancement

1. **Tests column in Living Test Plan**
   - Shows count of associated test rows per condition
   - e.g., TC01.03 — `"filters"` — **4 tests**

2. **Status propagation**
   - If any test row is ⚠ blocked, the parent condition shows ⚠ in the Living Test Plan

### Phase 3: Pre-Flight Resolution Reporting

1. **Resolver pre-checks each test row**
   - After site scraping, before skeleton generation
   - For each test row: can the intended interaction pattern be found on the site?
   - Example: row expects `FILL:quantity` but site has no `<input type="number">`

2. **⚠ Blocked rows show context**
   - What was expected: `"FILL field for quantity"`
   - What was found: `"6 'Add to cart' buttons, 0 numeric inputs"`
   - Why it can't resolve: `"Site uses click-to-add, no quantity input exists"`

3. **Tester options per ⚠ row**
   - **Skip** — mark as `pytest.skip()` with the reason
   - **Edit** — go back and change the test condition
   - **Run anyway** — generate the test despite expected failure (for bug reproduction evidence)

### Phase 4: Skeleton Generation

1. **One skeleton function per test row**
   - Each row in the Test Table produces one skeleton function
   - Placeholders reflect the verification intent, not hardcoded interaction assumptions

2. **Placeholder improvement**
   - Optional: use more descriptive placeholder types that capture intent
     - `{{CLICK:Add to cart}}` (concrete — resolver finds the button)
     - `{{ASSERT:descending price order}}` (intent — resolver picks the right assertion type)

3. **Pre-resolved rows skip wait**
   - Rows marked `⚠ blocked → skip` don't go through resolution — they emit `pytest.skip()` immediately
   - Rows marked `⚠ blocked → run anyway` go through normal resolution (expected to fail)

## Files Affected

| File | Change |
|------|--------|
| `src/test_table.py` | **NEW** — TestTable data model, LLM expansion, CRUD |
| `src/placeholder_orchestrator.py` | Add pre-flight check before resolution |
| `src/test_plan.py` | Add `tests_count` property per condition |
| `src/ui_pipeline.py` | Wire Test Table into pipeline flow |
| `streamlit_app.py` | Test Table editor UI |
| `tests/test_test_table.py` | **NEW** — unit tests |

## Success Criteria

1. Condition `"filters — 4 types"` produces 4 test rows in the Test Table
2. Tester can add/remove/edit rows
3. Living Test Plan shows test count per condition
4. ⚠ shows when resolver can't match a test row's interaction pattern to the site DOM
5. Tester can choose Skip / Edit / Run anyway for each ⚠ row
6. No regression on existing pipeline for conditions that DO resolve

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| LLM over-generates test rows (10 filters → 40 rows) | Configurable max expansion per condition |
| Pre-flight check slows pipeline | Only run on first resolve; cache results |
| Tester workflow disruption (new step to learn) | Mirror Living Test Plan UI pattern |
| Scope creep (self-healing, auto-adaptation) | Out of scope — only surface the mismatch, don't try to fix it |

## Estimated Sessions

3-4 sessions (one per phase)
