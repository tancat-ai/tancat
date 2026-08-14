#!/usr/bin/env python3
"""Phase 7 local self-test — exercise the Docker action exactly the way
``.github/workflows/ci-cd-action.yml`` does, without GitHub.

Builds ``Dockerfile.action`` and runs the container with the same env surface
GitHub sets for Docker actions (``INPUT_*``, ``GITHUB_WORKSPACE``,
``GITHUB_OUTPUT``), the repo mounted at ``/github/workspace``, plus a mock
GitHub API on the host so comment posting is verified against real HTTP
traffic (host.docker.internal — Docker Desktop NAT).

Gates:
  1. generate-only + self-test     -> exit 0, driver JSON contract, persisted package
  2. run-existing + self-test      -> junit + evidence junit + report shape, exit 0
  3. generate-and-run (cache miss) -> generates, seeds cache, pytest, comment payload
     + idempotent POST to the mock API (1 comment), cache_hit=false
  4. generate-and-run (cache hit)  -> no regeneration, cache_hit=true, comment EDITED
     (still 1 comment)
  5. slash-command /adapt          -> sabotage a locator, verified adaptation fixes it
     (patch -> re-run -> gate -> keep), reply POSTED (2 comments)
  6. slash-command /ignore         -> reply renders the .ai-test-ignore.yml entry (3 comments)

Usage::

    python scripts/ci_action_selftest.py             # build + run + assert
    python scripts/ci_action_selftest.py --skip-build
    python scripts/ci_action_selftest.py --keep      # keep .ai-test-workspace/

Exit codes: 0 all green, 1 a gate failed, 2 usage/build error.
"""

from __future__ import annotations

import argparse

# Windows consoles default to cp1252 — the self-test prints 🤖-bearing artifacts.
import io
import json
import re
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError, ValueError:
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE = "ai-test-generator-action"
MOUNT = "/github/workspace"
WORKSPACE_NAME = "ai-test-workspace"
MOCK_SITE = "http://127.0.0.1:8781/index.html"
STORY = (
    "As a customer, I want to browse products on the store, add them to my cart, "
    "proceed to checkout, and place an order."
)
PR_REPO = "org/repo"
PR_NUMBER = "42"
GITHUB_OUTPUT_PATH = f"{MOUNT}/{WORKSPACE_NAME}/results/github-output.txt"

GATES: list[tuple[str, bool, str]] = []


