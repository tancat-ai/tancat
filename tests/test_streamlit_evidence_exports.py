"""t-1485: the UI download buttons obey the same Free cap as the file writers.

The exporters enforce the monthly cap when they write a file; the UI builds the
bytes in memory, so it had no check and a Free user past the cap could still
download. This is an AppTest: it runs the real panel function under Streamlit's
script runner and asserts what a buyer would see.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src.usage_meter import FreeTierLimitError


def _panel() -> None:  # pragma: no cover - executed by AppTest
    from unittest.mock import MagicMock as _Mock

    from src.ui.ui_evidence import render_export_downloads

    render_export_downloads(_Mock())


def _run(monkeypatch: pytest.MonkeyPatch, *, refuse: bool) -> AppTest:
    import src.usage_meter as meter_module

    if refuse:

        def _refuse(self: object, format_name: str) -> None:
            raise FreeTierLimitError(
                "Free tier evidence-export limit reached (10/10 exports in the current 30-day "
                "window). Upgrade to a paid tier for unlimited runs and exports."
            )

        monkeypatch.setattr(meter_module.UsageMeter, "assert_export_allowed", _refuse)
    else:
        monkeypatch.setattr(meter_module.UsageMeter, "assert_export_allowed", lambda self, name: None)

    at = AppTest.from_function(_panel, default_timeout=15)
    at.run(timeout=15)
    return at


def test_past_the_cap_the_buttons_are_gone_and_the_reason_is_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _run(monkeypatch, refuse=True)
    assert not at.exception
    assert len(at.warning) == 1, [w.value for w in at.warning]
    assert "evidence-export limit reached" in at.warning[0].value
    assert not at.get("download_button"), "a capped deployment can still download"


def test_inside_the_cap_the_three_buttons_render(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _run(monkeypatch, refuse=False)
    assert not at.exception
    buttons = at.get("download_button")
    assert len(buttons) == 3, [getattr(b, "label", b) for b in buttons]
    assert not at.warning
