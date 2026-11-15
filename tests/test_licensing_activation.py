"""j-0304: activation, the licence file, and the 12-month update window.

The network is never touched here: every test supplies its own transport, and
every file goes to ``tmp_path``. The ten cases are the ones the build brief
lists.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from src.licensing import activation as A

ZERO_KEY = "00000000-0000-0000-0000-000000000000"

STORE = "1234"
PRODUCT = "5678"

GOOD_META = {
    "activated": True,
    "error": None,
    "license_key": {
        "id": 1,
        "status": "active",
        "key": ZERO_KEY,
        "activation_limit": 1,
        "activation_usage": 1,
        "created_at": "2026-11-10T09:00:00.000000Z",
        "expires_at": None,
    },
    "instance": {"id": "inst-1", "name": "TanCat deployment"},
    "meta": {"store_id": 1234, "product_id": 5678, "variant_id": 999, "product_name": "TanCat Pro Deployment"},
}


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The build under test knows its store and product."""
    monkeypatch.setattr(A, "STORE_ID", STORE)
    monkeypatch.setattr(A, "PRODUCT_ID", PRODUCT)
    monkeypatch.setattr(A, "VARIANT_ID", "999")


def _transport(status: int = 200, body: dict[str, Any] | None = None, error: str = "") -> Any:
    calls: list[tuple[str, dict[str, str]]] = []

    def post(url: str, fields: dict[str, str]) -> tuple[int, dict[str, Any], str]:
        calls.append((url, fields))
        return status, dict(body if body is not None else GOOD_META), error

    post.calls = calls  # type: ignore[attr-defined]
    return post


def _stored(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "licence.json").read_text(encoding="utf-8"))


def test_activation_success_stores_the_key_and_its_created_at(tmp_path: Path) -> None:
    post = _transport()

    result = A.activate(f"  {ZERO_KEY}  ", transport=post, path=tmp_path / "licence.json")

    assert result.ok, result.message
    assert "2027-11-10" in result.message, "the message does not name the window end"
    assert post.calls[0][0] == A.ACTIVATE_URL  # type: ignore[attr-defined]
    assert post.calls[0][1]["license_key"] == ZERO_KEY  # type: ignore[attr-defined]
    assert post.calls[0][1]["instance_name"]  # type: ignore[attr-defined]

    stored = _stored(tmp_path)
    assert stored["instance_id"] == "inst-1"
    assert stored["key_created_at"] == "2026-11-10"
    assert stored["expires_at"] is None
    assert stored["last_seen_at"]


def test_a_key_from_another_product_is_refused(tmp_path: Path) -> None:
    body = json.loads(json.dumps(GOOD_META))
    body["meta"]["product_id"] = 424242

    result = A.activate("key", transport=_transport(body=body), path=tmp_path / "licence.json")

    assert not result.ok
    assert "different product" in result.message
    assert not (tmp_path / "licence.json").exists(), "a refused key must not be stored"


def test_a_key_from_another_store_is_refused(tmp_path: Path) -> None:
    body = json.loads(json.dumps(GOOD_META))
    body["meta"]["store_id"] = 11

    result = A.activate("key", transport=_transport(body=body), path=tmp_path / "licence.json")

    assert not result.ok and "different store" in result.message
    assert not (tmp_path / "licence.json").exists()


def test_activation_limit_reached_is_explained(tmp_path: Path) -> None:
    body = json.loads(json.dumps(GOOD_META))
    body["activated"] = False
    body["license_key"]["activation_limit"] = 1
    body["license_key"]["activation_usage"] = 1

    result = A.activate("key", transport=_transport(body=body), path=tmp_path / "licence.json")

    assert not result.ok
    assert "maximum number of times" in result.message
    assert "hello@tancat.dev" in result.message


def test_an_invalid_key_says_what_to_do(tmp_path: Path) -> None:
    result = A.activate("nope", transport=_transport(status=404, body={}), path=tmp_path / "licence.json")

    assert not result.ok
    assert "not recognised" in result.message
    assert not (tmp_path / "licence.json").exists()


@pytest.mark.parametrize("status", [0, 500, 503])
def test_a_network_failure_fails_soft_and_keeps_the_existing_licence(tmp_path: Path, status: int) -> None:
    path = tmp_path / "licence.json"
    existing = {"key": ZERO_KEY, "key_created_at": "2025-01-01", "instance_id": "old-inst"}
    A.write_licence(existing, path)

    result = A.activate("key", transport=_transport(status=status, body={}, error="timed out"), path=path)

    assert not result.ok
    assert "could not reach" in result.message or "try again" in result.message
    assert _stored(tmp_path) == existing, "a failed activation changed the stored licence"


