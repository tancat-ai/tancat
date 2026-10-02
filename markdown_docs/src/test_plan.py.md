# `src/test_plan.py`

## Purpose
Living test plan models and helpers for tester review/sign-off before test generation.

## Metadata
- **Lines:** 217
- **Imports:** dataclasses, datetime, src.spec_analyzer

## Classes
- **`TestPlan`** (frozen dataclass): Tester-reviewed plan of conditions. Supports confirm/remove/add/sign-off of conditions.

## Functions
| Function | Description |
|----------|-------------|
| `build_story_ref(user_story)` | Derives stable story ref slug from user-story text |
| `next_condition_id(existing, prefix)` | Returns next sequential condition id (e.g., MAN01) |
| `build_manual_condition(...)` | Creates tester-authored condition with stable id |
| `apply_editor_rows(plan, rows)` | Updates plan from editable table rows |

## Dependencies
- `src.spec_analyzer` (TestCondition, ConditionIntent, infer_condition_intent)

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `TestPlan.to_dict` (method of `TestPlan`): `TestPlan.to_dict() -> dict[str, object]` - Return a JSON/session-state friendly representation.
- `TestPlan.from_conditions` (method of `TestPlan`): `TestPlan.from_conditions(*, story_ref: str, sprint: str, conditions: list[TestCondition]) -> TestPlan` - Create a plan from analyzed conditions.
- `TestPlan.condition_ids` (method of `TestPlan`): `TestPlan.condition_ids() -> set[str]` - Return all condition ids currently in the plan.
- `TestPlan.reviewed_ids` (method of `TestPlan`): `TestPlan.reviewed_ids() -> set[str]` - Return confirmed ids that still exist in the plan.
- `TestPlan.unreviewed_ids` (method of `TestPlan`): `TestPlan.unreviewed_ids() -> set[str]` - Return condition ids that still need explicit confirmation.
- `TestPlan.is_ready_for_generation` (method of `TestPlan`): `TestPlan.is_ready_for_generation() -> bool` - Return True when all conditions are reviewed and sign-off is complete.
- `TestPlan.replace_condition` (method of `TestPlan`): `TestPlan.replace_condition(condition_id: str, updated_condition: TestCondition) -> TestPlan` - Replace one condition by id.
- `TestPlan.remove_condition` (method of `TestPlan`): `TestPlan.remove_condition(condition_id: str) -> TestPlan` - Remove one condition and any stale confirmation entry.
- `TestPlan.add_condition` (method of `TestPlan`): `TestPlan.add_condition(condition: TestCondition, *, confirmed: bool = False) -> TestPlan` - Append a new condition to the plan.
- `TestPlan.sign_off` (method of `TestPlan`): `TestPlan.sign_off(*, tester_name: str, sign_off_notes: str = '', sign_off_date: str | None = None) -> TestPlan` - Apply tester sign-off metadata.
