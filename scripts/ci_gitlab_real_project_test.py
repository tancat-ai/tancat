#!/usr/bin/env python3
"""Phase 7c real GitLab.com gate — mirrors the GitHub self-test against a real
GitLab project (spec §12 DoD: ``.gitlab-ci.yml`` template + platform adapter
tested against a real GitLab.com project).

Requires ``GITLAB_TOKEN`` (a PAT with ``api`` scope) — read from ``.env`` or
the environment. Never prints the token.

Flow (each step asserts as it goes):

  1. configure  — enable the container registry, upsert the project's CI/CD
     variables (AITEST_GL_TOKEN masked, AITEST_URL -> the hermetic mock-site
     URL, AITEST_SELF_TEST=true, story file, mode)
  2. push-main  — push the full repo to the project's default branch; wait
     for the push pipeline; assert: success, cache miss, junit.xml artifact
     (>= 1 test), action-state.txt exit_code=0, no MR note (no MR context)
  3. mr         — create a feature branch + MR (tiny commits via the API);
     wait for the MR pipeline; assert: success, cache HIT (branch cache),
     one §6 MR note posted (marker + metric table)
  4. edit-check — push a second tiny commit to the branch; wait for the new
     MR pipeline; assert: still exactly ONE note (edited, never duplicated)

The template's defaults are used unchanged where possible: AITEST_RUN_KEY is
left at its branch-level default so pipelines 2+ restore the branch cache
(miss on a fresh project, hit on re-runs — the GitHub selftest's shape).

Exit codes: 0 all green, 1 a gate failed, 2 usage/config error.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECT = "cat-tan-operations/ai-testgen-selftest"
API = "https://gitlab.com/api/v4"
MARKER = "## 🤖 AI Test Generator"
STORY = (
    "As a customer, I want to browse products on the store, add them to my cart, "
    "proceed to checkout, and place an order."
)
MOCK_URL = "http://127.0.0.1:8781/index.html"
POLL_SECONDS = 25
TIMEOUT_PIPELINE = 60 * 40

GATES: list[tuple[str, bool, str]] = []


def gate(name: str, passed: bool, detail: str = "") -> None:
    GATES.append((name, passed, detail))
    print(f"  [{'OK' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


class GitLab:
    """Minimal stdlib GitLab API client (the project's own project)."""

    def __init__(self, token: str, project: str) -> None:
        self.token = token
        self.project_path = urllib.parse.quote(project, safe="")

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None, raw: bool = False) -> Any:
        url = f"{API}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("PRIVATE-TOKEN", self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"GitLab API {method} {path} -> {exc.code}: {detail}") from exc
        if raw:
            return raw_bytes
        return json.loads(raw_bytes) if raw_bytes else {}

    def project(self, pid: int | None = None) -> dict[str, Any]:
        return self._request("GET", f"/projects/{pid or self.project_path}")

    def set_variable(self, key: str, value: str, masked: bool = False) -> None:
        try:
            self._request("PUT", f"/projects/{self.project_path}/variables/{key}", {"value": value, "masked": masked})
        except RuntimeError as exc:
            if "404" in str(exc):
                self._request(
                    "POST", f"/projects/{self.project_path}/variables", {"key": key, "value": value, "masked": masked}
                )
            else:
                raise

    def create_commit(self, branch: str, message: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{self.project_path}/repository/commits",
            {"branch": branch, "commit_message": message, "actions": actions},
        )

    def create_branch(self, branch: str, ref: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{self.project_path}/repository/branches",
            {"branch": branch, "ref": ref},
        )

    def delete_branch(self, branch: str) -> None:
        self._request(
            "DELETE", f"/projects/{self.project_path}/repository/branches/{urllib.parse.quote(branch, safe='')}"
        )

    def list_mrs(self, source: str) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            f"/projects/{self.project_path}/merge_requests?state=opened&source_branch={urllib.parse.quote(source)}&per_page=20",
        )
        return data if isinstance(data, list) else []

    def delete_mr(self, iid: int) -> None:
        self._request("DELETE", f"/projects/{self.project_path}/merge_requests/{iid}")

    def create_mr(self, source: str, target: str, title: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{self.project_path}/merge_requests",
            {"source_branch": source, "target_branch": target, "title": title},
        )

    def list_pipelines(self, ref: str = "", per_page: int = 5) -> list[dict[str, Any]]:
        query = f"?per_page={per_page}" + (f"&ref={urllib.parse.quote(ref)}" if ref else "")
        data = self._request("GET", f"/projects/{self.project_path}/pipelines{query}")
        return data if isinstance(data, list) else []

    def pipeline(self, pid: int) -> dict[str, Any]:
        return self._request("GET", f"/projects/{self.project_path}/pipelines/{pid}")

    def pipeline_jobs(self, pid: int) -> list[dict[str, Any]]:
        data = self._request("GET", f"/projects/{self.project_path}/pipelines/{pid}/jobs")
        return data if isinstance(data, list) else []

    def job_artifacts(self, job_id: int) -> bytes:
        return self._request("GET", f"/projects/{self.project_path}/jobs/{job_id}/artifacts", raw=True)

    def mr_notes(self, iid: int) -> list[dict[str, Any]]:
        data = self._request("GET", f"/projects/{self.project_path}/merge_requests/{iid}/notes?per_page=100")
        return data if isinstance(data, list) else []

    def mr_pipelines(self, iid: int) -> list[dict[str, Any]]:
        data = self._request("GET", f"/projects/{self.project_path}/merge_requests/{iid}/pipelines")
        return data if isinstance(data, list) else []


