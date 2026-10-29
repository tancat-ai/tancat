"""Tests for the codegen replay path, the repair picker, and the repair panels.

Covers the defects named in t-0937 part 0 and part 1:
- a missing state file refuses the replay;
- captured / no-click / failed are distinct outcomes;
- a timeout kills the process tree, not only the Playwright shim;
- the recording is removed on every path, not only success;
- both locator parsers survive wrapping, apostrophes, and adjacent calls;
- the repair picker returns the interaction before an assertion;
- the two Streamlit repair panels show each outcome.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import src.locator_repair as locator_repair
import src.ui.ui_run_results as ui_run_results
from src.locator_repair import CodegenOutcome, _extract_locator, extract_locator_from_line, run_codegen_session


class _FakeProc:
    def __init__(self, *, returncode: int = 0, timeouts: int = 0) -> None:
        self.pid = 4242
        self.returncode = returncode
        self._timeouts = timeouts
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if self._timeouts > 0:
            self._timeouts -= 1
            raise subprocess.TimeoutExpired(cmd="playwright", timeout=timeout or 0)
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class _FakePopen:
    """Write a recording (or nothing) and return a controllable process."""

    def __init__(self, script: str | None, *, returncode: int = 0, timeouts: int = 0) -> None:
        self.script = script
        self.returncode = returncode
        self.timeouts = timeouts
        self.output_path: Path | None = None
        self.proc: _FakeProc | None = None

    def __call__(self, cmd: list[str], **kwargs: Any) -> _FakeProc:
        output_index = cmd.index("--output") + 1
        self.output_path = Path(cmd[output_index])
        if self.script is not None:
            self.output_path.write_text(self.script, encoding="utf-8")
        self.proc = _FakeProc(returncode=self.returncode, timeouts=self.timeouts)
        return self.proc


def _patch_popen(monkeypatch: pytest.MonkeyPatch, fake: _FakePopen) -> None:
    monkeypatch.setattr(locator_repair.subprocess, "Popen", fake)


# -- missing state file -----------------------------------------------------


def test_missing_state_file_refuses_the_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen(None)
    _patch_popen(monkeypatch, fake)

    outcome = run_codegen_session("https://shop.example.com/cart", state_file="C:/does/not/exist.json")

    assert outcome.status == "cannot_replay"
    assert "cannot be replayed" in outcome.reason
    assert fake.output_path is None, "codegen must not launch without the journey's state"


# -- timeout, kill tree, cleanup -------------------------------------------


def test_timeout_is_failed_and_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen(None, timeouts=2)
    _patch_popen(monkeypatch, fake)
    killed: list[Any] = []
    monkeypatch.setattr(locator_repair, "_kill_process_tree", lambda proc: killed.append(proc))

    outcome = run_codegen_session("https://shop.example.com/cart", timeout_seconds=1)

    assert outcome.status == "failed"
    assert "timed out" in outcome.reason
    assert killed, "the timeout did not kill the codegen tree"
    assert fake.output_path is not None
    assert not fake.output_path.parent.exists(), "the private codegen directory leaked"


def test_timeout_kills_the_windows_process_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen(None, timeouts=1)
    _patch_popen(monkeypatch, fake)
    calls: list[list[str]] = []
    monkeypatch.setattr(locator_repair.sys, "platform", "win32")
    monkeypatch.setattr(locator_repair.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))

    outcome = run_codegen_session("https://shop.example.com/cart", timeout_seconds=1)

    assert outcome.status == "failed"
    assert any(call[:2] == ["taskkill", "/T"] for call in calls), calls


def test_timeout_kills_the_posix_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen(None, timeouts=1)
    _patch_popen(monkeypatch, fake)
    groups: list[int] = []
    killed: list[tuple[int, int]] = []

    def _killpg(pgid: int, sig: int) -> None:
        groups.append(pgid)
        killed.append((pgid, sig))

    fake_os = SimpleNamespace(
        name="posix",
        chmod=os.chmod,
        getpgid=lambda pid: 999,
        killpg=_killpg,
    )
    monkeypatch.setattr(locator_repair.sys, "platform", "linux")
    monkeypatch.setattr(locator_repair, "os", fake_os)
    monkeypatch.setattr(locator_repair, "signal", SimpleNamespace(SIGKILL=9))

    outcome = run_codegen_session("https://shop.example.com/cart", timeout_seconds=1)

    assert outcome.status == "failed"
    assert groups == [999], groups


def test_a_second_wait_timeout_does_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen(None, timeouts=2)
    _patch_popen(monkeypatch, fake)
    monkeypatch.setattr(locator_repair, "_kill_process_tree", lambda proc: None)

    # Both the first wait and the quiet five-second wait raise; neither escapes.
    outcome = run_codegen_session("https://shop.example.com/cart", timeout_seconds=1)
    assert outcome.status == "failed"


# -- captured / no-click / read failure, with cleanup ----------------------


def test_captured_recording_is_returned_and_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen('page.locator("text=Women\'s shoes").click()\n')
    _patch_popen(monkeypatch, fake)

    outcome = run_codegen_session("https://shop.example.com/cart")

    assert outcome.status == "captured"
    assert outcome.locator == "text=Women's shoes"
    assert outcome.captured
    assert fake.output_path is not None
    assert not fake.output_path.exists(), "the recording (and any typed values) leaked"
    assert not fake.output_path.parent.exists(), "the private codegen directory leaked"


def test_no_click_is_distinct_from_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen('page.goto("https://shop.example.com/cart")\n')
    _patch_popen(monkeypatch, fake)

    outcome = run_codegen_session("https://shop.example.com/cart")

    assert outcome.status == "no_click"
    assert outcome.locator is None
    assert not outcome.captured
    assert fake.output_path is not None
    assert not fake.output_path.parent.exists()


def test_read_failure_is_failed_and_still_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePopen("page.locator('#cart').click()\n")
    _patch_popen(monkeypatch, fake)

    def _raise(self: Path, encoding: str | None = None) -> str:
        raise OSError("disk went away")

    monkeypatch.setattr(Path, "read_text", _raise)

    outcome = run_codegen_session("https://shop.example.com/cart")

    assert outcome.status == "failed"
    assert "could not read" in outcome.reason
    assert fake.output_path is not None
    assert not fake.output_path.parent.exists()


def test_launch_failure_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(cmd: list[str], **kwargs: Any) -> None:
        raise OSError("playwright is not installed")

    monkeypatch.setattr(locator_repair.subprocess, "Popen", _boom)

    outcome = run_codegen_session("https://shop.example.com/cart")

    assert outcome.status == "failed"
    assert "could not start" in outcome.reason


# -- the two parsers, one failure shape each -------------------------------


def test_role_parser_handles_a_wrapped_call() -> None:
    content = 'page.get_by_role(\n    "link",\n    name="Women\'s shoes",\n).click()\n'
    assert _extract_locator(content) == "get_by_role('link', name='Women\\'s shoes')"


def test_role_parser_keeps_an_apostrophe_in_the_name() -> None:
    content = 'page.get_by_role("link", name="Women\'s shoes").click()\n'
    result = _extract_locator(content)
    assert result is not None
    assert "Women" in result and "shoes" in result
    assert result == "get_by_role('link', name='Women\\'s shoes')"


def test_role_parser_does_not_cross_into_a_second_call() -> None:
    content = 'page.get_by_role("button")\npage.get_by_role("link", name="Second")\n'
    result = _extract_locator(content)
    assert result == "get_by_role('button')"
    assert "Second" not in str(result)


def test_role_parser_keeps_a_closing_paren_inside_the_name() -> None:
    content = 'page.get_by_role("button", name="Continue (2)").click()\n'
    assert _extract_locator(content) == "get_by_role('button', name='Continue (2)')"


def test_parser_ignores_a_call_inside_a_print_string() -> None:
    content = "print(\"page.get_by_role('button', name='Fake')\")\n"
    assert _extract_locator(content) is None


def test_parser_requires_the_page_receiver() -> None:
    content = 'other_page.get_by_role("button", name="Fake").click()\n'
    assert _extract_locator(content) is None


def test_locator_parser_keeps_an_apostrophe() -> None:
    content = 'page.locator("text=Women\'s shoes").click()\n'
    assert _extract_locator(content) == "text=Women's shoes"


def test_locator_parser_keeps_an_escaped_quote() -> None:
    content = "page.locator('button:has-text(\"Women\\'s shoes\")').click()\n"
    assert _extract_locator(content) == 'button:has-text("Women\'s shoes")'


def test_locator_parser_handles_a_wrapped_call() -> None:
    content = 'page.locator(\n    "#submit-order",\n).click()\n'
    assert _extract_locator(content) == "#submit-order"


def test_parser_returns_none_for_a_recording_with_only_a_goto() -> None:
    assert _extract_locator('page.goto("https://shop.example.com/cart")\n') is None


# -- part 1: the repair picker ---------------------------------------------


def test_picker_returns_the_interaction_before_a_failed_assertion() -> None:
    steps = [
        {"type": "navigate", "label": "Open shop", "url": "https://shop.example.com/", "result": {"status": "passed"}},
        {
            "type": "click",
            "label": "Submit order",
            "url": "https://shop.example.com/checkout.html",
            "result": {"status": "passed"},
        },
        {
            "type": "assertion",
            "label": "checkout page loaded",
            "url": "https://shop.example.com/checkout.html",
            "result": {"status": "failed"},
        },
    ]

    step = ui_run_results._pick_repair_step(steps)

    assert step is not None
    assert step["label"] == "Submit order"
    assert step["url"] == "https://shop.example.com/checkout.html"


def test_picker_returns_none_when_the_assertion_is_the_first_step() -> None:
    steps = [
        {
            "type": "assertion",
            "label": "checkout page loaded",
            "url": "https://shop.example.com/checkout.html",
            "result": {"status": "failed"},
        }
    ]

    assert ui_run_results._pick_repair_step(steps) is None


def test_failure_context_reads_the_interaction_from_the_sidecar(tmp_path: Path) -> None:
    saved_path = tmp_path / "test_go_to_cart.py"
    saved_path.write_text("def test_go_to_cart(page):\n    pass\n", encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "test_go_to_cart.evidence.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "type": "click",
                        "label": "Submit order",
                        "url": "https://shop.example.com/checkout.html",
                        "result": {"status": "passed"},
                    },
                    {
                        "type": "assertion",
                        "label": "checkout page loaded",
                        "url": "https://shop.example.com/checkout.html",
                        "result": {"status": "failed"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    label, url, line_no = ui_run_results._failure_context(str(saved_path), "test_go_to_cart", None)

    assert label == "Submit order"
    assert url == "https://shop.example.com/checkout.html"
    assert line_no is None


# -- the two repair panels -------------------------------------------------


class _Rerun(Exception):
    pass


class _FakeState(dict[str, Any]):
    """Streamlit session_state supports both item and attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class _FakeST:
    def __init__(self) -> None:
        self.session_state = _FakeState()
        self.messages: list[tuple[str, str]] = []

    @contextlib.contextmanager
    def spinner(self, *args: Any, **kwargs: Any) -> Any:
        yield

    def warning(self, message: str) -> None:
        self.messages.append(("warning", message))

    def error(self, message: str) -> None:
        self.messages.append(("error", message))

    def rerun(self) -> None:
        raise _Rerun()


