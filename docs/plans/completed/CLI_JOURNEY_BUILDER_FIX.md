# CLI Journey Builder Fix Plan

**Date:** 2026-06-01
**Status:** Proposed
**Priority:** Critical

---

## Problem Statement

The CLI journey builder crashes when the user presses `Q` (Quit) at certain menus. The crash originates from `print_menu()` returning `-1` to signal quit, but downstream code doesn't check for negative returns before using the return value as a list index.

### Observed Symptom

```
   Enter selection: q

  Quitting.
  Description for this scrape step:: Traceback (most recent call last):
  File "cli/main.py", line 453, in <module>
    sys.exit(main())
  File "cli/main.py", line 427, in main
    asyncio.run(interactive_session())
  ...
```

The user presses `q` to quit the journey builder, but instead of exiting gracefully, the CLI crashes with a traceback.

---

## Root Cause Analysis

### The Mechanism

`cli/menu_renderer.py` — `print_menu()` returns:
- `0` to `len(options)-1`: valid selection index
- `-1`: quit signal (returned when user presses `Q` or triggers EOF/KeyboardInterrupt)

However, `collect_journey_steps()` uses the return value directly as a list index without checking for `-1`:

```python
# Line 570-571 — CURRENT CODE (buggy)
action_idx = print_menu(JOURNEY_STEP_ACTIONS, "Step type")
action = JOURNEY_STEP_ACTIONS[action_idx]  # CRASH: JOURNEY_STEP_ACTIONS[-1] == "scrape"
```

Python's negative indexing means `JOURNEY_STEP_ACTIONS[-1]` returns `"scrape"` instead of raising an error. This causes the code to continue building a scrape step the user never intended to add, leading to cascading confusion and eventual crash.

### Affected Locations

| Location | Line(s) | Problem |
|----------|---------|---------|
| `collect_journey_steps()` | 562-566 | "Add step / Done building" menu — doesn't handle `-1` |
| `collect_journey_steps()` | 570-571 | "Step type" menu — doesn't handle `-1`, negative index silently picks wrong action |

### Cascade Sequence

1. User is on "Add step / Done building" menu
2. User presses `Q` to quit
3. `print_menu()` returns `-1`
4. Code doesn't check for `-1`, falls through to step-type menu
5. User presses `Q` again on step-type menu
6. `print_menu()` returns `-1`
7. `JOURNEY_STEP_ACTIONS[-1]` → `"scrape"` (wrong action, but valid Python)
8. Code prompts for "Description for this scrape step:"
9. User is confused, enters more input or triggers EOF
10. Crash occurs in subsequent input handling

---

## Fix Plan

### Fix 1: Guard the "Add step / Done building" menu

**File:** `cli/menu_renderer.py`
**Location:** After line 566

```python
# CURRENT (buggy):
add_choice = print_menu(
    ["Add step", "Done building"],
    "Journey builder",
    shortcuts=[("A", "Add"), ("D", "Done")],
)
if add_choice == 1:
    break

# FIXED:
add_choice = print_menu(
    ["Add step", "Done building"],
    "Journey builder",
    shortcuts=[("A", "Add"), ("D", "Done")],
)
if add_choice == 1:
    break
if add_choice < 0:
    print(yellow("  Quitting journey builder."))
    return steps
```

### Fix 2: Guard the "Step type" menu

**File:** `cli/menu_renderer.py`
**Location:** After line 570

```python
# CURRENT (buggy):
action_idx = print_menu(JOURNEY_STEP_ACTIONS, "Step type")
action = JOURNEY_STEP_ACTIONS[action_idx]

# FIXED:
action_idx = print_menu(JOURNEY_STEP_ACTIONS, "Step type")
if action_idx < 0:
    print(yellow("  Quitting journey builder."))
    return steps
action = JOURNEY_STEP_ACTIONS[action_idx]
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `cli/menu_renderer.py` | Add two negative-index guards in `collect_journey_steps()` |

---

## Files to Create

| File | Purpose |
|------|---------|
| `tests/test_journey_builder_quit.py` | Regression test: verify `collect_journey_steps()` handles quit gracefully |

---

## Test Plan

### Manual Testing

1. Launch CLI: `python -m cli.main`
2. Navigate to "Configure Journey" → "Build journey steps"
3. Press `Q` on "Add step / Done building" menu → should quit gracefully
4. Add one step, then press `Q` on "Step type" menu → should quit gracefully with step preserved
5. Press `Q` while entering step description → should handle EOF gracefully

### Automated Testing

```python
# tests/test_journey_builder_quit.py
def test_journey_builder_quit_at_add_menu():
    """Pressing Q on 'Add step / Done building' returns existing steps without crash."""
    adapter = TestingTerminal(
        responses_iterable=["q"]  # Quit at first menu
    )
    set_terminal_adapter(adapter)
    steps = collect_journey_steps()
    assert steps == []  # No steps added before quit

def test_journey_builder_quit_at_step_type_menu():
    """Pressing Q on 'Step type' menu preserves steps added so far."""
    step = {"action": "navigate", "url": "https://example.com", "description": "Go to home"}
    adapter = TestingTerminal(
        responses_iterable=[
            "1",          # Add step
            "0",          # navigate
            "Go to home", # description
            "https://example.com",  # url
            "q",          # Quit at "Add step / Done building" menu
        ]
    )
    set_terminal_adapter(adapter)
    steps = collect_journey_steps()
    assert len(steps) == 1
    assert steps[0]["action"] == "navigate"
```

---

## Verification Checklist

- [ ] `ruff check cli/menu_renderer.py` passes
- [ ] `mypy cli/menu_renderer.py` passes
- [ ] `pytest tests/test_journey_builder_quit.py -v` passes
- [ ] Manual test: press `Q` at all three journey builder menus — no crashes
- [ ] Existing tests still pass: `pytest tests/test_cli_* -v`

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Fix breaks existing menu navigation | Low | Negative check is additive, doesn't change happy path |
| TestingTerminal doesn't simulate quit correctly | Medium | Use existing `test_cli_menu_interactive_mock.py` patterns |
| Other menus have same bug | Medium | Audit all `print_menu` call sites after fixing this one |

---

## Related Issues

- Known pattern: `print_menu()` returns `-1` for quit across all CLI menus
- Other callers that may need same audit: `collect_authentication()`, `collect_consent_mode()`, `collect_urls()`
- The same negative-index vulnerability exists anywhere `print_menu` output is used as a list index without validation

---

*Author: AI assistant (Cline)*
*Session: 2026-06-01 20:27 GMT+1*