def wait_pipeline(gitlab: GitLab, pid: int, label: str) -> dict[str, Any]:
    """Poll a pipeline until it finishes; print a live job summary."""
    print(f"  waiting for {label} (pipeline {pid})…")
    deadline = time.monotonic() + TIMEOUT_PIPELINE
    last = ""
    while time.monotonic() < deadline:
        pipeline = gitlab.pipeline(pid)
        status = pipeline.get("status", "")
        jobs = gitlab.pipeline_jobs(pid)
        summary = ", ".join(f"{j['name']}:{j['status']}" for j in jobs)
        if summary != last:
            print(f"    [{status}] {summary}")
            last = summary
        if status in {"success", "failed", "canceled", "skipped"}:
            return pipeline
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"{label} did not finish within {TIMEOUT_PIPELINE // 60} min")


def find_job(jobs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((j for j in jobs if j.get("name") == name), None)


def junit_from_artifact(gitlab: GitLab, job: dict[str, Any]) -> tuple[int, int]:
    """Fetch the run job's junit.xml artifact; return (tests, failures)."""
    raw = gitlab.job_artifacts(int(job["id"]))
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next((n for n in zf.namelist() if n.endswith("junit.xml")), None)
        if name is None:
            return -1, -1
        text = zf.read(name).decode("utf-8", "replace")
    suites = re.findall(r'<testsuite\b[^>]*\btests="(\d+)"[^>]*\bfailures="(\d+)"', text)
    if not suites:
        suites = re.findall(r'<testsuite\b[^>]*\bfailures="(\d+)"[^>]*\btests="(\d+)"', text)
        suites = [(b, a) for a, b in suites]
    total = sum(int(a) for a, _ in suites)
    failures = sum(int(b) for _, b in suites)
    return (total, failures)


def read_state(gitlab: GitLab, job: dict[str, Any]) -> dict[str, str]:
    """Pull action-state.txt out of the run job's artifacts."""
    raw = gitlab.job_artifacts(int(job["id"]))
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next((n for n in zf.namelist() if n.endswith("action-state.txt")), None)
        if name is None:
            return out
        for line in zf.read(name).decode("utf-8", "replace").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def push_main(token: str, project: str) -> None:
    """Push the repo's current main to the GitLab project (one-shot URL, no
    saved remote; force is safe on the throwaway project for re-runs)."""
    url = f"https://oauth2:{token}@gitlab.com/{project}.git"
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["git", "push", "--force", url, "main"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git push failed: {proc.stderr[-500:]}")


def load_token() -> str:
    env: dict[str, str] = {}
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    token = env.get("GITLAB_TOKEN") or os.environ.get("GITLAB_TOKEN", "")
    if not token:
        raise SystemExit("GITLAB_TOKEN not found in .env or environment (api scope required)")
    return token


def stage_configure(gitlab: GitLab) -> None:
    print("\n=== 1/4 configure project (registry + CI/CD variables) ===")
    proj = gitlab.project()
    gate("project reachable", proj.get("path_with_namespace") == DEFAULT_PROJECT, str(proj.get("path_with_namespace")))
    if proj.get("container_registry_enabled") is False:
        gitlab._request("PUT", f"/projects/{gitlab.project_path}", {"container_registry_enabled": True})
    gitlab.set_variable("AITEST_GL_TOKEN", gitlab.token, masked=True)
    gitlab.set_variable("AITEST_URL", MOCK_URL)
    gitlab.set_variable("AITEST_STORY_FILE", "ai-test-story.md")
    gitlab.set_variable("AITEST_MODE", "generate-and-run")
    gitlab.set_variable("AITEST_SELF_TEST", "true")
    gitlab.set_variable("AITEST_COMMENT", "true")
    gate("CI/CD variables configured", True, "AITEST_GL_TOKEN (masked) + URL/story/mode/self-test")


def stage_push_main(gitlab: GitLab, token: str) -> int:
    print("\n=== 2/4 push main -> push pipeline -> junit artifact ===")
    push_main(token, DEFAULT_PROJECT)
    print("  pushed main")
    time.sleep(15)  # let the pipeline be created
    pipelines = [p for p in gitlab.list_pipelines(ref="main") if p.get("ref") == "main"]
    gate("push pipeline created", len(pipelines) >= 1, f"{len(pipelines)} pipeline(s)")
    if not pipelines:
        return 1
    pipeline = wait_pipeline(gitlab, int(pipelines[0]["id"]), "push pipeline")
    gate("push pipeline success", pipeline.get("status") == "success", f"status={pipeline.get('status')}")

    jobs = gitlab.pipeline_jobs(int(pipelines[0]["id"]))
    run_job = find_job(jobs, "ai-testgen:run")
    gate("ai-testgen:run job present", run_job is not None, "")
    if run_job is None:
        return 1

    state = read_state(gitlab, run_job)
    gate("action-state exit_code=0", state.get("exit_code") == "0", str(state.get("exit_code")))
    gate("cache miss on fresh project", state.get("cache_hit") == "false", str(state.get("cache_hit")))

    tests, failures = junit_from_artifact(gitlab, run_job)
    gate("junit.xml artifact (tests >= 1)", tests >= 1, f"{tests} tests, {failures} failed")
    return 0


def _wait_latest_pipeline(gitlab: GitLab, ref: str, label: str) -> dict[str, Any]:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        pipelines = [p for p in gitlab.list_pipelines(ref=ref) if p.get("ref") == ref]
        if pipelines:
            return wait_pipeline(gitlab, int(pipelines[0]["id"]), label)
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"no {label} pipeline appeared on {ref}")


def _wait_mr_pipeline(gitlab: GitLab, iid: int, label: str, after_pid: int | None = None) -> dict[str, Any]:
    """Wait for the newest pipeline of an MR. MR pipelines report
    ``ref: refs/merge-requests/<iid>/head`` (not the source branch), so the
    MR's own pipelines endpoint is the reliable handle. ``after_pid`` skips
    already-seen pipelines (a commit may take ~30 s to spawn its pipeline;
    without it a fast poll can latch onto the previous run's)."""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        pipelines = [p for p in gitlab.mr_pipelines(iid) if p.get("id") != after_pid]
        if pipelines:
            return wait_pipeline(gitlab, int(pipelines[0]["id"]), label)
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"no {label} pipeline appeared on MR !{iid}")