def gate(name: str, passed: bool, detail: str = "") -> None:
    GATES.append((name, passed, detail))
    print(f"  [{'OK' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _host_mount_dir() -> Path:
    return PROJECT_ROOT / WORKSPACE_NAME


def _results() -> Path:
    return _host_mount_dir() / "results"


def _win_path(p: Path) -> str:
    return str(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# Mock GitHub API (host-side) — the container posts comments here
# ---------------------------------------------------------------------------


class MockGitHubAPI:
    def __init__(self) -> None:
        self.comments: list[dict[str, object]] = []
        self.requests: list[dict[str, object]] = []
        self._server = ThreadingHTTPServer(("0.0.0.0", 0), self._handler_factory())
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _handler_factory(self) -> type[BaseHTTPRequestHandler]:
        store = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _record(self, body: bytes | None = None) -> None:
                store.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "body": json.loads(body.decode("utf-8")) if body else None,
                    }
                )

            def _send(self, payload: list | dict, code: int = 200) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _comment_id(self) -> int | None:
                m = re.search(r"/issues/comments/(\d+)", self.path)
                return int(m.group(1)) if m else None

            def do_GET(self) -> None:  # noqa: N802
                self._record()
                if "/issues/42/comments" in self.path:
                    self._send(store.comments)
                elif (cid := self._comment_id()) is not None:
                    found = next((c for c in store.comments if c["id"] == cid), None)
                    self._send(found if found is not None else {"message": "Not Found"}, 200 if found else 404)
                else:
                    self._send({"message": "Not Found"}, 404)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else None
                self._record(body)
                if "/issues/42/comments" in self.path:
                    payload = json.loads(body or b"{}")
                    comment = {"id": len(store.comments) + 1, "body": payload.get("body", "")}
                    store.comments.append(comment)
                    self._send(comment, 201)
                else:
                    self._send({"message": "Not Found"}, 404)

            def do_PATCH(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else None
                self._record(body)
                cid = self._comment_id()
                found = next((c for c in store.comments if c["id"] == cid), None) if cid else None
                if found is None:
                    self._send({"message": "Not Found"}, 404)
                    return
                payload = json.loads(body or b"{}")
                found["body"] = payload.get("body", "")
                self._send(found)

        return Handler

    def __enter__(self) -> MockGitHubAPI:
        self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------


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
    results = _results()
    for path in sorted(results.glob("*")) if results.exists() else []:
        if path.is_file() and path.suffix in {".log", ".err", ".json", ".md", ".txt"}:
            print(f"--- {path.name} ---")
            try:
                print(path.read_text(encoding="utf-8")[-2500:])
            except OSError as exc:
                print(f"(unreadable: {exc})")


def docker_run(env: dict[str, str], label: str = "") -> subprocess.CompletedProcess[str]:
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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        print(f"--- container stderr ({label}) ---")
        print(proc.stderr[-3000:])
        _dump_results()
    return proc


def _github_outputs() -> dict[str, str]:
    """Parse the outputs written by the last run (action-state.txt mirror of
    GITHUB_OUTPUT — always written, even when the runner injects no file)."""
    path = _results() / "action-state.txt"
    if not path.exists():
        path = _results() / "github-output.txt"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def _clear_github_output() -> None:
    for name in ("action-state.txt", "github-output.txt"):
        path = _results() / name
        if path.exists():
            path.write_text("", encoding="utf-8")


def _find_generated_package() -> Path | None:
    """Most recently modified generated package (gate 1 and gate 3 each generate)."""
    base = _host_mount_dir() / "generated_tests"
    if not base.exists():
        return None
    candidates = [p for p in base.iterdir() if p.is_dir() and list(p.rglob("test_*.py"))]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def run_generate_only() -> int:
    print("\n=== Gate: generate-only (hermetic mock + fake LLM) ===")
    results = _results()
    results.mkdir(parents=True, exist_ok=True)
    env = {
        "INPUT_MODE": "generate-only",
        "INPUT_SELF-TEST": "true",
        "INPUT_STORY": STORY,
        "INPUT_URL": MOCK_SITE,
        "INPUT_WORKSPACE": WORKSPACE_NAME,
        "GITHUB_WORKSPACE": MOUNT,
        "GITHUB_OUTPUT": GITHUB_OUTPUT_PATH,
    }
    proc = docker_run(env, "generate-only")
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
    results = _results()
    pkg = _find_generated_package()
    if pkg is None:
        gate("run-existing package present", False, "no generated package to run")
        return 1
    env = {
        "INPUT_MODE": "run-existing",
        "INPUT_SELF-TEST": "true",
        "INPUT_TESTS": f"{WORKSPACE_NAME}/generated_tests/{pkg.name}",
        "INPUT_WORKSPACE": WORKSPACE_NAME,
        "GITHUB_WORKSPACE": MOUNT,
        "GITHUB_OUTPUT": GITHUB_OUTPUT_PATH,
    }
    proc = docker_run(env, "run-existing")
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
        gate("report.json payload shape (comment shape)", ok, str(report.get("tests")))
        md = results / "report.md"
        gate(
            "report.md comment body",
            md.exists() and md.read_text(encoding="utf-8").startswith("## 🤖 AI Test Generator"),
            "markdown summary present" if md.exists() else "report.md missing",
        )
    else:
        gate("report.json payload shape (comment shape)", False, "report.json missing")
    return proc.returncode


def _generate_and_run_env(api_port: int) -> dict[str, str]:
    return {
        "INPUT_MODE": "generate-and-run",
        "INPUT_SELF-TEST": "true",
        "INPUT_STORY": STORY,
        "INPUT_URL": MOCK_SITE,
        "INPUT_WORKSPACE": WORKSPACE_NAME,
        "INPUT_CACHE": "true",
        "INPUT_CACHE-DIR": f"{WORKSPACE_NAME}/cache",
        "INPUT_COMMENT": "true",
        "INPUT_REPO": PR_REPO,
        "INPUT_PR-NUMBER": PR_NUMBER,
        "INPUT_GITHUB-TOKEN": "test-token",
        "GITHUB_API_URL": f"http://host.docker.internal:{api_port}",
        "GITHUB_WORKSPACE": MOUNT,
        "GITHUB_OUTPUT": GITHUB_OUTPUT_PATH,
    }


def run_generate_and_run(api: MockGitHubAPI) -> int:
    print("\n=== Gate: generate-and-run (cache miss -> generate + seed + comment) ===")
    _clear_github_output()
    env = _generate_and_run_env(api.port)
    proc = docker_run(env, "generate-and-run (miss)")
    outputs = _github_outputs()
    gate("generate-and-run exits 0 (referee: tests pass)", proc.returncode == 0, f"rc={proc.returncode}")
    gate("cache_hit=false on first run", outputs.get("cache_hit") == "false", str(outputs.get("cache_hit")))
    gate("cache_key emitted", len(outputs.get("cache_key", "")) == 64, outputs.get("cache_key", "")[:16])

    cache = _host_mount_dir() / "cache" / "packages"
    seeded = list(cache.rglob("test_*.py")) if cache.exists() else []
    gate("cache seeded with the generated package", len(seeded) >= 1, f"{len(seeded)} test file(s)")

    comment_md = _results() / "comment.md"
    if comment_md.exists():
        body = comment_md.read_text(encoding="utf-8")
        gate(
            "comment payload matches §6 shape",
            body.startswith("## 🤖 AI Test Generator — results")
            and "| Metric | Value |" in body
            and "**Mode:**" in body
            and "Repair candidates" in body,
            f"{len(body)} chars",
        )
    else:
        gate("comment payload matches §6 shape", False, "comment.md missing")

    gate("comment POSTED to the mock GitHub API", len(api.comments) == 1, f"{len(api.comments)} comment(s)")
    return proc.returncode


def run_cache_hit(api: MockGitHubAPI, gen_stamp: float) -> int:
    print("\n=== Gate: generate-and-run (cache hit -> reuse, no regeneration) ===")
    _clear_github_output()
    env = _generate_and_run_env(api.port)
    proc = docker_run(env, "generate-and-run (hit)")
    outputs = _github_outputs()
    gate("generate-and-run exits 0 on cache hit", proc.returncode == 0, f"rc={proc.returncode}")
    gate("cache_hit=true on second run", outputs.get("cache_hit") == "true", str(outputs.get("cache_hit")))

    # The generation was skipped: generate.json is untouched since the miss run.
    gen = _results() / "generate.json"
    stamp = gen.stat().st_mtime if gen.exists() else 0
    gate("no regeneration on cache hit (generate.json untouched)", abs(stamp - gen_stamp) < 1.0, "")

    gate(
        "comment EDITED, not duplicated (still 1 comment)",
        len(api.comments) == 1,
        f"{len(api.comments)} comment(s)",
    )
    return proc.returncode


def sabotage_cart_link() -> tuple[Path | None, str | None]:
    """Rewrite the Cart-link locator to a bogus selector so pytest fails with
    a LocatorNotFound-class error (the adapt engine's exact input)."""
    pkg = _find_generated_package()
    if pkg is None:
        return None, None
    for path in sorted(pkg.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines()):
            m = re.search(r"\.click\(\s*'([^']+)'\s*,\s*label='Cart link'", line)
            if not m:
                continue
            old = m.group(1)
            if old == 'a[href="/bogus.html"]':
                return None, None
            new_line = line.replace(old, 'a[href="/bogus.html"]', 1)
            text = text.replace(line, new_line, 1)
            path.write_text(text, encoding="utf-8")
            print(f"  sabotaged {path.name}:{i + 1} '{old}' -> 'a[href=\"/bogus.html\"]'")
            return path, old
    return None, None


def run_slash_adapt(api: MockGitHubAPI) -> int:
    print("\n=== Gate: slash-command /adapt (sabotage -> verified adaptation) ===")
    pkg = _find_generated_package()
    if pkg is None:
        gate("sabotage target present", False, "no generated package")
        return 1
    sabotaged, old_locator = sabotage_cart_link()
    gate("locator sabotaged", sabotaged is not None, f"{sabotaged}" if sabotaged else "no Cart-link step found")

    env = {
        "INPUT_MODE": "slash-command",
        "INPUT_SELF-TEST": "true",
        "INPUT_COMMENT-BODY": "/adapt test_04_go_to_cart_page",
        "INPUT_TESTS": f"{WORKSPACE_NAME}/generated_tests/{pkg.name}",
        "INPUT_WORKSPACE": WORKSPACE_NAME,
        "INPUT_REPO": PR_REPO,
        "INPUT_PR-NUMBER": PR_NUMBER,
        "INPUT_GITHUB-TOKEN": "test-token",
        "GITHUB_API_URL": f"http://host.docker.internal:{api.port}",
        "GITHUB_WORKSPACE": MOUNT,
        "GITHUB_OUTPUT": GITHUB_OUTPUT_PATH,
    }
    proc = docker_run(env, "slash-adapt")
    gate("slash-command /adapt exits 0", proc.returncode == 0, f"rc={proc.returncode}")

    adapt_report = _results() / "adaptation.json"
    if adapt_report.exists():
        report = json.loads(adapt_report.read_text(encoding="utf-8"))
        summary = report.get("summary", {})
        kept = report.get("kept", [])
        gate(
            "adaptation kept (assertion gate green)",
            summary.get("adapted", 0) >= 1 and summary.get("reverted", 0) == 0,
            f"{summary.get('adapted')} kept / {summary.get('reverted')} reverted",
        )
        gate(
            "patch replaced the bogus locator",
            any(k.get("new_locator") != 'a[href="/bogus.html"]' for k in kept),
            str([k.get("new_locator") for k in kept]),
        )
    else:
        gate("adaptation kept (assertion gate green)", False, "adaptation.json missing")

    # The sabotaged source must now use a real locator.
    if sabotaged is not None:
        text = sabotaged.read_text(encoding="utf-8")
        gate("source patched back to a real locator", 'a[href="/bogus.html"]' not in text, sabotaged.name)
    else:
        gate("source patched back to a real locator", False, "no source to check")

    gate(
        "adapt reply POSTED (2 comments total)",
        len(api.comments) == 2,
        f"{len(api.comments)} comment(s)",
    )
    return proc.returncode


def run_slash_ignore(api: MockGitHubAPI) -> int:
    print("\n=== Gate: slash-command /ignore (reply renders the YAML entry) ===")
    pkg = _find_generated_package()
    if pkg is None:
        gate("ignore target package present", False, "no generated package")
        return 1
    env = {
        "INPUT_MODE": "slash-command",
        "INPUT_SELF-TEST": "true",
        "INPUT_COMMENT-BODY": "/ignore test_05_verify_cart_product_details",
        "INPUT_TESTS": f"{WORKSPACE_NAME}/generated_tests/{pkg.name}",
        "INPUT_WORKSPACE": WORKSPACE_NAME,
        "INPUT_REPO": PR_REPO,
        "INPUT_PR-NUMBER": PR_NUMBER,
        "INPUT_GITHUB-TOKEN": "test-token",
        "GITHUB_API_URL": f"http://host.docker.internal:{api.port}",
        "GITHUB_WORKSPACE": MOUNT,
        "GITHUB_OUTPUT": GITHUB_OUTPUT_PATH,
    }
    proc = docker_run(env, "slash-ignore")
    gate("slash-command /ignore exits 0", proc.returncode == 0, f"rc={proc.returncode}")

    comment_md = _results() / "comment.md"
    if comment_md.exists():
        body = comment_md.read_text(encoding="utf-8")
        gate(
            "ignore reply renders the .ai-test-ignore.yml entry",
            ".ai-test-ignore.yml" in body and "test_05_verify_cart_product_details" in body and "reason" in body,
            f"{len(body)} chars",
        )
    else:
        gate("ignore reply renders the .ai-test-ignore.yml entry", False, "comment.md missing")

    gate("ignore reply POSTED (3 comments total)", len(api.comments) == 3, f"{len(api.comments)} comment(s)")
    return proc.returncode


# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Docker self-test for the Phase 7 CI action.")
    parser.add_argument("--skip-build", action="store_true", help="Reuse an already-built image")
    parser.add_argument("--keep", action="store_true", help="Keep .ai-test-workspace/ on success")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.skip_build:
        build_image()

    with MockGitHubAPI() as api:
        run_generate_only()
        run_existing()
        run_generate_and_run(api)
        gen = _results() / "generate.json"
        run_cache_hit(api, gen.stat().st_mtime if gen.exists() else 0.0)
        run_slash_adapt(api)
        run_slash_ignore(api)

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
    print("\nVERDICT: PASS — the action image generates, runs, caches, comments and adapts hermetically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
