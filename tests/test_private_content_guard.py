"""Tests for the developer-machine part of the private-content guard.

t-0941: the old guard read only kanban.html and compared it with docs/private/.
A hostname attribute or an absolute local path inside a tracked fixture was
invisible. These tests plant each shape and prove the guard names the file and
line. They also prove the current user and machine names are derived at check
time, not hard-coded.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from scripts.maintenance import kanban

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _plant(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _findings(paths: Iterable[Path], root: Path) -> list[kanban.DeveloperMachineFinding]:
    return kanban.developer_machine_findings(paths, root=root)


def test_clean_tree_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = _plant(tmp_path, "fixtures/heldout_runs/run.txt", "no machine detail here\n")
    assert _findings([clean], tmp_path) == []
    assert kanban.developer_machine_check([clean], root=tmp_path) == 0
    assert "OK: tracked fixtures/evidence carry no developer-machine content" in capsys.readouterr().out


def test_absolute_home_path_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    planted = _plant(
        tmp_path,
        "fixtures/heldout_runs/2026-10-24/junit/test_eval_001.xml",
        r"skipped: C:\Users\alice\project\scratch\run.py:44" + "\n",
    )

    findings = _findings([planted], tmp_path)
    assert "home path" in {finding.kind for finding in findings}
    assert any("alice" in finding.matched for finding in findings)

    assert kanban.developer_machine_check([planted], root=tmp_path) == 1
    output = capsys.readouterr().out
    assert "test_eval_001.xml:1: home path" in output
    assert "alice" in output


def test_hostname_attribute_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    planted = _plant(
        tmp_path,
        "fixtures/heldout_runs/junit/test_eval_002.xml",
        '<testsuite name="pytest" hostname="ALICE-PC" tests="1"></testsuite>\n',
    )

    findings = _findings([planted], tmp_path)
    assert [finding.kind for finding in findings] == ["hostname attribute"]
    assert "ALICE-PC" in findings[0].matched

    assert kanban.developer_machine_check([planted], root=tmp_path) == 1
    assert "hostname attribute" in capsys.readouterr().out


def test_absolute_ignored_path_citation_fails(tmp_path: Path) -> None:
    planted = _plant(
        tmp_path,
        "fixtures/heldout_runs/excerpts/pytest.log",
        "see C:\\repo\\scratch\\gate1_out\\test_eval_001.py:44 for the line\n",
    )

    findings = _findings([planted], tmp_path)
    assert [finding.kind for finding in findings] == ["ignored-path citation"]
    assert "scratch" in findings[0].matched


def test_relative_ignored_citation_is_the_published_form(tmp_path: Path) -> None:
    """The t-0912 scrub normalised the leak to a relative scratch/ citation."""
    clean = _plant(
        tmp_path,
        "fixtures/heldout_runs/excerpts/pytest.log",
        "see scratch/gate1_out/test_eval_001.py:44 for the line\n",
    )
    assert _findings([clean], tmp_path) == []


def test_identities_are_derived_from_the_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kanban.getpass, "getuser", lambda: "alice")
    monkeypatch.setattr(kanban.socket, "gethostname", lambda: "alice-pc")

    users, machines = kanban._developer_identities()  # noqa: SLF001
    assert "alice" in users
    assert "alice-pc" in machines

    planted = _plant(tmp_path, "fixtures/heldout_runs/run.txt", "owner alice on alice-pc\n")
    kinds = {finding.kind for finding in _findings([planted], tmp_path)}
    assert "current username" in kinds
    assert "machine name" in kinds


def test_docs_plain_public_handle_is_not_a_machine_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hostname is also the public handle; prose must not fail on it."""
    monkeypatch.setattr(kanban.socket, "gethostname", lambda: "lacattano")
    docs = _plant(tmp_path, "docs/sessions/note.md", "Copyright 2026 lacattano\n")
    assert _findings([docs], tmp_path) == []

    # A home path in the same docs tree is still caught.
    docs_path = _plant(tmp_path, "docs/sessions/run.md", r"ran in C:\Users\alice\repo" + "\n")
    assert [finding.kind for finding in _findings([docs_path], tmp_path)] == ["home path"]


def test_ci_runs_the_extended_guard() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "private-content-guard" in workflow
    assert "kanban.py --check-private" in workflow
