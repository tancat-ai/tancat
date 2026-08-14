#!/usr/bin/env python3
"""GitLab REST platform adapter (Phase 7c) — the GitLab surface behind the
spec §5.5 platform seam, mirroring ``ci/platform/github.py``.

Everything GitLab-specific that the action does — find/create/edit the MR
note, post slash-command replies, fetch the latest slash command — goes
through this adapter. The report/adapt/flaky cores stay GitLab-free and are
reused unchanged (the §5.5 insurance).

MR-note posting is **idempotent**: one note per marker (``## 🤖 AI Test
Generator``), looked up and edited, never duplicated — the same pattern the
GitHub adapter uses, so a repo that moves between platforms keeps one comment
thread per run.

GitLab REST differs from GitHub in the shapes the GitHub adapter owns:
- notes live under ``/projects/:id/merge_requests/:iid/notes`` (not
  ``/issues/:n/comments``)
- the note body field is ``body`` on create and edit alike
- edits are **PUT**, not PATCH
- auth is ``PRIVATE-TOKEN: <pat>`` (a PAT with ``api`` scope)
- the project id is numeric **or** a URL-encoded path (``group%2Fproject``)

Stdlib urllib only (runs inside the action image and anywhere). The base URL
is injectable so unit tests point it at a local mock server and the local
Docker self-test verifies real POST/PUT traffic hermetically.

Usage::

    from ci.platform.gitlab import GitLabClient

    client = GitLabClient(token=os.environ["GITLAB_TOKEN"], project="group/proj", mr_iid=12)
    client.post_note(body, marker="## 🤖 AI Test Generator")

    # CLI (used by the action entrypoint + the .gitlab-ci.yml slash job):
    python ci/platform/gitlab.py --body-file comment.md --marker "## 🤖 ..."
    python ci/platform/gitlab.py --latest-command   # newest /adapt|/ignore note body
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class GitLabError(RuntimeError):
    """Raised on API failures (auth, not-found, rate-limit, transport)."""


MARKER = "## 🤖 AI Test Generator"
_SITE_RE = re.compile(r"\*\*Site:\*\*\s*(https?://[^\s·]+)")
# Mirror of scripts/ci_slash_commands._COMMAND_RE — the adapter only *locates*
# the latest command (the action's slash-command mode re-parses canonically),
# and it must not import the scripts package: as a standalone CLI its
# sys.path[0] is ci/platform/, not the repo root. Matches per line, exactly
# like the core's parse_slash_command (no re.MULTILINE — ^ and $ anchor to
# each split line).
_SLASH_RE = re.compile(r"^\s*/(?P<cmd>adapt|ignore)\s+(?P<test>\S+)\s*$", re.IGNORECASE)


class GitLabClient:
    """Thin GitLab REST client (MR notes scope only)."""

    def __init__(
        self,
        token: str = "",
        base_url: str = "https://gitlab.com/api/v4",
        timeout: float = 30.0,
        project: str = "",
        mr_iid: int = 0,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.project = project
        self.mr_iid = mr_iid

    # -- transport -----------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise GitLabError("no GITLAB_TOKEN — MR note posting requires a PAT with api scope")
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("PRIVATE-TOKEN", self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except OSError:
                pass
            raise GitLabError(f"GitLab API {method} {path} -> {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise GitLabError(f"GitLab API {method} {path} unreachable: {exc.reason}") from exc

    def _require_mr(self) -> None:
        if not self.project or not self.mr_iid:
            raise GitLabError("project + mr_iid required (set by the action from CI_PROJECT_PATH/CI_MERGE_REQUEST_IID)")

    @staticmethod
    def _encode_project(project: str) -> str:
        """Project id may be numeric or a path like ``group/project`` — the
        REST path needs the path form URL-encoded (``group%2Fproject``)."""
        if project.isdigit():
            return project
        return urllib.parse.quote(project, safe="")

    def _notes_path(self, project: str, mr_iid: int) -> str:
        return f"/projects/{self._encode_project(project)}/merge_requests/{mr_iid}/notes"

    # -- MR notes --------------------------------------------------------------

    def list_mr_notes(self, project: str = "", mr_iid: int = 0) -> list[dict[str, Any]]:
        project = project or self.project
        mr_iid = mr_iid or self.mr_iid
        self._require_mr()
        notes: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._request(
                "GET",
                f"{self._notes_path(project, mr_iid)}?per_page=100&page={page}",
            )
            if not isinstance(batch, list):
                break
            notes.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return notes

    def find_note_by_marker(self, marker: str = MARKER, project: str = "", mr_iid: int = 0) -> dict[str, Any] | None:
        """Return the existing MR note containing *marker*, or None."""
        for note in self.list_mr_notes(project, mr_iid):
            if marker in note.get("body", ""):
                return note
        return None

    def create_note(self, body: str, project: str = "", mr_iid: int = 0) -> dict[str, Any]:
        project = project or self.project
        mr_iid = mr_iid or self.mr_iid
        self._require_mr()
        return self._request("POST", self._notes_path(project, mr_iid), {"body": body})

    def edit_note(self, note_id: int, body: str, project: str = "", mr_iid: int = 0) -> dict[str, Any]:
        project = project or self.project
        mr_iid = mr_iid or self.mr_iid
        self._require_mr()
        return self._request(
            "PUT",
            f"{self._notes_path(project, mr_iid)}/{note_id}",
            {"body": body},
        )

    def post_note(self, body: str, marker: str = MARKER, project: str = "", mr_iid: int = 0) -> dict[str, Any]:
        """Idempotent create-or-edit: update the marker note, never duplicate."""
        existing = self.find_note_by_marker(marker, project, mr_iid)
        if existing is not None:
            return self.edit_note(int(existing["id"]), body, project, mr_iid)
        return self.create_note(body, project, mr_iid)

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def extract_url_from_comment(body: str) -> str | None:
        """Pull the site URL out of a §6 comment (used by slash-command runs)."""
        match = _SITE_RE.search(body or "")
        return match.group(1) if match else None

    def latest_slash_command_body(self, project: str = "", mr_iid: int = 0) -> str | None:
        """Body of the most recent MR note containing a ``/adapt`` or
        ``/ignore`` command (used by the .gitlab-ci.yml slash-command job),
        or None when no command has been posted yet."""
        for note in reversed(self.list_mr_notes(project, mr_iid)):
            body = note.get("body", "") or ""
            if any(_SLASH_RE.match(line) for line in body.splitlines()):
                return str(note["body"])
        return None


def client_from_env(env: dict[str, str] | None = None) -> GitLabClient:
    """Build a client from action env (GITLAB_TOKEN, project id/path, MR iid).

    Honors both the GitLab-runner-native names (``CI_PROJECT_ID`` /
    ``CI_PROJECT_PATH`` / ``CI_MERGE_REQUEST_IID`` / ``CI_API_V4_URL``) and
    explicit overrides (``GITLAB_TOKEN`` / ``GITLAB_PROJECT`` /
    ``GITLAB_MR_IID`` / ``GITLAB_API_URL``) so local runs and hermetic tests
    point at a mock API.
    """
    ctx: dict[str, str] = dict(os.environ) if env is None else env
    token = ctx.get("GITLAB_TOKEN", "")
    base_url = ctx.get("GITLAB_API_URL") or ctx.get("CI_API_V4_URL") or "https://gitlab.com/api/v4"
    project = ctx.get("GITLAB_PROJECT") or ctx.get("CI_PROJECT_ID") or ctx.get("CI_PROJECT_PATH", "")
    mr_iid = int(ctx.get("GITLAB_MR_IID") or ctx.get("CI_MERGE_REQUEST_IID") or 0)
    return GitLabClient(token=token, base_url=base_url, project=project, mr_iid=mr_iid)


def main(argv: list[str] | None = None) -> int:
    """CLI used by the action entrypoint + the .gitlab-ci.yml slash job.

    ``--body-file`` posts the payload idempotently (reads the body from a
    file — bodies contain newlines) and prints the resulting note id;
    ``--latest-command`` prints the newest /adapt|/ignore note body (empty
    when none exists) without posting.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="gitlab_note", description="Post an idempotent MR note / fetch the latest slash command."
    )
    parser.add_argument("--body-file", default="", help="Path to the markdown body (post mode)")
    parser.add_argument("--marker", default=MARKER, help="Marker for edit-not-duplicate")
    parser.add_argument(
        "--latest-command", action="store_true", help="Print the newest /adapt|/ignore note body, then exit"
    )
    parser.add_argument("--project", default="", help="Project id or group/project path (default: CI_PROJECT_ID/PATH)")
    parser.add_argument("--mr-iid", type=int, default=0, help="MR iid (default: CI_MERGE_REQUEST_IID)")
    parser.add_argument("--api-url", default="", help="API base URL override (tests/mocks)")
    args = parser.parse_args(argv)

    from pathlib import Path

    env = os.environ.copy()
    if args.project:
        env["GITLAB_PROJECT"] = args.project
    if args.mr_iid:
        env["GITLAB_MR_IID"] = str(args.mr_iid)
    if args.api_url:
        env["GITLAB_API_URL"] = args.api_url
    client = client_from_env(env)
    try:
        if args.latest_command:
            body = client.latest_slash_command_body()
            if body:
                print(body)
            return 0
        if not args.body_file:
            parser.error("either --body-file or --latest-command is required")
        body = Path(args.body_file).read_text(encoding="utf-8")
        result = client.post_note(body, marker=args.marker)
    except GitLabError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"posted MR note {result.get('id', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
