"""j-0317: the update window must govern the TIER, not only the upgrade gate.

The buyer pays for one version plus 12 months of updates. Past that window the
licence does not expire - the held version keeps working - but the tier is Free:
unlimited runs and exports were what the window bought.

This was broken on main (cbd3aa24): with a cache whose window ended in the past,
``license_status()`` said *valid / pro* and the meter reported no limits, so a
buyer past their window kept unlimited Pro. The audit fixed this in the signed-file
code, which the key-based rewrite deleted; nothing re-checked it here.

Every assertion below reads the ONE function that decides - ``license_status()`` -
and the two things that consume it: the meter and the sidebar sentence.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.licensing import entitlement
from src.licensing.license import license_status
from src.licensing.window import RELEASE_DATE, WINDOW_MONTHS, add_months


def _write(path: Path, *, created_at: str, status: str = "active", key: str = "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE") -> None:
    path.write_text(
        json.dumps(
            {
                "key": key,
                "instance_id": "lki_testinstance000000000000",
                "instance_name": "ci-runner",
                "status": status,
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


def _past_window_start() -> str:
    """A purchase date whose window ended a month before this build."""
    old = add_months(RELEASE_DATE, -(WINDOW_MONTHS + 1))
    return f"{old.isoformat()}T09:00:00.000Z"


def _inside_window_start() -> str:
    return f"{add_months(RELEASE_DATE, -1).isoformat()}T09:00:00.000Z"


class TestInsideTheWindow:
    def test_pro_and_unlimited(self, licence: Path) -> None:
        _write(licence, created_at=_inside_window_start())

        result = license_status()

        assert result.status == "valid"
        assert result.tier == "pro"
        assert result.usable

    def test_the_meter_shows_no_limits_and_the_sidebar_says_pro(self, licence: Path) -> None:
        from src.usage_meter import UsageMeter

        _write(licence, created_at=_inside_window_start())

        assert UsageMeter().runs_limit is None
        assert UsageMeter().exports_limit is None
        sentence = license_status().headline
        assert "pro" in sentence.lower()
        assert "window" not in sentence.lower()


class TestPastTheWindow:
    def test_the_tier_drops_to_free(self, licence: Path) -> None:
        _write(licence, created_at=_past_window_start())

        result = license_status()

        assert result.status == "valid", "the licence itself does not expire"
        assert result.tier == "free", "past the window the tier is Free"
        assert result.window_end, "the answer must still name the window end"

    def test_the_sentence_names_the_window_end_and_the_version_that_works(self, licence: Path) -> None:
        _write(licence, created_at=_past_window_start())

        sentence = license_status().headline

        assert "update window ended" in sentence
        assert result_end(licence) in sentence
        assert "keeps working" in sentence

    def test_the_meter_applies_the_free_limits(self, licence: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.usage_meter import UsageMeter

        _write(licence, created_at=_past_window_start())

        monkeypatch.delenv("AITEST_FREE_TIER_RUNS", raising=False)
        monkeypatch.delenv("AITEST_FREE_TIER_EXPORTS", raising=False)
        meter = UsageMeter()

        assert meter.runs_limit == 25
        assert meter.exports_limit == 10


class TestStatusRule:
    """Only "active" preserves the tier - the same rule activation applies.

    The first version of this fix listed "expired" and "disabled". That is a list,
    not a rule: "inactive", "revoked", "quarantined", an unknown word or an empty
    status all still granted Pro with no limits (j-0317 review).
    """

    @pytest.mark.parametrize("status", ["expired", "disabled", "inactive", "revoked", "quarantined", "weird-word"])
    def test_any_status_but_active_drops_the_tier(self, licence: Path, status: str) -> None:
        _write(licence, created_at=_inside_window_start(), status=status)

        result = license_status()

        assert result.tier == "free", f"status {status!r} still granted pro"
        assert status in result.headline.lower(), "the sentence must say what the store said"

    def test_an_empty_status_drops_the_tier(self, licence: Path) -> None:
        """No status at all is not permission."""
        _write(licence, created_at=_inside_window_start(), status="")

        result = license_status()

        assert result.tier == "free"
        assert "(no status)" in result.headline

    def test_active_inside_the_window_keeps_pro(self, licence: Path) -> None:
        _write(licence, created_at=_inside_window_start(), status="active")

        result = license_status()

        assert result.tier == "pro"

    def test_a_missing_licence_is_free_with_free_limits(self, licence: Path) -> None:
        from src.usage_meter import UsageMeter

        result = license_status()

        assert result.status == "unlicensed"
        assert result.tier == "free"
        assert UsageMeter().runs_limit == 25


def result_end(licence: Path) -> str:
    """The window end this cache implies, as the sentence should print it."""
    data = json.loads(licence.read_text(encoding="utf-8"))
    start = date.fromisoformat(str(data["created_at"])[:10])
    return add_months(start, WINDOW_MONTHS).isoformat()


def test_the_sidebar_does_not_draw_a_closed_window_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """j-0317 review: green is for a licence that is actually Pro."""
    from src.ui import ui_sidebar

    calls: list[tuple[str, str]] = []

    class FakeSidebar:
        def divider(self) -> None:
            return None

        def subheader(self, text: str) -> None:
            return None

        def success(self, text: str) -> None:
            calls.append(("success", text))

        def info(self, text: str) -> None:
            calls.append(("info", text))

        def error(self, text: str) -> None:
            calls.append(("error", text))

        def warning(self, text: str) -> None:
            return None

        def caption(self, text: str) -> None:
            return None

    class FakeStreamlit:
        sidebar = FakeSidebar()

    monkeypatch.setattr(ui_sidebar, "st", FakeStreamlit)
    monkeypatch.setattr(ui_sidebar.SidebarConfig, "_render_license_entry", staticmethod(lambda status: None))

    from src.licensing.license import LicenseResult

    closed = LicenseResult("valid", tier="free", reason="Your update window ended on 2026-10-13. ...")
    monkeypatch.setattr("src.licensing.license.license_status", lambda *a, **k: closed)
    ui_sidebar.SidebarConfig.render_license_usage()

    assert calls and calls[0][0] == "info", calls
