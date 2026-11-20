"""The CLI's licence glue: what it prints, and when it refuses to start (j-0309).

There is no activation any more: a signed licence file or Free. What remains to test
is the reading of that file, the startup backstop and the gated upgrade.
"""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.cli import main as cli_main
from src.licensing import entitlement, signed_file
from src.licensing.entitlement import LicenceState


def _write_signed(path: Path, *, purchased: str, window_end: str, tier: str = "pro") -> str:
    """A signed licence file and the public key it verifies against."""
    private = ed25519.Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = base64.b64encode(
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    path.write_text(
        signed_file.signed_file_text(
            {
                "id": "TC-2026-000321",
                "product": "tancat",
                "buyer_ref": "order 321 / buyer@example.com",
                "purchased_at": purchased,
                "window_end": window_end,
                "tier": tier,
            },
            raw,
        ),
        encoding="utf-8",
    )
    return public


def test_status_on_a_free_install_names_the_signed_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    accepted = tmp_path / "licence.signed.json"
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(accepted))
    monkeypatch.setattr(entitlement, "default_signed_path", lambda: accepted)

    assert cli_main.main(["licence", "status"]) == 0
    out = capsys.readouterr().out
    assert "Free Community" in out
    assert "Signed licence file:" in out
    assert str(accepted) in out
    assert "(not present)" in out


def test_status_with_a_signed_file_names_that_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    accepted = tmp_path / "licence.signed.json"
    public = _write_signed(accepted, purchased="2026-11-01", window_end="2027-11-01")
    monkeypatch.setattr(signed_file, "VENDORED_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(accepted))

    assert cli_main.main(["licence", "status"]) == 0
    out = capsys.readouterr().out
    assert "Source:       signed licence file" in out
    assert "TC-2026-000321" in out
    assert "Tier:         pro" in out
    assert "(not present)" not in out


def test_activate_is_gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """There is no store key to activate; the command must say so, not try."""
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(tmp_path / "absent.json"))
    assert cli_main.main(["licence", "activate", "some-key"]) == 2
    err = capsys.readouterr().err
    assert "Usage: tancat licence [status]" in err


@pytest.mark.parametrize(
    ("window_end", "expected_exit"),
    [("2025-01-01", 3), ("2099-01-01", 0)],
)
def test_the_startup_backstop_follows_the_signed_window(
    window_end: str,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = LicenceState(
        "signed",
        "pro",
        date.fromisoformat(window_end),
        licence=signed_file.SignedLicence(
            id="TC-1",
            product="tancat",
            buyer_ref="x",
            purchased_at=date(2024, 1, 1),
            window_end=date.fromisoformat(window_end),
            tier="pro",
        ),
    )
    monkeypatch.setattr(entitlement, "resolve", lambda: state)

    code = cli_main.main([])

    captured = capsys.readouterr()
    if expected_exit == 3:
        assert code == 3, "a build past its window did not refuse to start"
        assert "after your update window ended" in captured.err
        assert window_end in captured.err
    else:
        assert code != 3


def test_the_upgrade_past_the_window_refuses_and_names_the_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state = LicenceState(
        "signed",
        "pro",
        date(2025, 1, 1),
        licence=signed_file.SignedLicence(
            id="TC-1",
            product="tancat",
            buyer_ref="x",
            purchased_at=date(2024, 1, 1),
            window_end=date(2025, 1, 1),
            tier="pro",
        ),
    )
    monkeypatch.setattr(entitlement, "resolve", lambda: state)

    assert cli_main.main(["update"]) == 3
    err = capsys.readouterr().err
    assert "2025-01-01" in err
    assert "keeps working" in err


def test_the_upgrade_inside_the_window_prints_the_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state = LicenceState(
        "signed",
        "pro",
        date(2099, 1, 1),
        licence=signed_file.SignedLicence(
            id="TC-1",
            product="tancat",
            buyer_ref="x",
            purchased_at=date(2026, 1, 1),
            window_end=date(2099, 1, 1),
            tier="pro",
        ),
    )
    monkeypatch.setattr(entitlement, "resolve", lambda: state)

    assert cli_main.main(["update"]) == 0
    out = capsys.readouterr().out
    assert "Upgrade TanCat" in out


def test_status_says_a_refused_file_is_there_and_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'Present, but refused' is not 'not present' - the buyer needs the difference."""
    accepted = tmp_path / "licence.signed.json"
    awarded = _write_signed(accepted, purchased="2026-11-01", window_end="2027-11-01")
    monkeypatch.setattr(signed_file, "VENDORED_PUBLIC_KEY_B64", awarded)
    document = accepted.read_text(encoding="utf-8")
    accepted.write_text(document.replace('"TC-2026-000321"', '"TC-2026-999999"'), encoding="utf-8")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(accepted))

    assert cli_main.main(["licence", "status"]) == 0
    out = capsys.readouterr().out
    assert "present, but refused" in out
    assert "Refused because:" in out
    assert "signature does not verify" in out
    assert "(not present)" not in out
    assert "Free Community" in out
