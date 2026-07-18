# Structural Summary: `cli/__init__.py`

## High-Level Purpose

This file is the **package initializer** for the `cli` package. Its sole responsibility is to **force UTF-8 encoding on stdout and stderr** before any other module in the package is imported. This is a critical bootstrapping step for the CLI's retro-styled terminal UI, which relies on box-drawing Unicode characters (e.g., ┌, ─, ┐) that cannot be represented in the Windows default cp1252 encoding.

The file is designed to be imported **first** when the CLI is launched via `python -m cli.main`, ensuring the encoding fix is in place before `retro_ui` or `menu_renderer` are loaded.

---

## Imports

| Module | Alias | Purpose |
|--------|-------|---------|
| `io`   | —     | Provides `TextIOWrapper` for re-wrapping stdout/stderr with UTF-8 encoding. |
| `sys`  | —     | Provides access to `sys.stdout`, `sys.stderr`, and `sys.stdout.encoding`. |

---

## Logic / Execution Flow (module-level, no classes or functions)

The file contains **no classes** and **no function definitions**. All logic runs at **module import time** as a side effect of the `import cli` statement.

### Step-by-step flow

1. **Check encoding**  
   `if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):`  
   - Guard: only proceed if stdout has a known encoding **and** that encoding is not already a UTF-8 variant.
   - `CP65001` is Windows code page for UTF-8.

2. **Re-wire stdout and stderr**  
   Inside the `if` block:
   ```python
   sys.stdout = io.TextIOWrapper(
       open(sys.stdout.fileno(), "wb"),
       encoding="utf-8",
       write_through=True
   )
   sys.stderr = io.TextIOWrapper(
       open(sys.stderr.fileno(), "wb"),
       encoding="utf-8",
       write_through=True
   )
   ```
   - `open(sys.stdout.fileno(), "wb")` — re-opens the underlying raw file descriptor in binary-write mode.
   - `io.TextIOWrapper(..., encoding="utf-8", write_through=True)` — wraps the binary stream in a UTF-8 text layer. `write_through=True` flushes immediately on every write, avoiding buffering issues.

3. **Fallback on failure**  
   `except (OSError, io.UnsupportedOperation):`  
   - If the re-wrapping fails (e.g., stdout is not a real file descriptor, or the TTY doesn't support it), the exception is silently caught and the original streams are left untouched.

---

## Key Architectural Patterns

| Pattern | Description |
|---------|-------------|
| **Bootstrapping / Early initialization** | The encoding fix runs at module-import time, before any dependent modules are loaded. This is a deliberate ordering dependency. |
| **Monkey-patching of stdlib streams** | `sys.stdout` and `sys.stderr` are replaced in-place. This is a pragmatic, non-invasive approach that affects all downstream code in the process without requiring changes to how those streams are used. |
| **Defensive guard clause** | The encoding check prevents unnecessary re-wrapping when the environment already uses UTF-8, avoiding potential side effects on systems that work correctly. |
| **Silent fallback** | The `except` clause swallows `OSError` and `io.UnsupportedOperation` without logging or re-raising, ensuring the CLI can still start (albeit with potentially garbled output) on environments where the re-wrap is impossible. |

---

## Dependencies / Side Effects

- **Side effect on import**: Replaces `sys.stdout` and `sys.stderr` with UTF-8 wrappers if the current encoding is not UTF-8.
- **No public API**: The file exports nothing; it exists purely for its import-time side effect.
- **Ordering requirement**: Must be imported before `cli.retro_ui` and `cli.menu_renderer`.

---

## Summary of Signatures

There are **no classes** and **no functions** defined in this file. The entire module is a single imperative block executed at import time.

| Element | Kind | Signature / Description |
|---------|------|------------------------|
| (module-level) | Guard + re-wire | `if sys.stdout.encoding not in ("UTF-8", "UTF8", "CP65001"):` → re-wrap stdout/stderr with UTF-8 `TextIOWrapper` |
