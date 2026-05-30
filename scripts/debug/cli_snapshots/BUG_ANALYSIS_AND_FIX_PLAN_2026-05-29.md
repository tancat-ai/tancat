# CLI Bug Analysis and Fix Plan

**Date:** 2026-05-29
**Status:** Issue 1 FIXED · Issues 2-3 OPEN

---

## 1. ~~Duplicate "[Q]Quit" in Shortcut Bar~~ — ✅ FIXED (2026-05-29)

**Status:** Fix A applied. Enhanced deduplication logic added to `cli/menu_renderer.py` — checks both shortcut **keys** AND **labels** before appending mandatory Q/Quit. Three deduplication points covered (initial build, overflow-with-shortcuts trim, overflow-without-shortcuts trim).
Regression test: `scenario_duplicate_shortcut` in `scripts/debug/debug_cli_interactive.py` (already present — validates both duplicate keys and duplicate labels).

### Symptom (Resolved)
Bottom menu bar showed:
```
[1]Configure LLM  [2]Enter User Story  [3]Save & Exit  [4]Quit  [Q]Quit  [Q]Quit
```

### Root Cause (Resolved)
**File:** `cli/menu_renderer.py`, `print_menu()`

The `print_menu()` function unconditionally appended `("Q", "Quit")` at three locations (initial build, two overflow-trim branches) even when "Quit" already existed either as a numbered option key (e.g. key `"4"`) or via caller shortcuts. The original check only compared shortcut **keys** (`existing_keys`) but not **labels**, so when "Quit" appeared as a numbered option label (e.g. `("4", "Quit")`), the key `"Q"` was still absent and a duplicate `("Q", "Quit")` was appended.

### Fix Applied — Option A Enhanced (Key + Label Deduplication)
Every location that appends Q/Quit now checks both keys AND labels:
```python
existing_keys = {k for k, _ in bar}
existing_labels = {v.lower() for _, v in bar}
if "Q" not in existing_keys and "quit" not in existing_labels:
    bar.append(("Q", "Quit"))
```
This prevents duplicate Q whether "Quit" already exists as a numbered option or as a letter shortcut.

### Regression Test
`scenario_duplicate_shortcut` in `scripts/debug/debug_cli_interactive.py` captures the shortcut bar on the LLM provider screen and checks for:
1. Duplicate bracket keys using regex `\[(.)\]`
2. Duplicate labels using regex `\[[A-Za-z0-9]+\](\S+)` — catches cases where the same label text appears multiple times (e.g. `[Q]Quit  [Q]Quit`)

## 2. Arrow Navigation Doesn't Work in Git Bash

### Symptom
Bottom menu bar shows:
```
[1]Configure LLM  [2]Enter User Story  [3]Save & Exit  [4]Quit  [Q]Quit  [Q]Quit
```
Expected:
```
[1]Configure LLM  [2]Enter User Story  [3]Save & Exit  [4]Quit
```

### Root Cause
**File:** `cli/menu_renderer.py`, `print_menu()`, lines 274-282

```python
bar: list[tuple[str, str]] = []
for i, opt in enumerate(options):
    label = opt.split(" (", 1)[0]
    bar.append((str(i + 1), label))

if shortcuts:
    bar.extend(shortcuts)     # <-- shortcuts already contains [("Q", "Quit")]

bar.append(("Q", "Quit"))     # <-- UNCONDITIONAL: always adds another Q
```

In `cli/main.py` line 155: `main_shortcuts = [("Q", "Quit")]` already includes Q. The `print_menu()` function then **unconditionally** appends another Q. The trimming logic (lines 288-291) only removes items when the bar overflows terminal width; it does not deduplicate.

### Why Debug Scripts Missed This
- `debug_cli_interactive.py` scenarios use `expect()` regex patterns that match **any** occurrence of "Quit" — they don't validate the shortcut bar content for duplicates
- No assertion checks the rendered shortcut bar against expected content
- The `screen_clipping` scenario checks for "Enter User Story" bleed but not for duplicate shortcuts

### Fix
**Option A (preferred):** Deduplicate before adding mandatory Q
```python
# After building bar, before final render:
existing_keys = {k for k, _ in bar}
if "Q" not in existing_keys:
    bar.append(("Q", "Quit"))
```

**Option B:** Remove Q from caller shortcuts, rely on automatic Q
```python
# In cli/main.py:
main_shortcuts = []  # Remove ("Q", "Quit") — print_menu always adds it
```

Option A is safer because it handles all callers without changing any call sites.

---

## 2. Arrow Navigation Doesn't Work in Git Bash

### Symptom
Pressing Up/Down arrow keys in Git Bash (MINGW64) does not navigate the menu.

