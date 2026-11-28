"""The licence key: activated once, checked at update, offline in between.

**The moments, and there are only three** (owner, 2026-11-26):

1. activation - once, when the key is entered, through our relay;
2. update - once per upgrade, through the same relay;
3. everything else - the cache, on disk, with no call at all.

Every test here is about one of those, and the last class is the one that keeps the
promise: startup, runs and premium features must make **no** network call.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.licensing import activation as keys
from src.licensing import entitlement
from src.licensing.license import LicenseStatus, license_status
from src.licensing.window import add_months


class _Response:
    """A relay answer, shaped like the one urllib returns."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _relay(monkeypatch: pytest.MonkeyPatch, status: int, body: dict[str, Any]) -> list[dict[str, Any]]:
    """Answer every relay call with *status*/*body*, and record what was sent."""
    sent: list[dict[str, Any]] = []

    def _fake_urlopen(request: Any, timeout: float = 0) -> _Response:
        sent.append({"url": getattr(request, "full_url", ""), "body": json.loads(request.data.decode("utf-8"))})
        if status == 0:
            raise urllib.error.URLError("no route to host")
        return _Response(status, body)

    monkeypatch.setattr(keys.urllib.request, "urlopen", _fake_urlopen)
    return sent


def _activation_body(created_at: str = "2026-11-26T00:04:47.460Z") -> dict[str, Any]:
    return {
        "activation": {
            "key": "00000-00000-00000-00000-00000",
            "status": "active",
            "created_at": created_at,
            "expires_at": "",
            "activation_limit": 1,
            "instance": {"id": "lki_testinstance000000000000", "name": "acme-laptop", "status": "active"},
        }
    }


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / "licence.json"


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def test_activation_stores_the_key_and_the_instance(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    sent = _relay(monkeypatch, 200, _activation_body())

    result = keys.activate("00000-00000-00000-00000-00000", "acme-laptop", path=cache)

    assert result.ok, result.message
    stored = json.loads(cache.read_text(encoding="utf-8"))
    assert stored["key"] == "00000-00000-00000-00000-00000"
    assert stored["instance_id"] == "lki_testinstance000000000000"
    assert stored["status"] == "active"
    assert stored["created_at"].startswith("2026-11-26")
    assert stored["last_checked"]
    assert sent and sent[0]["url"].endswith("/activate")
    assert sent[0]["body"]["operation"] == "activate"
    assert sent[0]["body"]["instance_name"] == "acme-laptop"


def test_activation_goes_to_our_relay_and_never_to_a_store(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    monkeypatch.setenv(keys.RELAY_URL_ENV, "https://relay.example.test")
    sent = _relay(monkeypatch, 200, _activation_body())

    keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert sent[0]["url"] == "https://relay.example.test/activate"


def test_a_triggered_limit_says_the_key_is_on_its_maximum_machines(
    monkeypatch: pytest.MonkeyPatch, cache: Path
) -> None:
    # t-1506: our relay always sends its own code with a 403; only a 403 with no code
    # is the edge's. This is what a limit refusal actually looks like.
    _relay(monkeypatch, 403, {"error": keys.ACTIVATION_LIMIT})

    result = keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert not result.ok
    assert result.code == keys.ACTIVATION_LIMIT
    assert "maximum number of machines" in result.message
    assert not cache.exists(), "a refused activation must not write a licence"


def test_an_unknown_key_is_not_recognised(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 404, {})

    result = keys.activate("WRONG-KEY", path=cache)

    assert result.code == keys.NOT_RECOGNISED
    assert "not recognised" in result.message
    assert not cache.exists()


def test_a_machine_already_released_is_told_so(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 409, {})

    result = keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert result.code == keys.ALREADY_RELEASED
    assert "already released" in result.message


def test_a_network_failure_leaves_the_product_on_the_free_tier(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 0, {})

    result = keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert not result.ok
    assert result.code == keys.UNREACHABLE
    assert "runs on the free tier until you connect and retry" in result.message
    assert not result.reachable
    assert not cache.exists()


def test_no_refusal_asks_the_buyer_to_pay_again(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """Every activation refusal, in one place: none of them asks for money."""
    for status in (403, 404, 409, 410, 500, 0):
        _relay(monkeypatch, status, {})
        result = keys.activate("00000-00000-00000-00000-00000", path=cache)
        lowered = result.message.lower()
        for word in ("pay", "purchase again", "buy again", "checkout"):
            assert word not in lowered, f"status {status} asks the buyer to {word}: {result.message}"


# ---------------------------------------------------------------------------
# Offline between the two moments
# ---------------------------------------------------------------------------


def test_after_activation_startup_makes_no_call(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", "acme-laptop", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))

    def _explode(*_a: object, **_k: object) -> None:
        raise AssertionError("startup must not call the relay")

    monkeypatch.setattr(keys.urllib.request, "urlopen", _explode)

    state = entitlement.resolve()
    decision = entitlement.startup_check()
    status = license_status()

    assert state.source == "activated"
    assert decision.allowed
    assert status.status == LicenseStatus.VALID
    assert status.tier == "pro"


def test_the_cache_is_the_truth_between_moments(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """The rule the whole design rests on: what is on disk is what the product runs.

    A relay that would now say 'revoked' changes nothing until an update happens.
    """
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))

    def _revoked(*_a: object, **_k: object) -> None:
        raise AssertionError("resolve() must not ask the store")

    monkeypatch.setattr(keys.urllib.request, "urlopen", _revoked)

    assert license_status().status == LicenseStatus.VALID
    assert entitlement.resolve().tier == "pro"


# ---------------------------------------------------------------------------
# The update gate
# ---------------------------------------------------------------------------


def test_update_with_a_valid_key_proceeds(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))
    _relay(monkeypatch, 200, {"status": "active"})

    decision = entitlement.upgrade_check(build_date=date(2027, 1, 1), installed_version="1.0.0")

    assert decision.allowed
    assert decision.message == ""


def test_update_with_a_revoked_key_refuses_and_names_the_working_version(
    monkeypatch: pytest.MonkeyPatch, cache: Path
) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))
    _relay(monkeypatch, 410, {})

    decision = entitlement.upgrade_check(build_date=date(2027, 1, 1), installed_version="1.0.0")

    assert not decision.allowed
    assert "revoked or expired" in decision.message
    assert "Version 1.0.0 keeps working" in decision.message


