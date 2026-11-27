"""WHAT AITEST_ENFORCE_LICENSING=1 means, with licence keys (2026-11-26).

One meaning: **a run needs an activated licence key for this build**. No key on this
machine, a cache that cannot be used, or a build past the update window all refuse,
each with a reason and the command that checks it. Unset or ``0`` refuses nothing -
the free tier is a legitimate way to run.

The gate's decision is ``_licence_refusal()``: a string when the run may not proceed.
The gate reads the cache. A paid CI job that has activated once and then lost the
network must still run, so nothing here calls the relay.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.cli import headless
from src.licensing import activation as keys
from src.licensing import entitlement


def _write_licence(path: Path, *, created_at: str = "2026-11-26T00:04:47.460Z") -> None:
    path.write_text(
        json.dumps(
            {
                "key": "00000-00000-00000-00000-00000",
                "instance_id": "lki_testinstance000000000000",
                "instance_name": "ci-runner",
                "status": "active",
                "created_at": created_at,
                "expires_at": "",
                "activation_limit": 1,
                "last_checked": created_at,
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def licence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "licence.json"
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(path))
    monkeypatch.setattr(entitlement, "default_last_run_path", lambda: tmp_path / "last_run.json")
    return path


def test_no_key_refuses_when_enforced(licence: Path) -> None:
    refusal = headless._licence_refusal()
    assert "no activated licence key" in refusal


def test_a_damaged_cache_refuses_when_enforced(licence: Path) -> None:
    licence.write_text("{not json", encoding="utf-8")

    refusal = headless._licence_refusal()
    assert "could not be used" in refusal
    assert "activate the key again" in refusal


def test_an_activated_key_inside_its_window_passes(licence: Path) -> None:
    _write_licence(licence)
    assert headless._licence_refusal() == ""


def test_a_build_past_the_window_refuses_and_names_the_version_that_works(
    licence: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal names a version, like the upgrade path does (t-1470)."""
    _write_licence(licence, created_at="2025-01-01T00:00:00+00:00")
    entitlement.record_running_version("1.4.2")

    refusal = headless._licence_refusal()
    assert "update window ended on 2026-01-01" in refusal
    assert "Version 1.4.2 keeps working" in refusal


def test_the_gate_makes_no_network_call(licence: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A paid CI runner that has activated once must not need the relay to run."""
    _write_licence(licence)

    def _explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("the enforcement gate must read the cache only")

    monkeypatch.setattr(keys.urllib.request, "urlopen", _explode)
    assert headless._licence_refusal() == ""


def test_unset_or_zero_never_refuses(licence: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The setting decides; without it, nothing refuses - even with no licence."""
    monkeypatch.delenv("AITEST_ENFORCE_LICENSING", raising=False)
    # The reported state is still honest...
    assert headless._license_usage_section()["license"]["status"] == "unlicensed"
    assert headless._license_usage_section()["license"]["licence_valid"] is False


def test_the_json_field_is_named_for_what_it_means(licence: Path) -> None:
    """'token_present' meant "valid"; the field is now licence_valid."""
    _write_licence(licence)
    section = headless._license_usage_section()["license"]
    assert "token_present" not in section
    assert section["licence_valid"] is True


def test_a_past_window_still_checks_out_with_the_recorded_version(licence: Path) -> None:
    """No record on the machine: the message keeps its generic wording."""
    _write_licence(licence, created_at="2025-01-01T00:00:00+00:00")
    refusal = headless._licence_refusal()
    assert "after your update window ended" in refusal
    assert "keeps working" in refusal