### Root Cause
**File:** `cli/menu_renderer.py`, `_read_key_git_bash()`, lines 170-245

The reader thread (lines 184-210) reads characters one-at-a-time:

```python
ch = sys.stdin.read(1)
if not ch:
    break
buf.append(ch)
# Stop early if we have a complete escape sequence
if buf[0:1] == ["\x1b"] and len(buf) >= 3:
    break
if ch != "\x1b" and len(buf) >= 1:
    break    # <-- BUG: breaks after reading '[', before reading 'A'
```

When Up arrow (`\x1b[A`) arrives:
1. `ch = "\x1b"`, `buf = ["\x1b"]` — first guard passes (ch == "\x1b"), continues
2. `ch = "["`, `buf = ["\x1b", "["]` — second guard: `ch != "\x1b"` is True, `len(buf) >= 1` is True -> **breaks**

Result: `buf = ["\x1b", "["]` -> `raw = "\x1b["` which has `len(raw) == 2`, so `raw[2]` at line 228 causes IndexError, or the condition `raw.startswith("\x1b[")` is True but `raw[2]` access fails.

### Why Debug Scripts Missed This
- `debug_cli_interactive.py` sends arrow keys via `child.sendline("\x1b[B]")` which sends the **complete escape sequence** in one pipe write
- But the **real** Git Bash terminal sends escape sequences as separate keystrokes with timing gaps
- The subprocess pipe delivers all 3 bytes at once, masking the timing issue that occurs in a real terminal
- The `menu_navigation` scenario's `expect(r"> Enter User Story", timeout=5.0)` **times out** but the exception is caught and reported as a generic FAIL without revealing the actual cause

### Fix
Fix the premature break in the reader thread:
```python
def _reader() -> None:
    nonlocal buf
    try:
        while True:
            try:
                readable, _, _ = select.select([sys.stdin], [], [], 0.5)
            except OSError:
                line = sys.stdin.readline()
                if not line:
                    break
                buf.extend(line)
                break
            if not readable:
                break
            ch = sys.stdin.read(1)
            if not ch:
                break
            buf.append(ch)
            # Stop early if we have a complete escape sequence
            if buf[0:1] == ["\x1b"] and len(buf) >= 3:
                break
            # FIX: only stop for regular keys, NOT for incomplete escape sequences
            if buf[0:1] == ["\x1b"] and ch in ("[", "O"):
                continue  # escape sequence still in progress, keep reading
            if ch != "\x1b" and len(buf) >= 1:
                break
    except Exception as exc:
        error.append(exc)
```

Also fix the `raw[2]` access to use safe indexing:
```python
if raw.startswith("\x1b[") and len(raw) >= 3:
    if raw[-1] == "A":
        return "^"
    if raw[-1] == "B":
        return "v"
```

---

## 3. Pressing "1" to Configure LLM Does Nothing

### Symptom
User types "1" on main menu to select "Configure LLM" — screen clears but nothing changes (stays on main menu or flashes and returns).

### Root Cause
**Compound issue** from arrow key fix + Enter key handling in Git Bash.

When the user types "1" then Enter in Git Bash:
1. `_read_key_git_bash()` is called
2. Reader thread gets `ch = "1"`, appends to buf. Since `buf[0:1] != ["\x1b"]` and `ch != "\x1b"`, it triggers `break`. Returns `"1"`.
3. `print_menu()` parses `choice = "1"`, computes `idx = 0`, returns `0`.
4. `main.py` calls `_configure_llm_inline()` which calls `configure_llm()` which calls `print_menu()` for the provider sub-menu.
5. The provider sub-menu's `_read_key_git_bash()` call may read residual data from stdin — **or** the `clear_screen()` + `render_menu()` output gets intermingled with residual input.

**But the real issue:** In the current code, when the user presses "1" + Enter in a real terminal, the "1" arrives, then Enter (`\r`) arrives separately. The first `_read_key_git_bash()` gets "1" and returns it correctly. But `print_menu()` doesn't call `_read_key()` again — it returns `idx = 0`. Then `main.py` receives `idx = 0` and enters the Configure LLM branch.

However, looking more carefully at `main.py`:
- Line 155-156 shows main_shortcuts contains Q only
- Line 160: `idx = print_menu(main_options, ..., shortcuts=main_shortcuts)`
- Lines 162-178: `if idx == 0: self._configure_llm_inline()`

The "1" key path works in `print_menu()` — `int("1") - 1 = 0` which is valid. The issue is likely that `_read_key_git_bash()` returns `""` (empty string) when no input is immediately available (the `select` timeout fires), and the `while True` loop re-renders the menu, but since no input arrived, it loops forever without showing a prompt.