def test_update_with_no_network_proceeds_on_the_cached_licence(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))
    _relay(monkeypatch, 0, {})

    decision = entitlement.upgrade_check(build_date=date(2027, 1, 1), installed_version="1.0.0")

    assert decision.allowed, "our network must never block a paid upgrade"
    assert "could not reach the licence service" in decision.message.lower()
    assert "Proceeding on the licence stored on this machine" in decision.message


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


def test_the_window_is_twelve_months_from_the_key_date(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body("2026-11-26T00:04:47.460Z"))
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))

    state = entitlement.resolve()

    assert state.activated_on == date(2026, 11, 26)
    assert state.window_end == add_months(date(2026, 11, 26), 12)
    assert state.allows_build(state.window_end)
    assert not state.allows_build(state.window_end + timedelta(days=1))


def test_a_build_after_the_window_is_refused_by_cache_alone(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))

    decision = entitlement.startup_check(build_date=date(2028, 6, 1), installed_version="1.4.0")

    assert not decision.allowed
    assert "update window ended" in decision.message
    assert "Version 1.4.0 keeps working" in decision.message


def test_a_key_created_late_on_31_december_still_gets_a_full_year(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """The store creates the key seconds after the order; the date carries the window."""
    _relay(monkeypatch, 200, _activation_body("2026-12-31T23:59:30.000Z"))
    keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert keys.load(cache)[0].window_end == date(2027, 12, 31)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Release, and the failure that must not lose a licence
# ---------------------------------------------------------------------------


def test_release_removes_the_cache_and_tells_the_relay(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    sent = _relay(monkeypatch, 200, {"released": True})

    ok, message = keys.deactivate(path=cache)

    assert ok, message
    assert not cache.exists()
    assert sent[0]["url"].endswith("/deactivate")
    assert sent[0]["body"]["instance_id"] == "lki_testinstance000000000000"


def test_a_failed_activation_never_removes_a_working_licence(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    before = cache.read_text(encoding="utf-8")
    _relay(monkeypatch, 403, {})

    result = keys.activate("SOMEONE-ELSES-KEY", path=cache)

    assert not result.ok
    assert cache.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# t-1505: a 200 answer is not a pass. Only "active" opens the update gate.
# ---------------------------------------------------------------------------


def _licence_in_force(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("inactive", keys.INACTIVE),
        ("disabled", keys.DISABLED),
        ("expired", keys.EXPIRED),
    ],
)
def test_a_200_that_names_a_dead_state_refuses_the_upgrade(
    monkeypatch: pytest.MonkeyPatch, cache: Path, state: str, code: str
) -> None:
    """The reviewer served exactly this shape and the upgrade went ahead (t-1505).

    A 200 with a status word that is not "active" is the store saying the key is
    dead. It must refuse, and it must say which kind of dead.
    """
    _licence_in_force(monkeypatch, cache)
    _relay(monkeypatch, 200, {"status": state})

    checked = keys.validate()

    assert checked.kind == "refused", f"a 200 {state!r} answer was read as {checked.kind!r}"
    assert checked.code == code
    assert checked.message
    decision = entitlement.upgrade_check(build_date=date(2027, 1, 1), installed_version="1.0.0")
    assert not decision.allowed, f"a {state} key allowed the upgrade"
    assert "Version 1.0.0 keeps working" in decision.message


def test_a_200_with_no_status_is_refused_as_unreadable(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """No status at all used to default to "active" - the other half of the hole."""
    _licence_in_force(monkeypatch, cache)
    _relay(monkeypatch, 200, {"expires_at": ""})

    checked = keys.validate()

    assert checked.kind == "refused"
    assert checked.code == keys.UNKNOWN_STATUS
    assert "does not understand" in checked.message
    assert "check for an update" in checked.message
    assert not entitlement.upgrade_check(build_date=date(2027, 1, 1)).allowed


def test_a_200_with_an_unknown_status_is_refused_not_guessed(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """A future state word must fail closed, or a new store state silently pays."""
    _licence_in_force(monkeypatch, cache)
    _relay(monkeypatch, 200, {"status": "quarantined"})

    checked = keys.validate()

    assert checked.kind == "refused"
    assert checked.code == keys.UNKNOWN_STATUS
    assert not entitlement.upgrade_check(build_date=date(2027, 1, 1)).allowed


def test_a_refusal_does_not_rewrite_the_cache(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """A dead answer is not written over a licence the buyer may still roll back to."""
    _licence_in_force(monkeypatch, cache)
    before = cache.read_text(encoding="utf-8")
    _relay(monkeypatch, 200, {"status": "inactive"})

    keys.validate()

    assert cache.read_text(encoding="utf-8") == before, "the cache was rewritten from a refusal"


def test_only_active_passes_the_gate(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """The positive control, so the refusals above are not passing for the wrong reason."""
    _licence_in_force(monkeypatch, cache)
    _relay(monkeypatch, 200, {"status": "Active", "expires_at": ""})

    checked = keys.validate()

    assert checked.kind == "ok", checked.message
    assert entitlement.upgrade_check(build_date=date(2027, 1, 1)).allowed


# ---------------------------------------------------------------------------
# t-1506: the edge rejects a default user agent, and its 403 is not our 403
# ---------------------------------------------------------------------------


def test_every_relay_call_names_the_product_in_its_user_agent(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """Cloudflare answers 403 error 1010 to Python's default agent (t-1506).

    Every call must carry a product string instead, or activation is blocked before
    it reaches the relay and the buyer is told only "could not reach".
    """
    seen: list[str] = []

    class _Ok:
        status = 500

        def read(self) -> bytes:
            return b"{}"

        def __enter__(self) -> _Ok:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def _capture(request: Any, timeout: float = 0) -> _Ok:
        seen.append(request.get_header("User-agent") or request.headers.get("User-agent", ""))
        return _Ok()

    monkeypatch.setattr(keys.urllib.request, "urlopen", _capture)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))

    keys.activate("00000-00000-00000-00000-00000", path=cache)
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setattr(keys.urllib.request, "urlopen", _capture)
    keys.validate(path=cache)
    keys.deactivate(path=cache)

    assert seen, "no relay call was made"
    for agent in seen:
        assert agent.startswith("TanCat/"), f"a relay call went out with {agent!r}"
        assert "tancat.dev" in agent
        assert "urllib" not in agent.lower()


def test_the_user_agent_follows_the_product_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.version_info as version_info

    monkeypatch.setattr(version_info, "installed_version", lambda: "9.9.9")

    assert keys.user_agent() == "TanCat/9.9.9 (+https://tancat.dev)"


def test_an_edge_403_is_not_read_as_the_buyers_key_being_full(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """A 403 with no JSON code came from the edge; the buyer's key is not at fault."""
    _relay(monkeypatch, 403, {})

    result = keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert not result.ok
    assert result.code == keys.BLOCKED_AT_EDGE
    assert "edge error 1010" in result.message
    assert "fault at our end" in result.message
    assert "hello@tancat.dev" in result.message
    assert "maximum number of machines" not in result.message
    assert not cache.exists()


def test_a_relay_403_with_its_own_code_is_still_the_activation_limit(
    monkeypatch: pytest.MonkeyPatch, cache: Path
) -> None:
    """The positive control: our relay's coded 403 keeps meaning what it says."""
    _relay(monkeypatch, 403, {"error": keys.ACTIVATION_LIMIT})

    result = keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert result.code == keys.ACTIVATION_LIMIT
    assert "maximum number of machines" in result.message


def test_an_edge_403_at_update_does_not_block_the_upgrade(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """Our edge is our fault: the buyer proceeds on the cached licence and is told."""
    _relay(monkeypatch, 200, _activation_body())
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))
    _relay(monkeypatch, 403, {})

    checked = keys.validate()
    decision = entitlement.upgrade_check(build_date=date(2027, 1, 1), installed_version="1.0.0")

    assert checked.kind == "network", f"an edge block was read as {checked.kind!r}"
    assert checked.code == keys.BLOCKED_AT_EDGE
    assert decision.allowed, "our edge blocked a paid upgrade"
    assert "edge error 1010" in decision.message


# ---------------------------------------------------------------------------
# t-1524: a refusal says what works and how to get back to it
# ---------------------------------------------------------------------------


def test_a_closed_window_names_the_end_and_the_command_back(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    """The sentence a buyer sees: the window end, the held version, and the command."""
    _relay(monkeypatch, 200, _activation_body("2025-01-01T00:00:00+00:00"))
    keys.activate("00000-00000-00000-00000-00000", path=cache)
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))

    decision = entitlement.startup_check(build_date=date(2026, 6, 1), installed_version="0.1.0")

    assert not decision.allowed
    assert "update window ended on 2026-01-01" in decision.message
    assert "Version 0.1.0 keeps working" in decision.message
    assert "pip install 'tancat==0.1.0'" in decision.message
    assert "nothing on disk has changed" not in decision.message


def test_a_refused_key_names_the_held_version_and_how_to_return(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _licence_in_force(monkeypatch, cache)
    _relay(monkeypatch, 410, {})

    decision = entitlement.upgrade_check(build_date=date(2027, 1, 1), installed_version="0.1.0")

    assert not decision.allowed
    assert "The upgrade was not installed" in decision.message
    assert "Version 0.1.0 keeps working" in decision.message
    assert "pip install 'tancat==0.1.0'" in decision.message
    assert "nothing on disk has changed" not in decision.message


def test_with_no_recorded_version_the_refusal_still_points_somewhere() -> None:
    sentence = entitlement.held_version_sentence("")

    assert sentence == "The version you already have keeps working."


def test_a_v_prefix_is_not_doubled_in_the_command() -> None:
    assert entitlement.install_command("v0.1.0") == "pip install 'tancat==0.1.0'"
