# `src/prerequisite_injector.py`

## High-Level Purpose
Injects prerequisite setup code (fixtures, page navigation, auth state) into generated test functions before test body execution.

## Module Metadata
- **Lines:** ~180
- **Imports:** `re`, `dataclasses`, `typing`

## Classes

### `Prerequisite` (dataclass)
Single prerequisite block: type (goto, login, setup), code snippet, insert position.

## Functions

### `inject_prerequisites(code: str, prerequisites: list[Prerequisite]) -> str`
Injects prerequisite code blocks before test function body.

### `infer_prerequisites(story: UserStory) -> list[Prerequisite]`
Infers required prerequisites from user story (e.g., login before checkout).

### `_format_goto(url: str) -> str`
Generates `page.goto(url)` prerequisite line.

### `_format_login(credentials: dict) -> str`
Generates login prerequisite block.

## Key Design Decisions
- Prerequisite inference from story context, not manual config
- Insertion before first test assertion to preserve setup order
- No modification of test function signature

## Dependencies
- None from `src/` — stdlib only