def test_a_build_with_no_ids_compiled_in_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline first run, or a build shipped before the ids are set: Free, plainly said."""
    monkeypatch.setattr(A, "STORE_ID", "")

    result = A.activate("key", transport=_transport(), path=tmp_path / "licence.json")

    assert not result.ok
    assert "no store_id" in result.message
    assert "accepting an unverified key" in result.message
    assert not (tmp_path / "licence.json").exists()


def test_one_day_inside_the_window_runs_and_one_day_outside_is_refused() -> None:
    """The window is a boundary, not a mood: +1 day, and it flips."""
    licence = {"key_created_at": "2026-11-10"}  # window ends 2027-11-10

    inside = A.startup_check(licence, build_date=date(2027, 11, 10), installed_version="1.2.0")
    assert inside.allowed, inside.message

    outside = A.startup_check(licence, build_date=date(2027, 11, 11), installed_version="1.2.0")
    assert not outside.allowed
    assert "2027-11-10" in outside.message

    # And the build that was inside still runs a decade later: it is the BUILD's
    # date that matters, not today's.
    assert A.startup_check(licence, build_date=date(2027, 11, 10)).allowed


def test_an_expired_build_is_refused_at_upgrade_time_and_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "licence.json"
    licence = {"key_created_at": "2026-11-10", "installed_version": "1.2.0"}
    A.write_licence(licence, path)
    before = path.read_text(encoding="utf-8")

    decision = A.upgrade_check(A.read_licence(path), build_date=date(2027, 12, 1), installed_version="1.2.0")

    assert not decision.allowed
    assert "2027-11-10" in decision.message, "the refusal does not name the window end"
    assert "Version 1.2.0 keeps working" in decision.message
    assert "tancat.dev" in decision.message
    assert path.read_text(encoding="utf-8") == before, "the upgrade gate touched the disk"


def test_a_newer_build_run_directly_refuses_to_start_and_names_the_way_back() -> None:
    licence = {"key_created_at": "2026-11-10", "installed_version": "1.2.0"}

    decision = A.startup_check(licence, build_date=date(2027, 12, 1), installed_version="1.2.0")

    assert not decision.allowed
    assert decision.window_end == date(2027, 11, 10)
    assert "released after your update window" in decision.message
    assert "keeps working" in decision.message
    assert "Renew" in decision.message


def test_no_licence_means_free_and_nothing_is_refused() -> None:
    decision = A.startup_check(None)

    assert decision.allowed
    assert "Free" in decision.message


def test_the_licence_file_is_plain_json_and_an_edit_moves_the_window(tmp_path: Path) -> None:
    """The accepted hole, asserted rather than pretended away."""
    path = tmp_path / "licence.json"
    A.write_licence({"key_created_at": "2025-01-01"}, path)

    licence = A.read_licence(path)
    assert licence is not None
    denied = A.startup_check(licence, build_date=date(2026, 6, 1))
    assert not denied.allowed

    # Hand-editing the date on the buyer's own disk moves the window. Documented
    # in the module docstring: a boundary for honest buyers, not DRM.
    licence["key_created_at"] = "2026-01-01"
    A.write_licence(licence, path)
    assert A.startup_check(A.read_licence(path), build_date=date(2026, 6, 1)).allowed


def test_a_renewal_with_a_newer_created_at_extends_the_window() -> None:
    """Renewal is not sold yet; a new key with a newer date simply extends it."""
    old = {"key_created_at": "2026-01-01"}
    renewed = {"key_created_at": "2027-01-01"}

    assert not A.startup_check(old, build_date=date(2027, 6, 1)).allowed
    assert A.startup_check(renewed, build_date=date(2027, 6, 1)).allowed


def test_add_months_clamps_to_the_end_of_a_short_month() -> None:
    assert A.add_months(date(2026, 1, 31), 12) == date(2027, 1, 31)
    assert A.add_months(date(2026, 11, 10), 12) == date(2027, 11, 10)
    assert A.add_months(date(2028, 2, 29), 12) == date(2029, 2, 28)


def test_activation_sends_exactly_one_request_and_nothing_periodic(tmp_path: Path) -> None:
    post = _transport()
    A.activate("key", transport=post, path=tmp_path / "licence.json")

    A.startup_check(A.read_licence(tmp_path / "licence.json"), build_date=date(2026, 12, 1))
    A.upgrade_check(A.read_licence(tmp_path / "licence.json"), build_date=date(2026, 12, 1))
    A.touch_last_seen(tmp_path / "licence.json")

    assert len(post.calls) == 1, "something called the network after activation"  # type: ignore[attr-defined]


def test_an_activation_without_a_created_at_is_refused(tmp_path: Path) -> None:
    body = json.loads(json.dumps(GOOD_META))
    body["license_key"]["created_at"] = None

    result = A.activate("key", transport=_transport(body=body), path=tmp_path / "licence.json")

    assert not result.ok
    assert "purchase date" in result.message
    assert not (tmp_path / "licence.json").exists()


def test_last_seen_is_recorded_without_a_call(tmp_path: Path) -> None:
    path = tmp_path / "licence.json"
    A.write_licence({"key": ZERO_KEY, "key_created_at": "2026-01-01"}, path)

    A.touch_last_seen(path, now=datetime(2026, 12, 1, 12, 0, 0))

    assert _stored(tmp_path)["last_seen_at"].startswith("2026-12-01T12:00:00")


# -- the real constants: the success path and each refusal, as committed -----


def _real_meta(**overrides: object) -> dict[str, Any]:
    """A response carrying the ids the module actually ships with."""
    meta: dict[str, Any] = {
        "store_id": int(A.STORE_ID),
        "product_id": int(A.PRODUCT_ID),
        "variant_id": int(A.VARIANT_ID),
    }
    meta.update(overrides)
    body = json.loads(json.dumps(GOOD_META))
    body["meta"] = meta
    return body


def test_the_committed_ids_activate_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The real constants, not dummies: all three ids matching must activate."""
    monkeypatch.undo()  # drop the autouse fixture's dummy ids
    assert A.STORE_ID == "471488" and A.PRODUCT_ID == "1521271" and A.VARIANT_ID == "2367450"
    assert A.STORE_ID.isdigit() and A.PRODUCT_ID.isdigit() and A.VARIANT_ID.isdigit()

    result = A.activate(ZERO_KEY, transport=_transport(body=_real_meta()), path=tmp_path / "licence.json")

    assert result.ok, result.message
    stored = _stored(tmp_path)
    assert stored["store_id"] == "471488"
    assert stored["product_id"] == "1521271"
    assert stored["variant_id"] == "2367450"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"store_id": 1}, "different store"),
        ({"product_id": 2}, "different product"),
        ({"variant_id": 3}, "different product variant"),
    ],
)
def test_the_real_constants_refuse_a_foreign_key_and_name_the_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overrides: dict[str, object], expected: str
) -> None:
    monkeypatch.undo()
    body = _real_meta(**overrides)

    result = A.activate(ZERO_KEY, transport=_transport(body=body), path=tmp_path / "licence.json")

    assert not result.ok
    assert expected in result.message, result.message
    assert not (tmp_path / "licence.json").exists()


