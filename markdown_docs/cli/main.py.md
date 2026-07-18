# `cli/main.py`

## High-Level Purpose

This file is a **backwards-compatible shim** that serves as a legacy entry point for the CLI. The actual CLI implementation has been moved to `src/cli/main.py`, and this file simply re-exports the `main` function for compatibility with existing scripts and workflows that invoke `python -m cli.main`.

## File Content (verbatim)

```python
"""Backwards-compatible shim — CLI entry point moved to src.cli.main."""

import sys

from src.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
```

## Functions

| Name | Signature | Description |
|------|-----------|-------------|
| `main` | Imported from `src.cli.main` | The actual CLI entry point function. |

## Module-Level Attributes

| Name | Type | Value | Description |
|------|------|-------|-------------|
| `__doc__` | `str` | `"Backwards-compatible shim..."` | Module docstring explaining the file's purpose. |

## Imports

| Module | Purpose |
|--------|---------|
| `sys` | Provides `sys.exit()` for process exit. |
| `src.cli.main` | Imports the actual `main` function from the new location. |

## Architectural Patterns & Observations

| Aspect | Observation |
|--------|-------------|
| **Shim / Compatibility Layer** | This file exists solely to maintain backwards compatibility. It allows existing scripts to continue using `python -m cli.main` while the actual implementation lives in `src/cli/main.py`. |
| **No Logic** | The file contains no business logic; it is purely a re-export. |
| **Entry Point** | When run as `__main__`, it invokes `main()` and exits with the returned status code. |

## Dependencies

- `src.cli.main` — The actual CLI implementation.

## Related Files

- `src/cli/main.py` — The real CLI entry point.
- `launch_cli.sh` — Shell script that launches the CLI.