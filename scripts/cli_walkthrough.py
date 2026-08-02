#!/usr/bin/env python
# ruff: noqa: C408  # dict() with keyword args is the readable form for step tables
"""Drive the interactive CLI through every menu option (walkthrough).

Spawns ``python -m cli.main`` as a subprocess with a piped stdin/stdout and
feeds input only when the expected prompt marker appears on stdout, then
verifies each menu action produced its expected output marker. This makes
the walkthrough robust to slow LLM calls: an input is never sent before the
prompt it belongs to is actually on screen.

Usage:
    python scripts/cli_walkthrough.py --pass nav    # menu navigation only (fast, no LLM)
    python scripts/cli_walkthrough.py --pass full   # full LLM pipeline walkthrough (slow)
    python scripts/cli_walkthrough.py --pass all    # both (default)

Requires an LLM on :8080 (or :1234) for the ``full`` pass and a reachable
``https://automationexercise.com/``. Exit code is non-zero if any step fails.

Full output is logged to scripts/archive/cli_snapshots/cli_walkthrough_<ts>.log
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = REPO_ROOT / "scripts" / "archive" / "cli_snapshots"
CLI_CMD = [sys.executable, "-u", "-m", "cli.main"]

# ── User story used by the full pass (2 criteria → fast LLM calls) ─────────
# NOTE: no blank lines — the CLI paste reader terminates on the first empty
# line, so any blank line would truncate the story mid-way. The trailing
# newline provides that terminating empty line when the story is pasted.

STORY = (
    "## User Story\n"
    "As a shopper I want to view product details on the store\n"
    "## Acceptance Criteria\n"
    "1. [navigate] From the home page, click on a product name link\n"
    "2. [assert] The product detail page shows the product name and price\n"
    "(Total: 2 criteria)\n"
)


class CliDriver:
    """Spawn the CLI and drive it marker-by-marker."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.buffer = ""
        self.cursor = 0
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[Any] | None = None
        self.failures: list[str] = []

    def _reader(self, stream: Any) -> None:
        # buffering=1 → line-buffered so the snapshot log is written live
        with open(self.log_path, "a", encoding="utf-8", buffering=1) as log:
            # NOTE: read1() is critical on Windows — BufferedReader.read()
            # blocks until its buffer fills or EOF, so pipe output would only
            # arrive when the child exits. read1() returns what is available
            # immediately, which is what an interactive driver needs.
            while True:
                try:
                    chunk = stream.read1(4096)
                except ValueError:
                    break  # closed
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                with self.lock:
                    self.buffer += text
                log.write(text)

    def start(self) -> None:
        env = dict(os.environ)
        env["MSYSTEM"] = "MINGW64"  # force line-based (Git Bash) input path
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        self.log_path.write_text("", encoding="utf-8")
        self.proc = subprocess.Popen(
            CLI_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(REPO_ROOT),
            env=env,
        )
        threading.Thread(target=self._reader, args=(self.proc.stdout,), daemon=True).start()

    def send(self, text: str) -> None:
        assert self.proc and self.proc.stdin, "driver not started"
        # Windows quirk: the child's input() treats each pipe write as one line
        # even when the write contains embedded newlines, so multi-line content
        # (e.g. the pasted user story) must be written one line per write call.
        for line in text.split("\n"):
            self.proc.stdin.write((line + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _scan(self, marker: str) -> str | None:
        """Return text since last scan up to *marker*; advance cursor on match."""
        with self.lock:
            idx = self.buffer.find(marker, self.cursor)
            if idx == -1:
                return None
            chunk = self.buffer[self.cursor : idx]
            self.cursor = idx + len(marker)
            return chunk

    def wait_for(self, marker: str, timeout: float) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self._scan(marker)
            if chunk is not None:
                return chunk
            if self.proc and self.proc.poll() is not None and self.cursor >= len(self.buffer):
                return None  # process exited with no more output
            time.sleep(0.2)
        return None

    def wait_for_any(self, markers: list[str], timeout: float) -> tuple[str, str] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for m in markers:
                chunk = self._scan(m)
                if chunk is not None:
                    return m, chunk
            if self.proc and self.proc.poll() is not None and self.cursor >= len(self.buffer):
                return None
            time.sleep(0.2)
        return None

    def stop(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass


# ── Step definitions ──────────────────────────────────────────────────────

# Each step: dict(prompt=marker_to_wait_before_sending, send=text, expect=marker,
#                expect_any=[...], timeout=seconds)
# When `send` is None, the step only waits for `expect` (no input consumed).

NAV_STEPS: list[dict[str, Any]] = [
    # 1. Configure LLM → OpenAI-Compatible (local) → default URL + model
    dict(prompt="Enter selection:", send="1", expect="LLM Configuration", timeout=30),
    dict(prompt="Enter selection:", send="3", expect="Base URL", timeout=30),
    dict(send="", expect="Select model", timeout=60),  # prompt already on screen
    dict(send="", expect="✓ Provider: openai-local", timeout=30),
    # 2. Load Existing Generated Tests → first package
    dict(prompt="Enter selection:", send="3", expect="Saved Test Packages", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="✓ Loaded package:", timeout=60),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # 3. Show Package Metadata
    dict(prompt="Enter selection:", send="4", expect="Press Enter to continue...", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # 4. View Saved Package Diagnostics
    dict(prompt="Enter selection:", send="6", expect="Press Enter to continue...", timeout=60),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # 5. Clear Loaded Package
    dict(prompt="Enter selection:", send="7", expect="Press Enter to continue...", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # 6. Enter User Story (paste)
    dict(prompt="Enter selection:", send="2", expect="User Story Input", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="Paste your user story", timeout=30),
    dict(prompt="Paste your user story", send=STORY, expect="Enter selection:", timeout=60),
    # 7. Enter Target URLs → baseline
    dict(prompt="Enter selection:", send="2", expect="Target URLs", timeout=30),
    dict(prompt="Enter selection:", send="2", expect="Baseline loaded.", timeout=30),
    # 8. Consent Mode → auto-dismiss (opens a submenu, then pick option)
    dict(prompt="Enter selection:", send="3", expect="Enter selection:", timeout=30),
    dict(send="1", expect="Consent mode set", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # 9. POM Mode → ON
    dict(prompt="Enter selection:", send="4", expect="POM Mode: ON", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # 10. Configure Authentication (credentials)
    dict(prompt="Enter selection:", send="5", expect="Authentication (optional)", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="Profile label", timeout=30),
    dict(prompt="Profile label", send="Test user", expect="Username:", timeout=30),
    dict(prompt="Username:", send="demo", expect="Password:", timeout=30),
    dict(prompt="Password:", send="secret", expect="✓ Credential profile", timeout=30),
    # 11. Configure Journey (navigate + scrape steps)
    dict(prompt="Enter selection:", send="6", expect="Journey Builder (optional)", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="Define the steps", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="navigate", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="Description for this navigate step", timeout=30),
    dict(prompt="Description for this navigate step", send="Go to home", expect="URL to navigate to:", timeout=30),
    dict(
        prompt="URL to navigate to:", send="https://automationexercise.com/", expect="✓ Added navigate step", timeout=30
    ),
    dict(prompt="Enter selection:", send="1", expect="scrape", timeout=30),
    dict(prompt="Enter selection:", send="5", expect="Description for this scrape step", timeout=30),
    dict(prompt="Description for this scrape step", send="Capture products", expect="✓ Added scrape step", timeout=30),
    dict(prompt="Enter selection:", send="2", expect="✓ Journey configured with 2 step(s)", timeout=30),
    # 12. POM Mode → OFF (toggle back)
    dict(prompt="Enter selection:", send="4", expect="POM Mode: OFF", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # 13. Quit
    dict(prompt="Enter selection:", send="Q", expect="Quitting without saving", timeout=30),
]

FULL_STEPS: list[dict[str, Any]] = [
    # LLM config
    dict(prompt="Enter selection:", send="1", expect="LLM Configuration", timeout=30),
    dict(prompt="Enter selection:", send="3", expect="Base URL", timeout=30),
    dict(send="", expect="Select model", timeout=60),
    dict(send="", expect="✓ Provider: openai-local", timeout=30),
    # Story
    dict(prompt="Enter selection:", send="2", expect="User Story Input", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="Paste your user story", timeout=30),
    dict(prompt="Paste your user story", send=STORY, expect="Enter selection:", timeout=60),
    # URLs
    dict(prompt="Enter selection:", send="2", expect="Target URLs", timeout=30),
    dict(prompt="Enter selection:", send="2", expect="Baseline loaded.", timeout=30),
    # Consent / POM
    dict(prompt="Enter selection:", send="3", expect="Enter selection:", timeout=30),
    dict(send="1", expect="Consent mode set", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    dict(prompt="Enter selection:", send="4", expect="POM Mode: ON", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # Auth skip / Journey skip
    dict(prompt="Enter selection:", send="5", expect="Authentication (optional)", timeout=30),
    dict(prompt="Enter selection:", send="2", expect="Skipping authentication setup.", timeout=30),
    dict(prompt="Enter selection:", send="6", expect="Journey Builder (optional)", timeout=30),
    dict(prompt="Enter selection:", send="2", expect="Skipping journey builder", timeout=30),
    # Build Living Test Plan → sign off
    dict(prompt="Enter selection:", send="7", expect="Plan built:", timeout=900),
    dict(prompt="Enter selection:", send="2", expect="Tester name:", timeout=30),
    dict(prompt="Tester name:", send="", expect="Sign-off notes", timeout=30),
    dict(prompt="Sign-off notes", send="", expect="Plan signed off.", timeout=30),
    # Expand into Test Rows → confirm
    dict(prompt="Enter selection:", send="8", expect="Confirm all rows", timeout=900),
    dict(prompt="Enter selection:", send="3", expect="All test rows confirmed.", timeout=30),
    # Run Intelligent Pipeline (LLM + scrape + generation)
    dict(
        prompt="Enter selection:",
        send="9",
        expect_any=["✓ Tests saved to:", "✗ Pipeline failed", "Pipeline failed", "All placeholders resolved"],
        timeout=1800,
    ),
    # Post-pipeline views
    dict(prompt="Enter selection:", send="10", expect="Generated Code", timeout=30),
    dict(prompt="Enter selection:", send="11", expect="Generated Skeleton", timeout=30),
    dict(prompt="Enter selection:", send="12", expect="Scrape Summary", timeout=30),
    # Run Generated Tests + Re-run Failed Only
    dict(
        prompt="Enter selection:",
        send="13",
        expect_any=["All tests passed!", "Tests completed with return code"],
        timeout=900,
    ),
    dict(
        prompt="Enter selection:",
        send="14",
        expect_any=["All tests passed!", "Tests completed with return code"],
        timeout=600,
    ),
    # Reports
    dict(prompt="Enter selection:", send="15", expect="Local report:", timeout=120),
    dict(prompt="Enter selection:", send="16", expect="Local report (", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="Opening report", timeout=30),
    dict(send=None, expect="Enter selection:", timeout=30),  # preview ends, no input
    # Diagnostics / bug report / repair / self-heal
    dict(prompt="Enter selection:", send="17", expect="Failure Diagnostics", timeout=30),
    dict(
        prompt="Enter selection:",
        send="18",
        expect_any=["No failures — nothing to report.", "Bug report saved to:"],
        timeout=900,
    ),
    dict(
        prompt="Enter selection:",
        send="19",
        expect_any=["No locator failures found", "Which failure to repair?"],
        timeout=60,
    ),
    dict(prompt="Which failure to repair?", send="q", expect="Enter selection:", timeout=15, optional=True),
    dict(
        prompt="Enter selection:",
        send="20",
        expect_any=["nothing to heal", "Run tests now?", "All failures fixed!"],
        timeout=1200,
    ),
    dict(prompt="Run tests now?", send="n", expect="Enter selection:", timeout=15, optional=True),
    # Export / bundle / evidence
    dict(prompt="Enter selection:", send="21", expect="Flat (inline locators)", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="Press Enter to continue...", timeout=120),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    dict(prompt="Enter selection:", send="22", expect="Press Enter to continue...", timeout=120),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    dict(prompt="Enter selection:", send="23", expect="Press Enter to continue...", timeout=120),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # Load existing package (the one just created)
    dict(prompt="Enter selection:", send="24", expect="Saved Test Packages", timeout=30),
    dict(prompt="Enter selection:", send="1", expect="✓ Loaded package:", timeout=60),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # Package commands
    dict(prompt="Enter selection:", send="25", expect="Press Enter to continue...", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    dict(
        prompt="Enter selection:",
        send="26",
        expect_any=["Show raw pytest output?", "All tests passed!", "Tests completed with return code"],
        timeout=900,
    ),
    dict(prompt="Show raw pytest output?", send="n", expect="Enter selection:", timeout=15, optional=True),
    dict(prompt="Enter selection:", send="27", expect="Press Enter to continue...", timeout=60),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    dict(prompt="Enter selection:", send="28", expect="Press Enter to continue...", timeout=30),
    dict(prompt="Press Enter to continue...", send="", expect="Enter selection:", timeout=30),
    # Save & Exit — note: after Clear Loaded Package the menu reverts to the
    # non-package form, so Save & Exit is item 25 (not 29).
    dict(prompt="Enter selection:", send="25", expect="Session saved. Goodbye!", timeout=30),
]


# ── Runner ────────────────────────────────────────────────────────────────


def run_steps(driver: CliDriver, steps: list[dict[str, Any]], label: str) -> int:
    """Execute steps; returns number of failures.

    Marker semantics: a step's ``prompt`` is the marker that tells us it is OK
    to send now. If the previous step's ``expect`` already consumed that exact
    marker, the prompt is already on screen and we send immediately (no wait).
    """
    print(f"\n=== {label}: {len(steps)} steps ===", flush=True)
    failed = 0
    last_marker: str | None = None
    for i, step in enumerate(steps, 1):
        prompt = step.get("prompt")
        send_text = step.get("send")
        expect = step.get("expect")
        expect_any = step.get("expect_any")
        timeout = float(step.get("timeout", 60))
        name = f"{i:02d}"

        ok = True
        detail = ""
        if prompt:
            if prompt != last_marker:
                if not driver.wait_for(prompt, timeout):
                    if step.get("optional"):
                        print(f"  [SKIP] {name}  (optional prompt '{prompt}' never appeared)", flush=True)
                        continue
                    ok = False
                    detail = f"prompt '{prompt}' not seen (timeout {timeout:.0f}s)"
            if ok and send_text is not None:
                driver.send(send_text)
        elif send_text is not None:
            driver.send(send_text)

        if ok and expect_any:
            hit, _ = driver.wait_for_any(expect_any, timeout) or (None, "")
            if hit is None:
                ok = False
                detail = f"none of {expect_any} seen (timeout {timeout:.0f}s)"
            else:
                last_marker = hit
        elif ok and expect:
            if not driver.wait_for(expect, timeout):
                ok = False
                detail = f"expected '{expect}' not seen (timeout {timeout:.0f}s)"
            else:
                last_marker = expect

        if not ok:
            last_marker = None  # state unknown — force prompt waits again

        if ok:
            print(f"  [PASS] {name}", flush=True)
        else:
            failed += 1
            print(f"  [FAIL] {name}  {detail}", flush=True)
            if prompt:
                print(f"         sent: {send_text!r}")

    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pass",
        dest="pass_name",
        choices=["nav", "full", "all"],
        default="all",
        help="which walkthrough to run (default: all)",
    )
    args = parser.parse_args()

    # Driver's own stdout may be cp1252 on Windows — force UTF-8 so expected
    # markers (✓, —) can be echoed in FAIL/PASS lines.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = SNAPSHOT_DIR / f"cli_walkthrough_{ts}.log"
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    passes = ["nav", "full"] if args.pass_name == "all" else [args.pass_name]
    total_failed = 0

    for pass_name in passes:
        steps = NAV_STEPS if pass_name == "nav" else FULL_STEPS
        driver = CliDriver(log_path)
        driver.start()
        try:
            total_failed += run_steps(driver, steps, f"PASS {pass_name.upper()}")
            if driver.proc and driver.proc.poll() is None:
                driver.stop()
        finally:
            driver.stop()

    print(f"\n===== Walkthrough complete: {total_failed} failed step(s) =====", flush=True)
    print(f"Full log: {log_path}", flush=True)
    if total_failed:
        print("Tip: check the log for the last prompts before the failure.")
    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