def test_no_id_is_left_empty_in_the_committed_build() -> None:
    """The owner supplied them; an empty id would mean a build that cannot activate."""
    assert A.STORE_ID.strip() and A.PRODUCT_ID.strip() and A.VARIANT_ID.strip()


# -- j-0304 review: a response with no variant id, and last_seen moving -------


def test_a_response_with_no_variant_id_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An omitted field must not pass for a match."""
    monkeypatch.undo()  # the committed ids are set, so a variant is expected
    body = _real_meta()
    body["meta"].pop("variant_id")

    result = A.activate("key", transport=_transport(body=body), path=tmp_path / "licence.json")

    assert not result.ok
    assert "did not say which product variant" in result.message
    assert not (tmp_path / "licence.json").exists()


def test_a_response_with_no_variant_id_is_accepted_when_no_variant_is_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a build that deliberately has no variant id may accept an omission."""
    monkeypatch.setattr(A, "VARIANT_ID", "")
    body = json.loads(json.dumps(GOOD_META))
    body["meta"] = {"store_id": int(A.STORE_ID), "product_id": int(A.PRODUCT_ID)}
    body["meta"].pop("variant_id", None)

    result = A.activate("key", transport=_transport(body=body), path=tmp_path / "licence.json")

    assert result.ok, result.message


def test_a_second_start_moves_last_seen(tmp_path: Path) -> None:
    """touch_last_seen is called by the CLI at startup, so the field must move."""
    path = tmp_path / "licence.json"
    A.write_licence(
        {"key": ZERO_KEY, "key_created_at": "2026-01-01", "last_seen_at": "2026-01-01T00:00:00+00:00"}, path
    )

    A.touch_last_seen(path, now=datetime(2026, 11, 14, 9, 0, 0))
    first = _stored(tmp_path)["last_seen_at"]
    A.touch_last_seen(path, now=datetime(2026, 11, 14, 10, 0, 0))
    second = _stored(tmp_path)["last_seen_at"]

    assert first != second
    assert second.startswith("2026-11-14T10:00:00")
    assert _stored(tmp_path)["key_created_at"] == "2026-01-01", "touch changed the window"
