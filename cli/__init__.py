"""CLI module for Playwright test generator.

IMPORTANT: This file is imported FIRST when `python -m cli.main` runs.
It forces UTF-8 output on Windows Git Bash (MINGW64)
where the default stdout encoding is cp1252, which cannot encode box-drawing
characters (┌, ─, ┐, etc.) used in the retro UI.
"""

import io
import sys

# Force UTF-8 encoding BEFORE any other CLI module is imported.
# This must happen before retro_ui or menu_renderer are loaded.
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8", "CP65001"):
    # Re-wire stdout/stderr to UTF-8 writers. This works in Git Bash on Windows
    # where the console may default to cp1252.
    try:
        sys.stdout = io.TextIOWrapper(open(sys.stdout.fileno(), "wb"), encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(open(sys.stderr.fileno(), "wb"), encoding="utf-8", write_through=True)
    except OSError, io.UnsupportedOperation:
        pass  # stdout already a TTY or pipe — can't re-wrap
