"""The CLI's licence glue: activate, status, release - and when it refuses to start.

The mechanism (2026-11-26): a key from the store, activated once through our relay,
cached on this machine, checked again only when a new version is installed. The CLI
is where activation happens for a headless install, so its words matter.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.cli import main as cli_main
from src.licensing import activation as keys
from src.licensing import entitlement


def _write_licence(path: Path, *, created_at: str = "2026-11-26T00:04:47.460Z") -> None:
    path.write_text(
        json.dumps(
            {
                "key": "00000-00000-00000-00000-00000",
                "instance_id": "lki_testinstance000000000000",
                "instance_name": "acme-laptop",
                "status": "active",
                "created_at": created_at,
                "expires_at": "",
                "activation_limit": 1,
                "last_checked": created_at,
            }
        ),
        encoding="utf-8",
    )


class _Response:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "licence.json"
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(target))
    monkeypatch.delenv(keys.RELAY_URL_ENV, raising=False)
    return target


def test_status_on_a_free_install_names_the_path_and_the_command(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main.main(["licence", "status"]) == 0
    out = capsys.readouterr().out
    assert "Free Community" in out
    assert str(home) in out
    assert "(not present)" in out
    assert "tancat licence activate" in out


def test_status_with_an_activated_key_names_what_is_stored(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_licence(home)

    assert cli_main.main(["licence", "status"]) == 0
    out = capsys.readouterr().out
    assert "activated licence key" in out
    assert "00000-...-00000" in out, "the key must be masked on screen"
    assert "00000-00000" not in out, "the middle of the key must not be printed"
    assert "lki_testinstance000000000000" in out
    assert "Updates to:   2027-11-26" in out
    assert "Tier:         pro" in out


def test_status_says_when_the_build_is_past_the_window(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_licence(home, created_at="2020-01-01T00:00:00+00:00")

    assert cli_main.main(["licence", "status"]) == 0
    out = capsys.readouterr().out
    assert "AFTER the window" in out
    assert "update window ended" in out


def test_activate_prints_what_was_stored(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fake_urlopen(request: Any, timeout: float = 0) -> _Response:
        return _Response(
            200,
            {
                "activation": {
                    "key": "00000-00000-00000-00000-00000",
                    "status": "active",
                    "created_at": "2026-11-26T00:04:47.460Z",
                    "expires_at": "",
                    "activation_limit": 1,
                    "instance": {"id": "lki_testinstance000000000000", "name": "acme-laptop"},
                }
            },
        )

    monkeypatch.setattr(keys.urllib.request, "urlopen", _fake_urlopen)

    assert cli_main.main(["licence", "activate", "00000-00000-00000-00000-00000", "acme-laptop"]) == 0
    out = capsys.readouterr().out
    assert "Licence key activated on this machine" in out
    assert home.exists()


def test_activate_with_no_key_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["licence", "activate"]) == 2
    assert "Usage: tancat licence activate" in capsys.readouterr().err


def test_activate_that_the_relay_refuses_exits_non_zero(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # t-1506: our relay sends its code with a 403; a bare 403 is the edge's answer.
    monkeypatch.setattr(
        keys.urllib.request, "urlopen", lambda *a, **k: _Response(403, {"error": keys.ACTIVATION_LIMIT})
    )

    assert cli_main.main(["licence", "activate", "00000-00000-00000-00000-00000"]) == 1
    assert "maximum number of machines" in capsys.readouterr().out


def test_activate_blocked_at_the_edge_tells_the_buyer_it_is_our_fault(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The edge's 403 is a fault at our end, and the CLI says so (t-1506)."""
    monkeypatch.setattr(keys.urllib.request, "urlopen", lambda *a, **k: _Response(403, {}))

    assert cli_main.main(["licence", "activate", "00000-00000-00000-00000-00000"]) == 1
    out = capsys.readouterr().out
    assert "edge error 1010" in out
    assert "hello@tancat.dev" in out
    assert "maximum number of machines" not in out


def test_release_removes_the_stored_licence(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_licence(home)
    monkeypatch.setattr(keys.urllib.request, "urlopen", lambda *a, **k: _Response(200, {"released": True}))

    assert cli_main.main(["licence", "release"]) == 0
    assert not home.exists()
    assert "released" in capsys.readouterr().out.lower()


def test_the_startup_backstop_refuses_a_build_after_the_window(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_licence(home, created_at="2020-01-01T00:00:00+00:00")
    monkeypatch.setattr(entitlement, "RELEASE_DATE", date(2026, 11, 26))

    code = cli_main._startup_backstop()

    assert code == 3
    err = capsys.readouterr().err
    assert "update window ended" in err


def test_the_startup_backstop_makes_no_network_call(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_licence(home)

    def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("startup must not call the relay")

    monkeypatch.setattr(keys.urllib.request, "urlopen", _explode)
    monkeypatch.setattr(entitlement, "RELEASE_DATE", date(2026, 12, 1))

    assert cli_main._startup_backstop() is None