def _install_fake_st(monkeypatch: pytest.MonkeyPatch, fake: _FakeST) -> None:
    monkeypatch.setattr(ui_run_results, "st", fake)


def test_skip_repair_panel_shows_cannot_replay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_st = _FakeST()
    _install_fake_st(monkeypatch, fake_st)
    test_file = tmp_path / "test_skip.py"
    test_file.write_text('def test_skip(page):\n    pytest.skip("no element")\n', encoding="utf-8")
    fake_st.session_state.update(
        {
            "skip_repair_url": "https://shop.example.com/cart",
            "skip_repair_file": str(test_file),
            "skip_repair_test_name": "test_skip",
            "skip_repair_line": 2,
            "skip_repair_steps": [],
            "skip_repair_status": "browser_opening",
        }
    )
    monkeypatch.setattr(
        ui_run_results,
        "run_codegen_session",
        lambda *args, **kwargs: CodegenOutcome("cannot_replay", reason="state is gone"),
    )

    with pytest.raises(_Rerun):
        ui_run_results._render_skip_repair_capture()

    assert fake_st.session_state["skip_repair_status"] == "error"
    assert "cannot be replayed" in fake_st.session_state["skip_repair_message"]


def test_skip_repair_panel_applies_a_captured_locator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_st = _FakeST()
    _install_fake_st(monkeypatch, fake_st)
    test_file = tmp_path / "test_skip.py"
    test_file.write_text('def test_skip(page):\n    pytest.skip("no element")\n', encoding="utf-8")
    fake_st.session_state.update(
        {
            "skip_repair_url": "https://shop.example.com/cart",
            "skip_repair_file": str(test_file),
            "skip_repair_test_name": "test_skip",
            "skip_repair_line": 2,
            "skip_repair_steps": [],
            "skip_repair_status": "browser_opening",
        }
    )
    monkeypatch.setattr(
        ui_run_results,
        "run_codegen_session",
        lambda *args, **kwargs: CodegenOutcome("captured", locator="#cart"),
    )

    with pytest.raises(_Rerun):
        ui_run_results._render_skip_repair_capture()

    assert fake_st.session_state["skip_repair_status"] == "patched"
    assert "#cart" in test_file.read_text(encoding="utf-8")


