# `src/test_table.py`

## Purpose
Test Table (AI-034) — LLM expansion of Living Test Plan conditions into concrete
test rows. Sits between the Living Test Plan and skeleton generation: each
condition may describe several distinct test scenarios (e.g. "filters — A-Z, Z-A,
price low-high, price high-low" describes four); the LLM expands it into one
`TestRow` per scenario so the tester sees — and can refine — exactly what will be
generated before skeleton code exists. Each confirmed row produces exactly one
skeleton function (Phase 3 hook via `table_to_conditions()`).

## Metadata
- **Lines:** 449
- **Imports:** json, re, dataclasses, collections.abc, typing, src.llm_client, src.spec_analyzer

## Classes
- **`TestRow`** (frozen dataclass): One concrete test scenario expanded from a
  condition. Fields: `id` ("T01"), `condition_ref` ("TC01.03"), `intent`,
  `expected_action` (SELECT|CLICK|FILL|ASSERT|NAVIGATE), `expected_target`,
  `row_index`. `to_dict()` / `from_dict()` round-trip for session-state/editor use.
- **`TestTable`** (frozen dataclass): Tester-reviewable collection of rows with
  CRUD (`add_row`, `remove_row`, `update_row`), confirmation (`confirm`,
  `confirm_condition`), and counting (`rows_for_condition`, `tests_count_for` —
  feeds the LTP "Tests" column).
- **`TestTableExpander`**: LLM expansion engine. `expand_condition()` /
  `expand_conditions()` produce rows via `LLMClient.generate_test` with a
  JSON-schema SYSTEM_PROMPT (fences/trailing-comma/unquoted-key repair included).
  **Resilient by design**: any LLM failure degrades to one deterministic row per
  condition (`single_row_for_condition`) instead of raising — the pipeline never
  breaks because the LLM is down. Hard cap: `DEFAULT_MAX_ROWS_PER_CONDITION = 10`.

## Functions
| Function | Description |
|----------|-------------|
| `normalize_action(raw)` | Normalizes free-text action to a valid `TestAction` literal (aliases: select→SELECT, verify→ASSERT, …) |
| `single_row_for_condition(condition)` | Deterministic 1-row fallback; action inferred from condition intent |
| `table_to_conditions(table, confirmed_only=True)` | Converts (confirmed) rows → `TestCondition`s — one skeleton per row (id=row.id, text=intent+target) |
| `build_table(conditions, expander)` | Expand conditions and build a `TestTable` with sequential row ids |
| `apply_editor_rows(table, rows)` | Returns a table updated from editable table rows (mirrors `test_plan.apply_editor_rows`) |
| `next_row_id(rows, prefix="T")` | Next sequential test row id (T01, T02, …) |

## Dependencies
- `src.llm_client` (LLMClient — provider-agnostic generation)
- `src.spec_analyzer` (TestCondition, infer_condition_intent)

## Consumers
- `src/ui_pipeline.py` — `build_test_table()`, `plan_rows_from_plan(plan, test_table)` (Tests column), `test_table_rows(table)` (editor rows)
- `streamlit_app.py` — 🧪 Test Table editor expander (data_editor + confirm-all)
- `src/cli/pipeline_runner.py` — "Expand into Test Rows" menu flow (`build_test_table_interactive`), `_select_conditions_for_generation()`
- `src/orchestrator.py` / `src/test_generator.py` — via `reviewed_conditions` (rows → conditions feed the per-condition skeleton generator)

## Key Design Decisions
- **LLM-first, deterministic fallback**: expansion is LLM-driven (semantic
  splitting of concerns); the 1-row-per-condition fallback guarantees no
  regression for atomic conditions and no hard failure when the LLM is down.
- **Cap 10 rows/condition** (`DEFAULT_MAX_ROWS_PER_CONDITION`) guards against
  LLM over-generation; tester can merge/split/remove rows in the editors.
- **Confirmed-only generation**: only `confirmed_row_ids` produce skeletons
  (unconfirmed rows skipped); rows removed by the tester simply don't generate.
- **Frozen dataclasses + `__test__ = False`**: immutable value objects that
  pytest does not collect; `replace()`-based immutability like `TestPlan`.
