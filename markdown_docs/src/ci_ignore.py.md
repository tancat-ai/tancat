# `src/ci_ignore.py`

## High-Level Purpose

The CI ignore list (`.ai-test-ignore.yml`) — a **versioned, human-recorded**
list of *known-benign* test failures for the Phase 7 CI/CD integration. When
a test fails in CI for a reason a human has already accepted ("the button
moved but still works", "known flaky in this environment"), the report
surfaces it as **"N known-benign ignored"** instead of a real failure.

This module parses + validates that file. It exists so CI fails *loudly* on
a malformed ignore file (never silently ignore the wrong things), and so the
"this failure is acceptable" decision lives in git — visible, reviewable,
versioned — instead of in hidden `@pytest.mark.skip` markers, commented-out
tests, or silent self-healing patches (the mechanisms this file exists to
replace).

**The anti-rug rule:** every ignore rule **requires a `reason`**. A rule
without a recorded "why" is the rug-sweeping shape and is rejected at parse
time — the ignore list must never be how a real failure gets hidden.

```yaml
# .ai-test-ignore.yml
ignores:
  - test: "test_08_checkout*"
    reason: "button moved to new class, verified still functional 2026-08-14"
    match: "Locator '.*' not found"   # optional regex on the failure message
```

## Public API

### `load_ignore_spec(path: str | Path | None) -> IgnoreSpec`

Load and validate the ignore file.

- **`path`** — file path, or `None` (empty spec — no ignores).
- **Returns** an `IgnoreSpec` (empty when `path is None`).
- **Raises `ValueError`** with a clear message when the file is missing, the
  YAML is malformed, the structure is wrong (no `ignores` list), a rule has
  an unknown key / missing `test` / missing `reason`, or a `match` regex
  doesn't compile. CI fails fast on any of these.

### `IgnoreSpec` (dataclass)

| Member | Type | Purpose |
|--------|------|---------|
| `ignores` | `tuple[IgnoreRule, ...]` | The parsed rules |
| `path` | `str` | The source file path (empty for a `None`-loaded spec) |
| `count` | `int` (property) | Number of rules |
| `matches(test_name, failure_message="")` | `bool` | True when any rule's glob matches `test_name` AND (if the rule has a `match` regex) the regex matches `failure_message` |
| `describe(test_name, failure_message="")` | `str \| None` | The matching rule's `reason` (or the rule's glob), used so the CI report can name *why* a failure was ignored — an ignore is never silent |

### `IgnoreRule` (dataclass, frozen)

| Field | Type | Purpose |
|-------|------|---------|
| `test` | `str` | Test-name glob (fnmatch-style, `*` wildcards) |
| `reason` | `str` | **Required** — why the failure is known-benign (the human record) |
| `match` | `str` | Optional regex on the failure message; empty = any failure of a matching test |
| `pattern` | `re.Pattern[str] \| None` | Compiled `match` (internal, set by the parser) |

## How It Works (internals)

### `load_ignore_spec(path)` — main parser
- **`_parse_rule(item, index)`** — validates one YAML mapping into an
  `IgnoreRule`:
  - unknown keys rejected (typos fail loudly),
  - non-empty `test` required,
  - **non-empty `reason` required** (the anti-rug rule),
  - `match` compiled with `re.compile`, invalid regexes rejected with a
    message naming the rule index.
- **`_KEYS`** — the allowed rule keys (`{"test", "reason", "match"}`);
  anything else is an unknown-key error.

### `IgnoreSpec.matches(...)` / `IgnoreSpec.describe(...)` — matching
- **`fnmatch.fnmatch(test_name, rule.test)`** — glob match on the test name
  (handles pytest parameterization suffixes like `[chromium]`).
- **`rule.pattern.search(failure_message)`** — when a rule has a `match`
  regex, the failure message must match too; a rule without one covers any
  failure of the matching test.
- First matching rule wins (rules are evaluated in file order).
- `describe()` returns the matching rule's `reason` so the CI report can
  print *why* an ignore applied — never a silent pass.

### Internal utilities
- **`yaml.safe_load`** — the file is plain YAML; `safe_load` avoids arbitrary
  object construction (no code execution from the config).
