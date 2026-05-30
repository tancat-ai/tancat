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