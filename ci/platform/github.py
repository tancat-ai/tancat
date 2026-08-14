#!/usr/bin/env python3
"""GitHub REST platform adapter (Phase 7b) — the GitHub surface behind the
spec §5.5 platform seam.

Everything GitHub-specific that the action does — find/edit/create the PR
comment, post slash-command replies — goes through this adapter. The
report/adapt/flaky cores stay GitHub-free and are reused unchanged by the
GitLab adapter (7c).

Comment posting is **idempotent**: one comment per marker (``## 🤖 AI Test
Generator``), looked up and edited, never duplicated — the same pattern
``scripts/cli_walkthrough.py`` uses for markers.

Stdlib urllib only, so it runs inside the action image (and anywhere). The
base URL is injectable so unit tests point it at a local mock server and the
local Docker self-test can verify real POST/PATCH traffic hermetically.

Usage::

    from ci.platform.github import GitHubClient

    client = GitHubClient(token=os.environ["GITHUB_TOKEN"], repo="org/repo", pr_number=12)
    client.post_comment(body, marker="## 🤖 AI Test Generator")
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any


class GitHubError(RuntimeError):
    """Raised on API failures (auth, not-found, rate-limit, transport)."""


MARKER = "## 🤖 AI Test Generator"
_SITE_RE = re.compile(r"\*\*Site:\*\*\s*(https?://[^\s·]+)")


class GitHubClient:
    """Thin GitHub REST client (issue-comments scope only)."""

    def __init__(
        self,
        token: str = "",
        base_url: str = "https://api.github.com",
        timeout: float = 30.0,
        repo: str = "",
        pr_number: int = 0,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.repo = repo
        self.pr_number = pr_number

    # -- transport -----------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise GitHubError("no GITHUB_TOKEN — comment posting requires pull-requests: write")
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
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
            raise GitHubError(f"GitHub API {method} {path} -> {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"GitHub API {method} {path} unreachable: {exc.reason}") from exc

    def _require_pr(self) -> None:
        if not self.repo or not self.pr_number:
            raise GitHubError("repo + pr-number required (set by the action from GITHUB_REPOSITORY/GITHUB_PR_NUMBER)")

    # -- comments -------------------------------------------------------------

    def list_issue_comments(self, repo: str = "", pr_number: int = 0) -> list[dict[str, Any]]:
        repo = repo or self.repo
        pr_number = pr_number or self.pr_number
        self._require_pr()
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = self._request("GET", f"/repos/{repo}/issues/{pr_number}/comments?per_page=100&page={page}")
            if not isinstance(batch, list):
                break
            comments.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return comments

    def find_comment_by_marker(self, marker: str = MARKER, repo: str = "", pr_number: int = 0) -> dict[str, Any] | None:
        """Return the existing comment containing *marker*, or None."""
        for comment in self.list_issue_comments(repo, pr_number):
            if marker in comment.get("body", ""):
                return comment
        return None

    def create_comment(self, body: str, repo: str = "", pr_number: int = 0) -> dict[str, Any]:
        repo = repo or self.repo
        pr_number = pr_number or self.pr_number
        self._require_pr()
        return self._request("POST", f"/repos/{repo}/issues/{pr_number}/comments", {"body": body})

    def edit_comment(self, comment_id: int, body: str, repo: str = "") -> dict[str, Any]:
        repo = repo or self.repo
        if not repo:
            raise GitHubError("repo required to edit a comment")
        return self._request("PATCH", f"/repos/{repo}/issues/comments/{comment_id}", {"body": body})

    def post_comment(self, body: str, marker: str = MARKER, repo: str = "", pr_number: int = 0) -> dict[str, Any]:
        """Idempotent create-or-edit: update the marker comment, never duplicate."""
        existing = self.find_comment_by_marker(marker, repo, pr_number)
        if existing is not None:
            return self.edit_comment(int(existing["id"]), body, repo)
        return self.create_comment(body, repo, pr_number)

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def extract_url_from_comment(body: str) -> str | None:
        """Pull the site URL out of a §6 comment (used by slash-command runs)."""
        match = _SITE_RE.search(body or "")
        return match.group(1) if match else None


def client_from_env(env: dict[str, str] | None = None) -> GitHubClient:
    """Build a client from action env (GITHUB_TOKEN, GITHUB_REPOSITORY, PR number)."""
    ctx: dict[str, str] = dict(os.environ) if env is None else env
    repo = ctx.get("GITHUB_REPOSITORY", "")
    pr_number = int(ctx.get("GITHUB_PR_NUMBER", "") or 0)
    return GitHubClient(
        token=ctx.get("GITHUB_TOKEN", ""),
        base_url=ctx.get("GITHUB_API_URL", "https://api.github.com"),
        repo=repo,
        pr_number=pr_number,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI used by the action entrypoint to post a comment payload.

    Reads the comment body from a file (never argv — bodies contain newlines),
    posts idempotently, prints the resulting comment id.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="github_comment", description="Post an idempotent PR comment.")
    parser.add_argument("--body-file", required=True, help="Path to the markdown body")
    parser.add_argument("--marker", default=MARKER, help="Marker for edit-not-duplicate")
    parser.add_argument("--repo", default="", help="org/repo (default: GITHUB_REPOSITORY)")
    parser.add_argument("--pr-number", type=int, default=0, help="PR number (default: GITHUB_PR_NUMBER)")
    parser.add_argument("--api-url", default="", help="API base URL override (tests/mocks)")
    args = parser.parse_args(argv)

    from pathlib import Path

    body = Path(args.body_file).read_text(encoding="utf-8")
    env = os.environ.copy()
    if args.repo:
        env["GITHUB_REPOSITORY"] = args.repo
    if args.pr_number:
        env["GITHUB_PR_NUMBER"] = str(args.pr_number)
    if args.api_url:
        env["GITHUB_API_URL"] = args.api_url
    client = client_from_env(env)
    try:
        result = client.post_comment(body, marker=args.marker)
    except GitHubError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"posted comment {result.get('id', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
