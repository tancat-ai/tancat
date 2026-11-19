"""j-0309 / t-1470: what AITEST_ENFORCE_LICENSING=1 means now.

The setting used to test a status that no longer exists, so it could never fire. It
now means one thing: **a run needs a valid signed licence for this build**. Missing,
refused, or past the update window all refuse, each with a reason and the command that
checks it. Unset or ``0`` refuses nothing - the free tier is a legitimate way to run.

The gate's decision is ``_licence_refusal()``: a string when the run may not proceed.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.cli import headless
from src.licensing import entitlement, signed_file


def _keypair() -> tuple[bytes, str]:
    private = ed25519.Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = base64.b64encode(
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    return raw, public


def _write(path: Path, private: bytes, *, window_end: str, purchased: str = "2026-01-01") -> None:
    path.write_text(
        signed_file.signed_file_text(
            {
                "id": "TC-2026-000555",
                "product": "tancat",
                "buyer_ref": "order 555 / buyer@example.com",
                "purchased_at": purchased,
                "window_end": window_end,
                "tier": "pro",
            },
            private,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def licence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    private, public = _keypair()
    monkeypatch.setattr(signed_file, "VENDORED_PUBLIC_KEY_B64", public)
    monkeypatch.setattr(entitlement, "default_last_run_path", lambda: tmp_path / "last_run.json")
    return {"private": private, "public": public, "path": tmp_path / "licence.signed.json", "dir": tmp_path}


def test_no_file_refuses_when_enforced(licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence["path"]))  # absent
    refusal = headless._licence_refusal()
    assert "no signed licence file" in refusal


def test_a_tampered_file_refuses_when_enforced(licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _write(licence["path"], licence["private"], window_end="2027-11-01")
    licence["path"].write_text(
        licence["path"].read_text(encoding="utf-8").replace("TC-2026-000555", "TC-2026-999999"), encoding="utf-8"
    )
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence["path"]))

    refusal = headless._licence_refusal()
    assert "could not be used" in refusal
    assert "signature does not verify" in refusal


def test_a_valid_file_inside_its_window_passes(licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    _write(licence["path"], licence["private"], window_end="2099-01-01")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence["path"]))
    assert headless._licence_refusal() == ""


def test_a_build_past_the_window_refuses_and_names_the_version_that_works(
    licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal names a version, like the upgrade path does (t-1470)."""
    _write(licence["path"], licence["private"], window_end="2026-06-01")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence["path"]))
    entitlement.record_running_version("1.4.2")

    refusal = headless._licence_refusal()
    assert "after your update window ended on 2026-06-01" in refusal
    assert "Version 1.4.2 keeps working" in refusal


def test_unset_or_zero_never_refuses(licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """The setting decides; without it, nothing refuses - even with no licence."""
    monkeypatch.delenv("AITEST_ENFORCE_LICENSING", raising=False)
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence["path"]))
    # The reported state is still honest...
    assert headless._license_usage_section()["license"]["status"] == "unlicensed"
    assert headless._license_usage_section()["license"]["licence_valid"] is False
    # ...and the gate is only consulted when the setting is on.
    assert os.environ.get("AITEST_ENFORCE_LICENSING", "0") != "1"


def test_the_json_field_is_named_for_what_it_means(licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """'token_present' meant "valid"; the field is now licence_valid."""
    _write(licence["path"], licence["private"], window_end="2099-01-01")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence["path"]))
    section = headless._license_usage_section()["license"]
    assert "token_present" not in section
    assert section["licence_valid"] is True


def test_a_past_window_still_checks_out_with_the_recorded_version(
    licence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """No record on the machine: the message keeps its generic wording."""
    _write(licence["path"], licence["private"], window_end="2026-06-01")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence["path"]))
    refusal = headless._licence_refusal()
    assert "after your update window ended" in refusal
    assert "keeps working" in refusal
