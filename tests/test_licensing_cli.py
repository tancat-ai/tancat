"""j-0304: the CLI glue - the only production path to the network and to a refusal.

``_licence_command`` makes the activation call; ``_startup_backstop`` refuses a
build past its window. Both were untested, which is where a regression would ship.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.cli import main as cli_main
from src.licensing import activation as A

ZERO_KEY = "00000000-0000-0000-0000-000000000000"


def _response(**meta_overrides: object) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "store_id": int(A.STORE_ID),
        "product_id": int(A.PRODUCT_ID),
        "variant_id": int(A.VARIANT_ID),
    }
    meta.update(meta_overrides)
    return {
        "activated": meta_overrides.pop("activated", True) if False else True,
        "license_key": {
            "status": "active",
            "key": ZERO_KEY,
            "activation_limit": 1,
            "activation_usage": 1,
            "created_at": "2026-11-12T09:00:00.000000Z",
            "expires_at": None,
        },
        "instance": {"id": "inst-cli"},
        "meta": meta,
    }


@pytest.fixture()
def licence_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the module at a temp licence file, and stub the network transport."""
    path = tmp_path / "licence.json"
    monkeypatch.setattr(A, "default_licence_path", lambda: path)
    return path


def test_the_cli_activates_a_key_and_stores_it(
    licence_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(A, "_post_form", lambda url, fields, timeout=20.0: (200, _response(), ""))

    code = cli_main.main(["licence", "activate", ZERO_KEY])

    assert code == 0
    out = capsys.readouterr().out
    assert "Activated" in out
    assert "2027-11-12" in out, "the message does not name the window end"
    stored = json.loads(licence_file.read_text(encoding="utf-8"))
    assert stored["key"] == ZERO_KEY
    assert stored["store_id"] == A.STORE_ID


def test_the_cli_refusal_names_the_mismatched_id_and_keeps_the_existing_licence(
    licence_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {"key": ZERO_KEY, "key_created_at": "2026-01-01", "instance_id": "old"}
    A.write_licence(before, licence_file)
    monkeypatch.setattr(A, "_post_form", lambda url, fields, timeout=20.0: (200, _response(product_id=1), ""))

    code = cli_main.main(["licence", "activate", "new-key"])

    assert code == 2
    out = capsys.readouterr().out
    assert "different product" in out
    assert json.loads(licence_file.read_text(encoding="utf-8")) == before, "the refusal changed the licence"


def test_the_startup_backstop_exits_three_and_names_the_version_that_works(
    licence_file: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    A.write_licence({"key": ZERO_KEY, "key_created_at": "2024-01-01", "installed_version": "1.2.0"}, licence_file)
    monkeypatch.setattr(A, "RELEASE_DATE", date(2027, 1, 1))

    code = cli_main.main(["licence", "status"])

    # status is a licence command, not a start: the backstop must not fire for it.
    assert code == 0

    code = cli_main.main([])
    captured = capsys.readouterr()
    assert code == 3, "a build past its window did not refuse to start"
    assert "Version 1.2.0 keeps working" in captured.err
    assert "2025-01-01" in captured.err, "the refusal does not name the window end"


def test_the_startup_backstop_does_not_fire_inside_the_window(
    licence_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    A.write_licence({"key": ZERO_KEY, "key_created_at": "2026-11-12", "installed_version": "1.2.0"}, licence_file)
    monkeypatch.setattr(A, "RELEASE_DATE", date(2027, 1, 1))

    # Inside the window the CLI proceeds to its normal dispatch; --help exits 0.
    assert cli_main.main(["--help"]) == 0


def test_a_start_records_last_seen(licence_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """touch_last_seen runs at startup, so the field moves on a second run."""
    A.write_licence(
        {"key": ZERO_KEY, "key_created_at": "2026-11-12", "last_seen_at": "2020-01-01T00:00:00+00:00"}, licence_file
    )

    assert cli_main.main(["--help"]) == 0
    first = json.loads(licence_file.read_text(encoding="utf-8"))["last_seen_at"]
    assert first != "2020-01-01T00:00:00+00:00"

    assert cli_main.main(["--help"]) == 0
    second = json.loads(licence_file.read_text(encoding="utf-8"))["last_seen_at"]
    assert second >= first