def test_locator_repair_panel_shows_a_failed_session(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeST()
    _install_fake_st(monkeypatch, fake_st)
    fake_st.session_state.update(
        {
            "repair_target": SimpleNamespace(
                failure_url="https://shop.example.com/cart", raw_locator="#old", line_number=2
            ),
            "repair_failure_url": "https://shop.example.com/cart",
            "repair_test_file": "unused.py",
        }
    )
    monkeypatch.setattr(
        ui_run_results,
        "run_codegen_session",
        lambda *args, **kwargs: CodegenOutcome("failed", reason="codegen crashed"),
    )

    with pytest.raises(_Rerun):
        ui_run_results._render_repair_browser_session()

    assert fake_st.session_state["repair_status"] == "error"
    assert "codegen crashed" in fake_st.session_state["repair_message"]


def test_locator_repair_panel_applies_a_captured_locator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_st = _FakeST()
    _install_fake_st(monkeypatch, fake_st)
    test_file = tmp_path / "test_locator.py"
    test_file.write_text('def test_x(page):\n    page.locator("#old").click()\n', encoding="utf-8")
    fake_st.session_state.update(
        {
            "repair_target": SimpleNamespace(
                failure_url="https://shop.example.com/cart", raw_locator="#old", line_number=2
            ),
            "repair_failure_url": "https://shop.example.com/cart",
            "repair_test_file": str(test_file),
        }
    )
    applied: list[Any] = []
    monkeypatch.setattr(
        ui_run_results,
        "run_codegen_session",
        lambda *args, **kwargs: CodegenOutcome("captured", locator="#new"),
    )
    monkeypatch.setattr(locator_repair, "apply_patch_to_file", lambda patch: applied.append(patch))

    with pytest.raises(_Rerun):
        ui_run_results._render_repair_browser_session()

    assert applied and applied[0].repaired_locator == "#new"
    assert fake_st.session_state["repair_status"] == "patched"


def test_extract_locator_from_line_unescapes_an_apostrophe() -> None:
    """The single-line helper must return the value the generated line runs."""
    line = r"    page.locator('text=Women\'s shoes').click()"
    assert extract_locator_from_line(line) == "text=Women's shoes"


def test_extract_locator_from_line_keeps_a_plain_locator() -> None:
    line = '    page.locator("#submit-order").click()'
    assert extract_locator_from_line(line) == "#submit-order"
