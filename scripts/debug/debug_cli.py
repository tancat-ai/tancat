#!/usr/bin/env python
"""Debug CLI input handling.

Runs the menu input loop with diagnostic output to identify where blocking occurs.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading

from src.cli.menu_renderer import _read_key, _running_in_git_bash

# Print environment diagnostics
print("=" * 60)
print("CLI Debug - Environment")
print("=" * 60)
print(f"stdin.isatty(): {sys.stdin.isatty()}")
print(f"MSYSTEM: {os.environ.get('MSYSTEM', '')}")
print(f"TERM: {os.environ.get('TERM', '')}")
print(f"SHELL: {os.environ.get('SHELL', '')}")
print(f"Platform: {sys.platform}")
print()

print("=" * 60)
print("Git Bash Detection")
print("=" * 60)
in_git_bash = _running_in_git_bash()
print(f"_running_in_git_bash(): {in_git_bash}")
print()

# Test _read_key with a timeout
print("=" * 60)
print("_read_key() test")
print("=" * 60)
print("About to call _read_key()...")
print("Type a key and press Enter (if in Git Bash)")
print("or just press a key (if native console)")
print("This will block until input is received.")
print()

result = ["(timeout)"]


def read_key_threaded() -> None:
    try:
        val = _read_key()
        result[0] = repr(val)
    except Exception as e:
        result[0] = f"Exception: {e}"


t = threading.Thread(target=read_key_threaded, daemon=True)
t.start()
t.join(timeout=3)

if t.is_alive():
    print("_read_key() is BLOCKING after 3 seconds (thread still alive)")
    print("This confirms the bug: _read_key() does not return in Git Bash")
else:
    print(f"_read_key() returned: {result[0]}")

print()
print("=" * 60)
print("Testing select-based approach")
print("=" * 60)

# Test if select works on stdin
try:
    import select

    readable, _, _ = select.select([sys.stdin], [], [], 0.5)
    if readable:
        print("stdin has data available via select")
        data = sys.stdin.read(1)
        print(f"Read: {repr(data)}")
    else:
        print("select says stdin is readable (no data pending after 500ms)")
        print("select works on stdin in this environment")
except Exception as e:
    print(f"select failed: {e}")

print()
print("=" * 60)
print("Testing tty.tcsetattr / termios for non-blocking")
print("=" * 60)

try:
    if importlib.util.find_spec("termios") and importlib.util.find_spec("tty"):
        print("termios and tty modules available")
    else:
        print("termios/tty not available")
    # Can't actually test without a real TTY context
except ImportError as e:
    print(f"termios/tty not available: {e}")

print()
print("=" * 60)
print("Summary")
print("=" * 60)
print(f"Running in Git Bash: {in_git_bash}")
print(f"stdin is a TTY: {sys.stdin.isatty()}")
if in_git_bash and sys.stdin.isatty():
    print("PROBLEM: sys.stdin.readline() blocks waiting for Enter in Git Bash.")
    print("SOLUTION: Use 'select' to poll stdin, then read available characters.")
    print("Or switch to a line-based CLI for Git Bash (type number + Enter).")
