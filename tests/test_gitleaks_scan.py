"""Tests for the local gitleaks hook (``scripts/security/gitleaks_scan.py``)."""

from __future__ import annotations

import pytest

from scripts.security import gitleaks_scan


class _Result:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def test_missing_gitleaks_skips_cleanly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """A machine without gitleaks must not fail the commit."""
    monkeypatch.delenv("GITLEAKS_BIN", raising=False)
    monkeypatch.setattr(gitleaks_scan.shutil, "which", lambda _name: None)

    assert gitleaks_scan.main([]) == 0
    assert "not installed" in capsys.readouterr().out


def test_found_gitleaks_runs_staged_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    """gitleaks, when present, is run against the staged commit."""
    monkeypatch.delenv("GITLEAKS_BIN", raising=False)
    monkeypatch.setattr(gitleaks_scan.shutil, "which", lambda _name: "/usr/bin/gitleaks")
    seen: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], check: bool = False) -> _Result:
        seen["cmd"] = cmd
        return _Result(1)

    monkeypatch.setattr(gitleaks_scan.subprocess, "run", fake_run)

    assert gitleaks_scan.main([]) == 1
    assert seen["cmd"][0] == "/usr/bin/gitleaks"
    assert seen["cmd"][1:] == gitleaks_scan._STAGED_ARGS


def test_gitleaks_bin_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """GITLEAKS_BIN wins even when it is not on PATH."""
    monkeypatch.setenv("GITLEAKS_BIN", "C:/tools/gitleaks.exe")
    monkeypatch.setattr(gitleaks_scan.shutil, "which", lambda _name: None)

    assert gitleaks_scan.find_gitleaks() == "C:/tools/gitleaks.exe"


def test_run_failure_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the binary is found but cannot start, skip rather than fail."""
    monkeypatch.setattr(gitleaks_scan.shutil, "which", lambda _name: "gitleaks")

    def raise_oserror(cmd: list[str], check: bool = False) -> _Result:
        raise OSError("not executable")

    monkeypatch.setattr(gitleaks_scan.subprocess, "run", raise_oserror)

    assert gitleaks_scan.main([]) == 0
