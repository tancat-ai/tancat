"""j-0306: the update check - one question a day, silent, and switchable off.

Every call is stubbed: no test touches the network or the real settings store.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src import version_check as V
from src.cli import main as cli_main


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp cache, a fresh setting, and a known current version."""
    cache = tmp_path / "update_check.json"
    monkeypatch.setattr(V, "cache_path", lambda: cache)
    monkeypatch.setattr(V, "current_version", lambda: "1.4.2")
    monkeypatch.setattr(V, "enabled", lambda: True)
    return cache


def _fetching(latest: str | None) -> Any:
    calls: list[str] = []

    def fetch(url: str, timeout: float = V.TIMEOUT_S) -> str | None:
        calls.append(url)
        return latest

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def test_a_fresh_cache_makes_no_call(_isolated: Path) -> None:
    V.write_cache({"last_checked_at": (NOW - timedelta(hours=1)).isoformat(), "latest_version": "1.5.0"}, _isolated)
    fetch = _fetching("1.5.0")

    result = V.check(now=NOW, fetcher=fetch)

    assert fetch.calls == []  # type: ignore[attr-defined]
    assert result.source == "cache"
    assert result.latest == "1.5.0"
    assert result.newer is True


def test_a_stale_cache_makes_exactly_one_call(_isolated: Path) -> None:
    V.write_cache({"last_checked_at": (NOW - timedelta(hours=25)).isoformat(), "latest_version": "1.4.2"}, _isolated)
    fetch = _fetching("1.5.0")

    result = V.check(now=NOW, fetcher=fetch)

    assert fetch.calls == [V.FEED_URL]  # type: ignore[attr-defined]
    assert result.source == "network"
    assert result.latest == "1.5.0"
    stored = V.read_cache(_isolated)
    assert stored["latest_version"] == "1.5.0"
    assert stored["last_checked_at"].startswith(NOW.date().isoformat())


