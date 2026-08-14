"""Slash-command loop core tests (Phase 7b, spec §6).

Parsing + reply payloads are platform-neutral and fully offline.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.ci_slash_commands import (
    build_adapt_reply,
    build_ignore_reply,
    parse_slash_command,
)

COMMENT_ADAPT = "This is a reply\n/adapt test_08_checkout[chromium]\nplease fix"
COMMENT_IGNORE = "/ignore test_03_review_cart_contents"


def test_parse_adapt_command() -> None:
    cmd = parse_slash_command(COMMENT_ADAPT)
    assert cmd is not None
    assert cmd.command == "adapt"
    assert cmd.test == "test_08_checkout[chromium]"


def test_parse_ignore_command() -> None:
    cmd = parse_slash_command(COMMENT_IGNORE)
    assert cmd is not None
    assert cmd.command == "ignore"
    assert cmd.test == "test_03_review_cart_contents"


def test_parse_non_command_is_none() -> None:
    assert parse_slash_command("just a normal comment") is None
    assert parse_slash_command("") is None
    assert parse_slash_command("   /adapt   ") is None  # missing test name
    assert parse_slash_command("/unknown test_x") is None


def test_parse_case_insensitive_and_backticks() -> None:
    cmd = parse_slash_command("/ADAPT `test_01_browse`")
    assert cmd is not None
    assert cmd.command == "adapt"
    assert cmd.test == "test_01_browse"


def test_build_ignore_reply_contains_yaml_and_reason() -> None:
    reply = build_ignore_reply("test_08_checkout[chromium]", "waiting for locator('a[href=\"/x\"]')")
    body = reply["body"]
    assert ".ai-test-ignore.yml" in body
    assert "test_08_checkout[chromium]" in body
    assert "reason" in body
    entry = json.loads(reply["yaml_entry"])
    assert entry["test"] == "test_08_checkout[chromium]"
    assert entry["reason"]  # anti-rug rule: a reason is always present
    assert entry["match"] == r'a\[href="/x"\]'  # escaped locator regex


def test_build_ignore_reply_flags_duplicate(tmp_path: Path) -> None:
    reply = build_ignore_reply(
        "test_x",
        "",
        existing_ignores=[{"test": "test_x", "reason": "already known"}],
    )
    assert "already exists" in reply["body"]


def test_build_adapt_reply_renders_kept_and_reverted() -> None:
    report = {
        "summary": {"adapted": 1, "reverted": 1, "candidates": 2},
        "kept": [{"test": "t1", "old_locator": "a", "new_locator": "b"}],
        "reverted": [{"test": "t2", "message": "assertions still failed"}],
    }
    body = build_adapt_reply(report)["body"]
    assert "1 adapted · 1 reverted" in body
    assert "`a` → `b`" in body
    assert "t2" in body


def test_build_adapt_reply_empty() -> None:
    body = build_adapt_reply({"summary": {"adapted": 0, "reverted": 0, "candidates": 0}, "kept": [], "reverted": []})[
        "body"
    ]
    assert "No repair candidates" in body


def _junit(tmp_path: Path) -> Path:
    path = tmp_path / "junit.xml"
    suite = ET.Element("testsuite", {"tests": "1"})
    case = ET.SubElement(suite, "testcase", {"name": "test_08_checkout[chromium]", "classname": "pkg"})
    ET.SubElement(case, "failure", {"message": "waiting for locator('a[href=\"/x\"]')"}).text = "log"
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=False)
    return path


def test_main_ignore_writes_reply(tmp_path: Path) -> None:

    import scripts.ci_slash_commands as mod

    comment = tmp_path / "comment.txt"
    comment.write_text(COMMENT_IGNORE, encoding="utf-8")
    out = tmp_path / "out"
    rc = mod.main(["--comment-file", str(comment), "--output", str(out), "--junit", str(_junit(tmp_path))])
    assert rc == 0
    payload = json.loads((out / "command.json").read_text(encoding="utf-8"))
    assert payload["parsed"] is True
    assert payload["command"] == "ignore"
    assert "test_03_review_cart_contents" in payload["reply"]
    assert (out / "reply.md").exists()


def test_main_no_command_is_noop(tmp_path: Path) -> None:
    import scripts.ci_slash_commands as mod

    comment = tmp_path / "comment.txt"
    comment.write_text("hello world", encoding="utf-8")
    out = tmp_path / "out"
    rc = mod.main(["--comment-file", str(comment), "--output", str(out)])
    assert rc == 0
    assert json.loads((out / "command.json").read_text(encoding="utf-8"))["parsed"] is False