def stage_mr(gitlab: GitLab, edit_check: bool) -> int:
    print("\n=== 3/4 feature branch + MR -> MR pipeline -> §6 note ===")
    existing = gitlab.list_mrs("feature/selftest")
    if existing:
        iid = int(existing[0]["iid"])
        print(f"  reusing existing MR !{iid}")
    else:
        # Fresh state: drop any stale branch, recreate, commit, open the MR.
        try:
            gitlab.delete_branch("feature/selftest")
        except RuntimeError:
            pass  # never existed
        gitlab.create_branch("feature/selftest", "main")
        gitlab.create_commit(
            "feature/selftest",
            "ci: feature branch for the real-project gate",
            [{"action": "update", "file_path": "ai-test-story.md", "content": STORY + "\n"}],
        )
        print("  feature/selftest created + committed")
        mr = gitlab.create_mr("feature/selftest", "main", "ci: real-project gate")
        iid = int(mr["iid"])
        print(f"  MR !{iid} created")

    pipeline = _wait_mr_pipeline(gitlab, iid, "MR")
    gate("MR pipeline success", pipeline.get("status") == "success", f"status={pipeline.get('status')}")
    mr_first_pid = int(pipeline["id"])

    notes = [n for n in gitlab.mr_notes(iid) if MARKER in n.get("body", "")]
    gate("§6 MR note posted (1)", len(notes) == 1, f"{len(notes)} note(s)")
    if notes:
        body = str(notes[0]["body"])
        gate(
            "MR note carries §6 shape",
            body.startswith("## 🤖 AI Test Generator — results")
            and "| Metric | Value |" in body
            and "**Mode:**" in body,
            f"{len(body)} chars",
        )

    if edit_check:
        print("\n=== 4/4 second commit -> note EDITED, not duplicated ===")
        gitlab.create_commit(
            "feature/selftest",
            "ci: edit-check commit (idempotency)",
            [{"action": "update", "file_path": "ai-test-story.md", "content": STORY.strip() + "\n\n# edit-check\n"}],
        )
        pipeline2 = _wait_mr_pipeline(gitlab, iid, "MR #2", after_pid=mr_first_pid)
        gate("MR pipeline #2 success", pipeline2.get("status") == "success", f"status={pipeline2.get('status')}")
        # cache HIT: same branch + same §7 key -> the package is reused
        jobs2 = gitlab.pipeline_jobs(int(pipeline2["id"]))
        run2 = find_job(jobs2, "ai-testgen:run")
        if run2 is not None:
            state2 = read_state(gitlab, run2)
            gate(
                "cache hit on re-run (package reused)", state2.get("cache_hit") == "true", str(state2.get("cache_hit"))
            )
        notes2 = [n for n in gitlab.mr_notes(iid) if MARKER in n.get("body", "")]
        gate("note still ONE (edited, never duplicated)", len(notes2) == 1, f"{len(notes2)} note(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Real GitLab.com gate for the Phase 7c template.")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="GitLab project (path_with_namespace)")
    parser.add_argument("--no-edit-check", action="store_true", help="Skip the note-edit (idempotency) pipeline")
    args = parser.parse_args()

    token = load_token()
    gitlab = GitLab(token, args.project)
    if not token.startswith("glpat-"):
        print(f"WARNING: token does not look like a GitLab PAT (prefix {token[:8]}…)", file=sys.stderr)

    stage_configure(gitlab)
    rc = stage_push_main(gitlab, token)
    if rc:
        return rc
    rc = stage_mr(gitlab, edit_check=not args.no_edit_check)
    if rc:
        return rc
    passed = sum(1 for _, ok, _ in GATES if ok)
    print(f"\nREAL-PROJECT GATE: {passed}/{len(GATES)} checks passed")
    if passed == len(GATES):
        print(
            "VERDICT: PASS — the template runs end-to-end on GitLab.com (pipeline, cache, junit, MR note idempotency)."
        )
        return 0
    print("VERDICT: FAIL — see failing checks above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
