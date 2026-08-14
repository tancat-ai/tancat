#!/usr/bin/env python3
"""Slash-command loop core (Phase 7b, spec §6 + §9.7).

Parses PR-thread commands and builds the reply payloads the workflow posts:

- ``/adapt <test>`` — run verified adaptation on the named test (locator-only
  patch -> re-run -> assertion gate). Execution happens in the action's
  ``mode: adapt``; this module validates the request and renders the reply
  from the adaptation report.
- ``/ignore <test>`` — record a known-benign failure: this module renders the
  exact ``.ai-test-ignore.yml`` entry (with the human-recorded ``reason`` —
  the anti-rug rule) and the reply text telling the user to commit it.

Platform-neutral core (spec §5.5): no GitHub imports, no network. The
slash-command *workflow* (``.github/workflows/ci-slash-commands.yml``) owns
the trigger (``issue_comment``) and posts replies through
``ci/platform/github.py``. Fork PRs are filtered by the workflow (never
``pull_request_target``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# /adapt test_08_checkout[chromium]  |  /ignore test_03_review_cart_contents
# Backticks allowed in the test token (users wrap names in ``) — stripped after.
_COMMAND_RE = re.compile(r"^\s*/(?P<cmd>adapt|ignore)\s+(?P<test>\S+)\s*$", re.IGNORECASE)

MARKER = "## 🤖 AI Test Generator"


@dataclass(frozen=True)
class SlashCommand:
    """A parsed slash command."""

    command: str  # adapt | ignore
    test: str  # test name as written (may carry [chromium])


def parse_slash_command(body: str) -> SlashCommand | None:
    """Return the parsed command from a comment body, or None."""
    if not body:
        return None
    for line in body.splitlines():
        match = _COMMAND_RE.match(line)
        if match:
            return SlashCommand(command=match.group("cmd").lower(), test=match.group("test").strip("`"))
    return None


def build_ignore_reply(
    test: str,
    failure_message: str,
    existing_ignores: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Reply payload for ``/ignore`` — the YAML entry to commit, never a silent mute.

    The human records the reason (the anti-rug rule from ``src/ci_ignore.py``);
    the bot suggests the exact entry and explains why the rule exists.
    """
    reason_hint = "known-benign: button moved, verified still functional (add your why)"
    entry = {
        "test": test,
        "reason": reason_hint,
        "match": _suggest_match_regex(failure_message),
    }
    lines = [
        f"`{test}` looks like a known-benign locator failure. To record it, add this to "
        "`.ai-test-ignore.yml` in a commit (versioned + reviewable — this is the "
        "‘button moved but still works’ mechanism):",
        "",
        "```yaml",
        "ignores:",
        f'  - test: "{entry["test"]}"',
        f'    reason: "{entry["reason"]}"',
    ]
    if entry["match"]:
        lines.append(f'    match: "{entry["match"]}"')
    lines.append("```")
    if existing_ignores and any(i.get("test") == test for i in existing_ignores):
        lines.append("")
        lines.append(f"⚠️ A rule for `{test}` already exists — verify it matches this failure before re-adding.")
    body = "\n".join(lines)
    return {"body": body, "yaml_entry": json.dumps(entry)}


def build_adapt_reply(report: dict[str, Any]) -> dict[str, str]:
    """Reply payload for ``/adapt`` from an adaptation report."""
    summary = report.get("summary", {})
    kept = report.get("kept", [])
    reverted = report.get("reverted", [])
    lines = [
        "Verified adaptation ran (locator-only patch → re-run → assertion gate).",
        "",
        f"**{summary.get('adapted', 0)} adapted · {summary.get('reverted', 0)} reverted · "
        f"{summary.get('candidates', 0)} candidate(s) total.**",
        "",
    ]
    if kept:
        lines.append("Kept (re-run passed):")
        for k in kept:
            lines.append(f"- `{k['test']}` — `{k['old_locator']}` → `{k['new_locator']}`")
        lines.append("")
    if reverted:
        lines.append("Reverted (assertions still failed after patch):")
        for r in reverted:
            lines.append(f"- `{r['test']}` — {r.get('message', '')[:160]}")
        lines.append("")
    if not kept and not reverted:
        lines.append("No repair candidates matched this test (locator-class failures only are auto-adapted).")
    body = "\n".join(lines)
    return {"body": body}


def _suggest_match_regex(failure_message: str) -> str:
    """Suggest a ``match`` regex scoping the ignore to the failure's locator.

    Handles both Playwright (``locator('…')``) and evidence_tracker
    (``Locator '…' not found``) message shapes.
    """
    for pattern in (
        re.compile(r"locator\(\s*(['\"])(.*?)\1\s*\)"),
        re.compile(r"\bLocator\s+(['\"])(.*?)\1\s+not found", re.IGNORECASE),
    ):
        match = pattern.search(failure_message or "")
        if match:
            return re.escape(match.group(2))
    return ""


def main(argv: list[str] | None = None) -> int:
    """CLI for the slash-command workflow: parse a comment body and write the
    reply payload file for the workflow to post (via the action's GitHub adapter)."""
    parser = argparse.ArgumentParser(prog="ci_slash_commands", description="Parse and render slash-command replies.")
    parser.add_argument("--comment-file", required=True, help="Path to the comment body text")
    parser.add_argument("--output", required=True, help="Output dir (command.json + reply.md)")
    parser.add_argument("--adapt-report", default="", help="adaptation.json path (for /adapt replies)")
    parser.add_argument("--junit", default="", help="junit.xml path (failure message source for /ignore)")
    args = parser.parse_args(argv)

    body = Path(args.comment_file).read_text(encoding="utf-8")
    cmd = parse_slash_command(body)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if cmd is None:
        (out_dir / "command.json").write_text(json.dumps({"parsed": False}), encoding="utf-8")
        print("no slash command parsed")
        return 0

    payload: dict[str, Any] = {"parsed": True, "command": cmd.command, "test": cmd.test}

    if cmd.command == "adapt":
        report: dict[str, Any] = {}
        if args.adapt_report and Path(args.adapt_report).exists():
            report = json.loads(Path(args.adapt_report).read_text(encoding="utf-8"))
        reply = build_adapt_reply(report)
    else:  # ignore
        failure_message = ""
        if args.junit and Path(args.junit).exists():
            import xml.etree.ElementTree as ET

            root = ET.parse(args.junit).getroot()
            suites = list(root) if root.tag == "testsuites" else [root]
            base = cmd.test.split("[", 1)[0]
            for suite in suites:
                for case in suite.iter("testcase"):
                    if case.get("name", "").split("[", 1)[0] != base:
                        continue
                    failure = case.find("failure")
                    if failure is not None:
                        failure_message = failure.get("message", "") or (failure.text or "").strip()
                        break
        reply = build_ignore_reply(cmd.test, failure_message)

    payload["reply"] = reply["body"]
    (out_dir / "command.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out_dir / "reply.md").write_text(reply["body"], encoding="utf-8")
    print(f"slash command: /{cmd.command} {cmd.test} -> {out_dir / 'reply.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
