# `src/cli/__init__.py` — CLI Module Entry Point

## Purpose

UTF-8 encoding fix for Windows Git Bash (MINGW64). This file is imported **first** when `python -m cli.main` runs to force UTF-8 output before any other CLI module loads.

## Problem Solved

On Windows Git Bash, `sys.stdout.encoding` defaults to `cp1252`, which cannot encode box-drawing characters (`┌`, `─`, `┐`, etc.) used by the retro UI (`src/cli/retro_ui.py`) and menu renderer.

## Mechanism

Checks if stdout encoding is **not** UTF-8/UTF8/CP65001. If so, re-wraps `sys.stdout` and `sys.stderr` as `io.TextIOWrapper` with UTF-8 encoding and `write_through=True`.

Catches `OSError` / `io.UnsupportedOperation` silently when stdout is already a TTY or pipe (cannot be re-wrapped).

## Key Notes

- Must be imported before `retro_ui` or `menu_renderer`.
- No-ops on native Linux/macOS environments (already UTF-8).