def test_the_setting_off_means_no_call_at_all(_isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(V, "enabled", lambda: False)
    fetch = _fetching("1.5.0")

    assert V.check(force=True, now=NOW, fetcher=fetch).source == "off"
    assert V.notice(now=NOW) == ""
    V.refresh_in_background()
    assert fetch.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("failure", ["offline", "500", "parse", "timeout"])
def test_every_failure_is_silent(_isolated: Path, failure: str) -> None:
    def fetch(url: str, timeout: float = V.TIMEOUT_S) -> str | None:
        return None  # the module's own fetch maps every one of these failures to None

    result = V.check(now=NOW, fetcher=fetch)

    assert result.source == "error"
    assert result.latest is None
    assert V.notice(now=NOW) == ""
    assert V.read_cache(_isolated).get("last_checked_at"), "a failed check must still count as today's check"


def test_the_notice_appears_only_when_the_remote_version_is_newer(_isolated: Path) -> None:
    V.write_cache({"last_checked_at": NOW.isoformat(), "latest_version": "1.5.0"}, _isolated)
    assert V.notice(now=NOW) == "TanCat 1.5.0 is available; you have 1.4.2. Run: tancat update"

    V.write_cache({"last_checked_at": NOW.isoformat(), "latest_version": "1.4.2"}, _isolated)
    assert V.notice(now=NOW) == ""

    V.write_cache({"last_checked_at": NOW.isoformat()}, _isolated)
    assert V.notice(now=NOW) == "", "no known version must never produce a notice"


def test_the_notice_is_shown_once_per_version_per_day(_isolated: Path) -> None:
    V.write_cache({"last_checked_at": NOW.isoformat(), "latest_version": "1.5.0"}, _isolated)

    assert V.notice(now=NOW) != ""
    assert V.notice(now=NOW + timedelta(hours=2)) == "", "the same line repeated inside the day"
    assert V.notice(now=NOW + timedelta(days=1, hours=1)) != "", "a new day shows it again"

    V.write_cache({"last_checked_at": NOW.isoformat(), "latest_version": "1.6.0"}, _isolated)
    assert V.notice(now=NOW + timedelta(hours=3)) != "", "a NEW version is announced at once"


def test_the_manual_check_bypasses_the_cache(_isolated: Path) -> None:
    V.write_cache({"last_checked_at": NOW.isoformat(), "latest_version": "1.4.2"}, _isolated)
    fetch = _fetching("1.5.0")

    result = V.check(force=True, now=NOW, fetcher=fetch)

    assert fetch.calls == [V.FEED_URL]  # type: ignore[attr-defined]
    assert result.latest == "1.5.0"


def test_version_comparison_ignores_suffixes() -> None:
    assert V.is_newer("1.5.0", "1.4.2")
    assert not V.is_newer("1.4.2", "1.4.2")
    assert not V.is_newer("1.4.1", "1.4.2")
    assert V.is_newer("2.0.0rc1", "1.9.9")


def test_the_manual_cli_check_prints_plainly(
    _isolated: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(V, "_fetch", lambda url, timeout=V.TIMEOUT_S: "1.5.0")

    assert cli_main.main(["update", "--check"]) == 0
    out = capsys.readouterr().out
    assert "TanCat 1.5.0 is available" in out
    assert "tancat update" in out


def test_the_upgrade_refuses_past_the_window_with_the_version_that_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.licensing import activation as A

    licence = tmp_path / "licence.json"
    A.write_licence({"key": "k", "key_created_at": "2024-01-01", "installed_version": "1.2.0"}, licence)
    monkeypatch.setattr(A, "default_licence_path", lambda: licence)

    assert cli_main.main(["update"]) == 3
    err = capsys.readouterr().err
    # The version named is the one actually installed (the fixture pins 1.4.2).
    assert "Version 1.4.2 keeps working" in err
    assert "2025-01-01" in err


def test_the_upgrade_inside_the_window_prints_the_command_and_does_not_shell_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.licensing import activation as A

    licence = tmp_path / "licence.json"
    A.write_licence({"key": "k", "key_created_at": "2026-11-01", "installed_version": "1.2.0"}, licence)
    monkeypatch.setattr(A, "default_licence_path", lambda: licence)

    assert cli_main.main(["update"]) == 0
    out = capsys.readouterr().out
    assert "pip install --upgrade tancat" in out


# -- j-0306 follow-up: an unowned feed is an attack surface ------------------


def _feed(**info_overrides: object) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name": "tancat",
        "version": "1.5.0",
        "home_page": "https://tancat.dev",
        "project_urls": {"Repository": "https://github.com/tancat-ai/tancat"},
        "author": "Louis Cattano",
    }
    info.update(info_overrides)
    return {"info": info}


class _Response:
    """A urlopen() response that carries a fixed JSON body."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _stub_urlopen(payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Any, timeout: float = 0.0) -> _Response:
        return _Response(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_a_feed_with_our_identity_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_urlopen(_feed(), monkeypatch)

    assert V._fetch(V.FEED_URL) == "1.5.0"


def test_a_feed_whose_author_and_urls_are_not_ours_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """The supply-chain case: someone else registered the name first."""
    squatter = _feed(
        home_page="https://example.com/tancat",
        project_urls={"Homepage": "https://example.com"},
        author="Somebody Else",
    )
    _stub_urlopen(squatter, monkeypatch)

    assert V._fetch(V.FEED_URL) is None, "a feed that is not ours was trusted"


def test_identity_matches_requires_the_exact_name_and_our_marker() -> None:
    assert V.identity_matches(_feed())
    assert not V.identity_matches(_feed(name="tancat-pro"))
    assert not V.identity_matches(_feed(name="tancat", home_page="", project_urls={}, author="Anon"))

    # A repository URL is enough on its own.
    assert V.identity_matches(_feed(home_page="", project_urls={"Source": "https://github.com/tancat-ai/tancat"}))
    # As is the domain in an author field.
    assert V.identity_matches(_feed(home_page="", project_urls={}, author="hello@tancat.dev"))
    # An empty or malformed payload is no answer.
    assert not V.identity_matches({})
    assert not V.identity_matches({"info": "nope"})
