#!/usr/bin/env python3
"""Phase 7a local self-test — exercise the Docker action exactly the way
``.github/workflows/ci-cd-action.yml`` does, without GitHub.

Builds ``Dockerfile.action`` and runs the container twice with the same env
surface GitHub sets for Docker actions (``INPUT_*``, ``GITHUB_WORKSPACE``,
``GITHUB_OUTPUT``), with the repo mounted at ``/github/workspace``:

  1. generate-only + self-test  -> hermetic mock site + fake LLM inside the
     container; asserts exit 0, driver JSON contract, persisted package.
  2. run-existing + self-test    -> pytest --junitxml + AI-028 evidence JUnit
     + report against the generated package; asserts JUnit well-formedness,
     report payload shape (the 7b comment shape), exit 0 (referee).

Usage::

    python scripts/ci_action_selftest.py             # build + run + assert
    python scripts/ci_action_selftest.py --skip-build
    python scripts/ci_action_selftest.py --keep      # keep .ai-test-workspace/

Exit codes: 0 all green, 1 a gate failed, 2 usage/build error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE = "ai-test-generator-action"
MOUNT = "/github/workspace"
WORKSPACE_NAME = "ai-test-workspace"
STORY = (
    "As a customer, I want to browse products on the store, add them to my cart, "
    "proceed to checkout, and place an order."
)

GATES: list[tuple[str, bool, str]] = []


def gate(name: str, passed: bool, detail: str = "") -> None:
    GATES.append((name, passed, detail))
    print(f"  [{'OK' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _host_mount_dir() -> Path:
    return PROJECT_ROOT / WORKSPACE_NAME


def _win_path(p: Path) -> str:
    return str(p).replace("\\", "/")


def build_image() -> None:
    print(f"\n=== Build image: {IMAGE} (docker build -f Dockerfile.action .) ===")
    proc = subprocess.run(
        ["docker", "build", "-f", "Dockerfile.action", "-t", IMAGE, "."],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if proc.returncode != 0:
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:], file=sys.stderr)
        raise SystemExit("docker build failed")
    print("image built")


def _dump_results() -> None:
    """Print any entrypoint/driver artifacts on failure for diagnosis."""
    results = _host_mount_dir() / "results"
    for path in sorted(results.glob("*")) if results.exists() else []:
        if path.is_file() and path.suffix in {".log", ".err", ".json"}:
            print(f"--- {path.name} ---")
            try:
                print(path.read_text(encoding="utf-8")[-2500:])
            except OSError as exc:
                print(f"(unreadable: {exc})")


def docker_run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{_win_path(PROJECT_ROOT)}:{MOUNT}",
    ]
    for key, value in env.items():
        cmd += ["-e", f"{key}={value}"]
    cmd.append(IMAGE)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=1200)


def run_generate_only() -> int:
    print("\n=== Gate: generate-only (hermetic mock + fake LLM) ===")
    results = _host_mount_dir() / "results"
    results.mkdir(parents=True, exist_ok=True)
    env = {
        "INPUT_MODE": "generate-only",
        "INPUT_SELF_TEST": "true",
        "INPUT_STORY": STORY,
        "INPUT_URL": "http://127.0.0.1:8781/index.html",
        "INPUT_WORKSPACE": WORKSPACE_NAME,
        "GITHUB_WORKSPACE": MOUNT,
        "GITHUB_OUTPUT": f"{MOUNT}/{WORKSPACE_NAME}/results/github-output.txt",
    }
    proc = docker_run(env)
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        print(proc.stderr[-3000:], file=sys.stderr)
        _dump_results()
    gate("generate-only exits 0", proc.returncode == 0, f"rc={proc.returncode}")

    summary_path = results / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        gate("driver JSON contract ok", summary.get("ok") is True and summary.get("exit_code") == 0, str(summary))
        gate("test_count >= 1", summary.get("test_count", 0) >= 1, f"{summary.get('test_count')} tests")
    else:
        gate("driver JSON contract ok", False, "summary.json missing")

    pkgs = (
        sorted((_host_mount_dir() / "generated_tests").rglob("test_*.py"))
        if (_host_mount_dir() / "generated_tests").exists()
        else []
    )
    gate("package persisted to mounted workspace", len(pkgs) >= 1, f"{len(pkgs)} test file(s)")
    return proc.returncode


def run_existing() -> int:
    print("\n=== Gate: run-existing (generated package -> pytest + JUnit) ===")
    results = _host_mount_dir() / "results"
    env = {
        "INPUT_MODE": "run-existing",
        "INPUT_SELF_TEST": "true",
        "INPUT_TESTS": f"{WORKSPACE_NAME}/generated_tests",
        "INPUT_WORKSPACE": WORKSPACE_NAME,
        "GITHUB_WORKSPACE": MOUNT,
        "GITHUB_OUTPUT": f"{MOUNT}/{WORKSPACE_NAME}/results/github-output.txt",
    }
    proc = docker_run(env)
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        print(proc.stderr[-3000:], file=sys.stderr)
        _dump_results()
    gate("run-existing exits 0 (referee: tests pass)", proc.returncode == 0, f"rc={proc.returncode}")

    junit = results / "junit.xml"
    if junit.exists():
        try:
            root = ET.parse(junit).getroot()
            suites = [root] if root.tag == "testsuite" else list(root)
            total = sum(int(s.get("tests", 0) or 0) for s in suites)
            failures = sum(int(s.get("failures", 0) or 0) for s in suites)
            gate("junit.xml well-formed with tests", total >= 1, f"{total} tests, {failures} failed")
        except ET.ParseError as exc:
            gate("junit.xml well-formed with tests", False, str(exc))
    else:
        gate("junit.xml well-formed with tests", False, "junit.xml missing")

    ev = results / "junit-evidence.xml"
    if ev.exists():
        try:
            ev_root = ET.parse(ev).getroot()
            ev_suites = [ev_root] if ev_root.tag == "testsuite" else list(ev_root)
            ev_total = sum(int(s.get("tests", 0) or 0) for s in ev_suites)
            gate("evidence junit.xml (AI-028) well-formed", ev_total >= 1, f"{ev_total} tests")
        except ET.ParseError as exc:
            gate("evidence junit.xml (AI-028) well-formed", False, str(exc))
    else:
        gate("evidence junit.xml (AI-028) well-formed", False, "junit-evidence.xml missing")

    report_path = results / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        ok = (
            report.get("mode") == "run-existing"
            and isinstance(report.get("tests"), dict)
            and report["tests"].get("total", 0) >= 1
            and isinstance(report.get("repair_candidates"), list)
            and isinstance(report.get("failed_tests"), list)
        )
        gate("report.json payload shape (7b comment shape)", ok, str(report.get("tests")))
        md = results / "report.md"
        gate(
            "report.md comment body",
            md.exists() and md.read_text(encoding="utf-8").startswith("## 🤖 AI Test Generator"),
            "markdown summary present" if md.exists() else "report.md missing",
        )
    else:
        gate("report.json payload shape (7b comment shape)", False, "report.json missing")
    return proc.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Docker self-test for the Phase 7a CI action.")
    parser.add_argument("--skip-build", action="store_true", help="Reuse an already-built image")
    parser.add_argument("--keep", action="store_true", help="Keep .ai-test-workspace/ on success")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.skip_build:
        build_image()

    run_generate_only()
    run_existing()

    passed = sum(1 for _, ok, _ in GATES if ok)
    print(f"\n{'=' * 60}")
    print(f"ACTION SELF-TEST: {passed}/{len(GATES)} gates passed")
    print(f"{'=' * 60}")

    if not args.keep and _host_mount_dir().exists():
        shutil.rmtree(_host_mount_dir(), ignore_errors=True)
        print(f"[CLEANED] {WORKSPACE_NAME}/ (use --keep to retain)")

    if passed < len(GATES):
        print("\nVERDICT: FAIL — see failing gates above.")
        return 1
    print("\nVERDICT: PASS — the action image generates and runs hermetically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