**Actually the real issue:** In `print_menu()`, line 297: `key = _read_key()` returns `""` in Git Bash when no input is available. Line 317: `if not choice: continue` — this **loops forever** re-rendering the menu without any input being consumed. The menu appears frozen because it's spinning in a tight loop calling `_read_key_git_bash()` which times out after 0.5s each time, then re-renders.

### Fix
In `print_menu()`, when `_read_key()` returns empty in Git Bash mode, add a small sleep before looping to avoid tight re-render:
```python
if key == "":
    # Git Bash: no input yet, wait a moment before re-rendering
    time.sleep(0.2)
    continue
```

Or better: make `_read_key_git_bash()` block properly by adjusting the select timeout and retry logic.

---

## Why Debug Scripts Didn't Catch These

| Bug | Why `debug_cli.py` Missed | Why `debug_cli_interactive.py` Missed |
|-----|---------------------------|---------------------------------------|
| Duplicate Q | Doesn't test menu rendering output | Scenarios use `expect()` regex that matches first occurrence, doesn't validate full bar |
| Arrow keys | Tests `_read_key()` in isolation, not through subprocess pipe | Sends complete escape sequence via pipe (all 3 bytes at once), masking timing issue |
| "1" does nothing | Doesn't test full menu->submenu routing | Uses `sendline("1")` which sends "1\r\n" as one block — all bytes available, no timing gap |

### Core Problem with Debug Scripts
Both debug scripts run the CLI as a **subprocess with pipe-based stdin/stdout**. This fundamentally changes how `_read_key_git_bash()` behaves:
- Pipe input arrives as complete blocks, not as individual keystrokes with timing gaps
- The `select.select()` call returns immediately with all data available
- Arrow key escape sequences arrive as 3 bytes at once instead of separately

### Recommended Debug Script Improvements

1. **Add assertion for shortcut bar content:**
   ```python
   child.expect(r"AI Playwright", timeout=10.0)
   snapshot = w._capture_snapshot()
   # Count occurrences of "Quit" in snapshot
   quit_count = snapshot.count("Quit")
   assert quit_count <= 2, f"Expected at most 2 'Quit' references, found {quit_count}"
   ```

2. **Test arrow keys with character-by-character sending:**
   ```python
   # Send escape sequence as individual characters with delays
   child.send("\x1b")
   time.sleep(0.05)
   child.send("[")
   time.sleep(0.05)
   child.send("A")
   ```

3. **Test menu->submenu transition with explicit snapshot comparison:**
   ```python
   main_menu_snapshot = w._capture_snapshot()
   child.sendline("1")
   time.sleep(1.0)
   llm_menu_snapshot = w._capture_snapshot()
   assert "Ollama" in llm_menu_snapshot or "Provider" in llm_menu_snapshot
   ```

---

## Implementation Plan

### Phase 1: Fix Blocker Bugs (menu_renderer.py)

1. **Fix duplicate Q shortcut** — Add deduplication before appending mandatory Q
2. **Fix arrow key reading** — Fix premature break in `_reader()` thread, use safe indexing for `raw[2]`
3. **Fix menu freeze on empty input** — Add small delay or better blocking in Git Bash mode
4. **Run ruff + mypy** on changed files
5. **Run existing tests:** `pytest tests/test_cli_menu_renderer.py -v`

### Phase 2: Improve Debug Scripts

6. **Add shortcut bar assertion** to `screen_clipping` scenario in `debug_cli_interactive.py`
7. **Add character-by-character arrow key test** to `menu_navigation` scenario
8. **Add submenu transition assertion** to `provider_selection` scenario
9. **Run debug scripts** and verify they detect the bugs before fixes and pass after fixes

### Phase 3: Add Unit Tests

10. **Test `_read_key_git_bash()` with character-by-character input** simulating real terminal timing
11. **Test `print_menu()` shortcut bar deduplication**
12. **Test full menu->submenu transition in Git Bash mode**
13. **Run full test suite:** `pytest -x -q`

### Phase 4: Verify End-to-End

14. **Run `ruff check cli/menu_renderer.py`**
15. **Run `mypy cli/menu_renderer.py`**
16. **Run `pytest tests/test_cli_menu_renderer.py -v`**
17. **Run `pytest tests/test_retro_ui.py -v`**
18. **Manual test in Git Bash terminal** — verify all 3 bugs are fixed

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Fix breaks non-Git Bash arrow keys | Medium | Keep `if _running_in_git_bash()` guard — msvcrt path unchanged |
| Fix changes timing for pipe-based tests | Low | Debug scripts send complete blocks — escape sequence fix handles both |
| Dedup removes expected shortcuts | Low | Only deduplicates on key, not label — Q is unique |
| Sleep in menu loop causes lag | Low | 0.2s sleep only when no input — imperceptible |