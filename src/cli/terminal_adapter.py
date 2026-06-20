"""Terminal abstraction for reading keys and handling platform quirks.

Provides a single `terminal` instance with methods used by CLI code so
TTY/PTY handling is centralized and testable.
"""

from __future__ import annotations

import os
import sys


class TerminalAdapter:
    def running_in_git_bash(self) -> bool:
        if os.environ.get("MSYSTEM"):
            return True
        return bool(os.environ.get("MSYS_WINVERSION"))

    def _flush_msvcrt_buffer(self) -> None:
        if self.running_in_git_bash():
            return
        try:
            import msvcrt

            for _ in range(10):
                if msvcrt.kbhit():  # type: ignore[attr-defined]
                    msvcrt.getwch()  # type: ignore[attr-defined]
                else:
                    break
        except Exception:
            pass

    def flush(self) -> None:
        self._flush_msvcrt_buffer()

    def read_key(self) -> str:
        if self.running_in_git_bash():
            return self._read_key_git_bash()

        try:
            import msvcrt

            char = msvcrt.getwch()  # type: ignore[attr-defined]
            if char in ("\x00", "\xe0"):
                char2 = msvcrt.getwch()  # type: ignore[attr-defined]
                if char2 == "H":
                    return "^"
                if char2 == "P":
                    return "v"
            return char
        except Exception:
            try:
                return sys.stdin.read(1)
            except Exception:
                return ""

    def _read_key_git_bash(self) -> str:
        # Fast path: try readline directly — works for StringIO (tests) and
        # piped input.  Falls back to threaded os.read for interactive TTYs.
        try:
            line = sys.stdin.readline()
            if line:
                return self._normalize_git_bash_input(line)
        except Exception:
            pass

        # Slow path: threaded byte-level read for interactive TTY.
        import select
        import threading

        buf: list[str] = []
        error: list[BaseException] = []

        def _reader() -> None:
            nonlocal buf
            try:
                while True:
                    try:
                        readable, _, _ = select.select([sys.stdin], [], [], 0.5)
                    except OSError, ValueError, TypeError:
                        line = sys.stdin.readline()
                        if not line:
                            break
                        buf.extend(line)
                        break
                    if not readable:
                        break
                    try:
                        raw_byte = os.read(sys.stdin.fileno(), 1)
                    except OSError, AttributeError:
                        line = sys.stdin.readline()
                        if not line:
                            break
                        buf.extend(line)
                        break
                    else:
                        ch = raw_byte.decode("utf-8", errors="replace")
                    if not ch:
                        break
                    buf.append(ch)
                    if buf[0:1] == ["\x1b"] and len(buf) >= 3:
                        break
                    if buf[0:1] == ["\x1b"] and ch in ("[", "O"):
                        continue
                    if ch != "\x1b" and len(buf) >= 1:
                        break
            except Exception as exc:
                error.append(exc)

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()
        thread.join(timeout=3.0)

        if error:
            raise error[0]

        if not buf:
            return ""

        return self._normalize_git_bash_input("".join(buf))

    def _normalize_git_bash_input(self, raw: str) -> str:
        """Normalise raw Git Bash input into a key token."""
        normalized = raw.rstrip("\n\r")

        if raw in ("\r", "\n", "\r\n"):
            return "\r"

        if normalized.startswith("\x1b[") and len(normalized) >= 3:
            if normalized[-1] == "A":
                return "^"
            if normalized[-1] == "B":
                return "v"
            return normalized
        if normalized.startswith("\x1bO") and len(normalized) >= 3:
            if normalized[-1] == "A":
                return "^"
            if normalized[-1] == "B":
                return "v"
            return normalized

        return normalized


terminal = TerminalAdapter()
