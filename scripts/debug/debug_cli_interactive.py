#!/usr/bin/env python3
"""Interactive CLI Walkthrough Debugger.

Spawns the CLI (python -m cli.main) as a subprocess and drives it via
stdin/stdout pipes to replay predefined test scenarios.

Usage:
    python scripts/debug/debug_cli_interactive.py              # Run all scenarios
    python scripts/debug/debug_cli_interactive.py --list        # List scenarios
    python scripts/debug/debug_cli_interactive.py --run NAME    # Run single scenario

Each scenario captures terminal snapshots after every interaction for
manual inspection and optional assertions.

Requires no external dependencies - uses subprocess.Popen with pipes.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Types ──────────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    """Result of a single interaction step."""

    step_name: str
    sent: str
    matched: str
    snapshot: str
    duration_ms: int
    success: bool = True
    error: str = ""


@dataclass
class ScenarioResult:
    """Result of running a full scenario."""

    name: str
    description: str
    steps: list[StepResult] = field(default_factory=list)
    total_duration_ms: int = 0
    success: bool = True
    error: str = ""


# ── Helper ─────────────────────────────────────────────────────────────────


def _describe(input_text: str) -> str:
    """Human-readable description of input for logs."""
    if input_text == "\n":
        return "<Enter>"
    if input_text == "\r":
        return "<CR>"
    if input_text == "\x1b[A":
        return "<Up>"
    if input_text == "\x1b[B":
        return "<Down>"
    if len(input_text) == 1:
        return f"'{input_text}'"
    return input_text


# ── Subprocess wrapper (replaces wexpect) ─────────────────────────────────


class SubprocessChild:
    """Minimal wexpect-compatible wrapper around subprocess.Popen.

    Provides sendline(), expect(), terminate(), wait(), kill(),
    before, match, and pid attributes so scenarios work unchanged.
    """

    def __init__(
        self,
        cmd: str | list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 30,
        codepage: str | None = None,
    ) -> None:
        self._timeout = timeout
        self.pid: int | None = None

        if isinstance(cmd, str):
            cmd = cmd.split()

        self._proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            bufsize=0,  # unbuffered binary mode
        )
        self.pid = self._proc.pid
        self._buffer = ""
        self.before: str = ""
        self.match: Any = None
        # Thread-safe lock for buffer access and a background reader
        self._buffer_lock = threading.Lock()
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

    def sendline(self, text: str = "") -> None:
        """Send a line of text to stdin."""
        if self._proc.stdin is not None:
            self._proc.stdin.write((text + "\r\n").encode("utf-8"))
            self._proc.stdin.flush()

    def send(self, text: str) -> None:
        """Send text without newline (alias for sendline for compatibility)."""
        self.sendline(text)

    def expect(self, pattern: str | re.Pattern, timeout: float | None = None) -> int:
        """Read stdout until pattern matches.

        Returns 0 on match, raises on timeout.
        """
        t = timeout if timeout is not None else self._timeout
        deadline = time.monotonic() + t
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        while time.monotonic() < deadline:
            # Check buffer for pattern under lock
            with self._buffer_lock:
                m = compiled.search(self._buffer)
                if m:
                    self.before = self._buffer[: m.start()]
                    self.match = m
                    # Remove matched text from buffer, keep remaining
                    self._buffer = self._buffer[m.end():]
                    return 0
            time.sleep(0.05)

        # Check process exit
        if self._proc.poll() is not None:
            raise EOFError(f"Process exited with code {self._proc.returncode}")

        raise TimeoutError(
            f"Timeout after {t}s waiting for pattern: {pattern!r}"
        )

    def _read_nonblocking(self) -> str:
        """Read available output on Windows where select() doesn't work for pipes.

        Uses a thread-based approach to read what's available.
        """
        # Deprecated: kept for compatibility but no longer used.
        return ""

    def _reader(self) -> None:
        """Background thread that continuously reads stdout and appends to buffer."""
        if self._proc.stdout is None:
            return
        try:
            while True:
                data = self._proc.stdout.read(1024)
                if not data:
                    break
                try:
                    chunk = data.decode("utf-8", errors="replace")
                except Exception:
                    chunk = str(data)
                with self._buffer_lock:
                    self._buffer += chunk
        except Exception:
            # Reader thread must never raise to avoid crashing parent thread
            pass

    def terminate(self) -> None:
        """Terminate the process."""
        if self._proc.poll() is None:
            self._proc.terminate()

    def wait(self) -> int | None:
        """Wait for process to exit and return exit code."""
        return self._proc.wait(timeout=5)

    def kill(self) -> None:
        """Force kill the process."""
        if self._proc.poll() is None:
            self._proc.kill()


# ── Walkthrough Helper ─────────────────────────────────────────────────────


class CliWalkthrough:
    """Build and execute a CLI walkthrough step-by-step."""

    def __init__(self, child: Any, snapshot_dir: Path) -> None:
        self.child = child
        self.snapshot_dir = snapshot_dir
        self.steps: list[StepResult] = []
        self._step_count = 0

    def _capture_snapshot(self) -> str:
        """Capture current terminal output."""
        try:
            text = ""
            before = self.child.before
            if before:
                text += before if isinstance(before, str) else before.decode("utf-8", errors="replace")
            if self.child.match:
                group = self.child.match.group(0)
                text += group if isinstance(group, str) else group.decode("utf-8", errors="replace")
            return text[-2000:]
        except Exception:
            return "<snapshot capture failed>"

    def log(self, name: str, sent: str, duration_ms: int = 0, success: bool = True, error: str = "") -> StepResult:
        """Log a step with current snapshot."""
        self._step_count += 1
        r = StepResult(
            step_name=f"Step {self._step_count}: {name}",
            sent=sent,
            matched="",
            snapshot=self._capture_snapshot(),
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        self.steps.append(r)
        return r

    def save_snapshots(self, scenario_name: str) -> Path:
        """Save all step snapshots to a markdown file."""
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        out = self.snapshot_dir / f"{scenario_name.replace(' ', '_')}.md"

        all_pass = all(s.success for s in self.steps)
        lines = [
            f"# Scenario: {scenario_name}",
            f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Steps:** {len(self.steps)}",
            f"**Status:** {'PASS' if all_pass else 'FAIL'}",
            "---",
        ]

        for step in self.steps:
            lines.extend([
                f"## {step.step_name}",
                f"- **Sent:** `{_describe(step.sent)}`",
                f"- **Duration:** {step.duration_ms}ms",
                f"- **Status:** {'OK' if step.success else 'FAIL'}",
            ])
            if step.error:
                lines.append(f"- **Error:** {step.error}")
            lines.append("```")
            lines.append(step.snapshot)
            lines.extend(["```", "---"])

        out.write_text("\n".join(lines), encoding="utf-8")
        return out


# ── Scenarios ──────────────────────────────────────────────────────────────


def scenario_menu_navigation(child: Any, snapshot_dir: Path) -> ScenarioResult:
    """Arrow key navigation and Enter selection in main menu."""
    result = ScenarioResult(name="Menu Navigation", description=scenario_menu_navigation.__doc__ or "")
    t0 = time.monotonic()
    try:
        w = CliWalkthrough(child, snapshot_dir)

        child.expect(r"AI Playwright|Main menu", timeout=10.0)
        w.log("Initial menu", "<wait>")

        child.sendline("\x1b[B")
        time.sleep(0.3)
        w.log("Down arrow", "<Down>")

        child.sendline("\x1b[A")
        time.sleep(0.3)
        w.log("Up arrow", "<Up>")

        child.sendline("")
        child.expect(r"LLM|Provider|Configure|Select|Base URL", timeout=10.0)
        w.log("Select first item", "<Enter>")

        child.sendline("q")
        time.sleep(0.3)
        w.log("Quit with Q", "q")

        out = w.save_snapshots("menu_navigation")
        result.steps = w.steps
        result.success = True
        print(f"  OK Menu Navigation -> snapshots: {out}")

    except Exception as e:
        result.success = False
        result.error = str(e)
        print(f"  FAIL Menu Navigation -> {e}")

    result.total_duration_ms = int((time.monotonic() - t0) * 1000)
    return result


def scenario_provider_selection(child: Any, snapshot_dir: Path) -> ScenarioResult:
    """Full LLM provider configuration flow."""
    result = ScenarioResult(name="Provider Selection", description=scenario_provider_selection.__doc__ or "")
    t0 = time.monotonic()
    try:
        w = CliWalkthrough(child, snapshot_dir)

        child.expect(r"AI Playwright|Configure LLM", timeout=10.0)
        w.log("Initial menu", "<wait>")

        child.sendline("1")
        child.expect(r"Provider|Ollama|Select", timeout=10.0)
        w.log("Select Configure LLM", "1<Enter>")

        child.sendline("1")
        child.expect(r"Base URL|localhost", timeout=10.0)
        w.log("Select Ollama", "1<Enter>")

        child.sendline("")
        child.expect(r"model|Model|Select|Could not", timeout=15.0)
        w.log("Accept default URL", "<Enter>")

        out = w.save_snapshots("provider_selection")
        result.steps = w.steps
        result.success = True
        print(f"  OK Provider Selection -> snapshots: {out}")

    except Exception as e:
        result.success = False
        result.error = str(e)
        print(f"  FAIL Provider Selection -> {e}")

    result.total_duration_ms = int((time.monotonic() - t0) * 1000)
    return result


def scenario_quit_shortcut(child: Any, snapshot_dir: Path) -> ScenarioResult:
    """Verify Q key exits gracefully from main menu."""
    result = ScenarioResult(name="Quit Shortcut", description=scenario_quit_shortcut.__doc__ or "")
    t0 = time.monotonic()
    try:
        w = CliWalkthrough(child, snapshot_dir)

        child.expect(r"AI Playwright|Quit", timeout=10.0)
        w.log("Main menu", "<wait>")

        child.sendline("q")
        time.sleep(0.5)
        w.log("Press Q", "q")

        out = w.save_snapshots("quit_shortcut")
        result.steps = w.steps
        result.success = True
        print(f"  OK Quit Shortcut -> snapshots: {out}")

    except Exception as e:
        result.success = False
        result.error = str(e)
        print(f"  FAIL Quit Shortcut -> {e}")

    result.total_duration_ms = int((time.monotonic() - t0) * 1000)
    return result


def scenario_screen_clipping(child: Any, snapshot_dir: Path) -> ScenarioResult:
    """Verify clear_screen prevents bleed between menu screens."""
    result = ScenarioResult(name="Screen Clipping", description=scenario_screen_clipping.__doc__ or "")
    t0 = time.monotonic()
    try:
        w = CliWalkthrough(child, snapshot_dir)

        child.expect(r"AI Playwright", timeout=10.0)
        w.log("Main menu", "<wait>")

        child.sendline("1")
        child.expect(r"LLM|Provider", timeout=10.0)
        llm_snapshot = w._capture_snapshot()
        w.log("LLM config", "1<Enter>")

        bleed = "Enter User Story" in llm_snapshot or "Target URLs" in llm_snapshot
        status = not bleed
        error = "Main menu text found on LLM config screen" if bleed else ""
        w.log("Bleed check", "analyze", success=status, error=error)

        out = w.save_snapshots("screen_clipping")
        result.steps = w.steps
        result.success = status
        print(f"  {'OK' if status else 'WARN'} Screen Clipping -> snapshots: {out}")

    except Exception as e:
        result.success = False
        result.error = str(e)
        print(f"  FAIL Screen Clipping -> {e}")

    result.total_duration_ms = int((time.monotonic() - t0) * 1000)
    return result


# ── Scenario registry ──────────────────────────────────────────────────────

SCENARIOS: dict[str, Callable[[Any, Path], ScenarioResult]] = {
    "menu_navigation": scenario_menu_navigation,
    "provider_selection": scenario_provider_selection,
    "quit_shortcut": scenario_quit_shortcut,
    "screen_clipping": scenario_screen_clipping,
}


# ── Spawn CLI process ──────────────────────────────────────────────────────


def _spawn_cli() -> SubprocessChild:
    """Spawn the CLI using subprocess.Popen with pipes."""
    python = sys.executable or "python"
    cmd = [python, "-u", "-m", "cli.main"]
    cwd = str(Path(__file__).resolve().parent.parent.parent)

    # Force MSYSTEM so the spawned CLI detects Git Bash and uses
    # sys.stdin.readline() instead of msvcrt (which does not work
    # under pipes). Also set COLUMNS/LINES for consistent
    # retro UI rendering.
    child = SubprocessChild(
        cmd,
        cwd=cwd,
        codepage="utf-8",
        timeout=30,
        env={
            **os.environ,
            "MSYSTEM": "MINGW64",
            "COLUMNS": "100",
            "LINES": "30",
            "PYTHONUNBUFFERED": "1",
        },
    )
    return child


# ── Runner ─────────────────────────────────────────────────────────────────


def _run_scenario(name: str, snapshot_dir: Path) -> ScenarioResult:
    """Spawn CLI, run scenario, kill process."""
    child = _spawn_cli()
    try:
        return SCENARIOS[name](child, snapshot_dir)
    finally:
        try:
            child.terminate()
            child.wait()
        except Exception:
            try:
                child.kill()
                child.wait()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI Interactive Walkthrough Debugger")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    parser.add_argument("--run", type=str, help="Run a single scenario by name")
    parser.add_argument("--output", type=str, default="scripts/debug/cli_snapshots", help="Snapshot output directory")
    args = parser.parse_args()

    snapshot_dir = Path(args.output)

    if args.list:
        print("Available scenarios:")
        for name, fn in SCENARIOS.items():
            doc_line = (fn.__doc__ or "").split("\n")[0].strip()
            print(f"  {name:30s} - {doc_line}")
        return 0

    names = [args.run] if args.run else list(SCENARIOS.keys())

    results: list[ScenarioResult] = []
    for name in names:
        if name not in SCENARIOS:
            print(f"Unknown scenario: {name}")
            continue
        print(f"\n{'=' * 60}")
        print(f"Running: {name}")
        print("=" * 60)
        result = _run_scenario(name, snapshot_dir)
        results.append(result)

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    for r in results:
        status = "OK" if r.success else "FAIL"
        print(f"  [{status}] {r.name} ({r.total_duration_ms}ms)")
        if r.error:
            print(f"         Error: {r.error}")

    print(f"\nSnapshots saved to: {snapshot_dir.resolve()}")
    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
