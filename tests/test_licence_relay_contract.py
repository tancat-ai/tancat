"""The relay and the product, held together by a real exchange, not a string match.

`services/licence-relay` is JavaScript and the product is Python, so nothing in a
type checker holds them together. An earlier version of this file searched the
Worker's source for field names; the reviewer renamed `expires_at` to `expiresAt` on
the Worker side alone and it still passed 15/15 (t-1505).

This version **runs the Worker** (Node, with the store's answer stubbed) and feeds
its answer to **the product's own parser**. A rename on either side fails here:
the Worker emits a key the product does not read, or the product reads one the
Worker stopped emitting.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.licensing import activation as keys

REPO_ROOT = Path(__file__).resolve().parent.parent
RELAY = REPO_ROOT / "services" / "licence-relay"
WORKER = RELAY / "src" / "index.js"
HARNESS = Path(__file__).resolve().parent / "relay_harness.mjs"
CONFIG = RELAY / "wrangler.toml"
README = RELAY / "README.md"

#: The activation body the store returned when the licence-key feature was read live
#: on 2026-11-26: the licence object, wrapped in a ``license`` key.
UPSTREAM_ACTIVATION: dict[str, Any] = {
    "license": {
        "id": "lk_7M7gsZ4EYrLmyxYhH4kJ0E",
        "product_id": "prod_3TN3d9ubb7PATzddFFuDT",
        "status": "active",
        "key": "00000-00000-00000-00000-00000",
        "activation": 1,
        "activation_limit": 1,
        "expires_at": None,
        "created_at": "2026-11-26T00:04:47.460Z",
        "instance": {"id": "lki_testinstance000000000000", "name": "acme-laptop", "status": "active"},
    }
}


def _node() -> str:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - depends on the machine
        pytest.skip("node is not installed, so the Worker cannot be exercised")
    assert node is not None
    return node


def _worker(
    operation: str,
    request: dict[str, Any],
    *,
    upstream: dict[str, Any],
    status: int = 200,
    env: dict[str, Any] | None = None,
) -> Any:
    """Run one request through the real Worker and return ``(status, body)``."""
    proc = subprocess.run(
        [
            _node(),
            str(HARNESS),
            operation,
            json.dumps(request),
            str(status),
            json.dumps(upstream),
            json.dumps(env or {}),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, f"the Worker harness failed: {proc.stderr[-800:]}"
    answer = json.loads(proc.stdout)
    return answer["status"], answer["body"]


def _product_request(monkeypatch: pytest.MonkeyPatch, action: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run a product call and capture the exact body it sent to the relay."""
    sent: list[dict[str, Any]] = []

    class _Answer:
        status = 500

        def read(self) -> bytes:
            return b"{}"

        def __enter__(self) -> _Answer:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def _capture(request: Any, timeout: float = 0) -> _Answer:
        sent.append(json.loads(request.data.decode("utf-8")))
        return _Answer()

    monkeypatch.setattr(keys.urllib.request, "urlopen", _capture)
    action(*args, **kwargs)
    assert sent, "the product made no request"
    return sent[0]


# ---------------------------------------------------------------------------
# The exchange
# ---------------------------------------------------------------------------


def test_the_activation_body_the_product_sends_is_accepted_by_the_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request = _product_request(monkeypatch, keys.activate, "00000-00000-00000-00000-00000", "acme-laptop")
    assert request.pop("operation") == "activate"

    status, body = _worker("activate", request, upstream=UPSTREAM_ACTIVATION)

    assert status == 200, body
    assert set(body) == {"activation"}, f"the Worker's activation answer changed shape: {sorted(body)}"


def test_the_worker_answer_parses_into_the_cache_the_product_writes(tmp_path: Path) -> None:
    """The structural check: Worker answer -> product parser -> cache fields.

    Rename ``created_at`` on the Worker side and the window loses its start date;
    rename it here and the parser looks for a key nobody sends. Either way this
    fails.
    """
    status, body = _worker(
        "activate",
        {"key": "00000-00000-00000-00000-00000", "instance_name": "acme-laptop"},
        upstream=UPSTREAM_ACTIVATION,
    )
    assert status == 200, body

    activation = keys._activation_from(body, key="00000-00000-00000-00000-00000", instance_name="acme-laptop")

    assert activation is not None, "the product could not parse the Worker's answer"
    assert activation.key == "00000-00000-00000-00000-00000"
    assert activation.instance_id == "lki_testinstance000000000000", "the instance id did not cross the boundary"
    assert activation.instance_name == "acme-laptop"
    assert activation.status == "active"
    assert activation.activation_limit == 1
    assert activation.created_at == "2026-11-26T00:04:47.460Z", "the key's date - and so the whole window - was lost"
    assert activation.activated_on is not None
    assert activation.window_end == keys.add_months(activation.activated_on, keys.WINDOW_MONTHS)


def test_the_validate_answer_is_the_one_the_product_reads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The answer names the state and the expiry; the gate must read both."""
    cache = tmp_path / "licence.json"
    keys.save(
        keys.Activation(
            key="00000-00000-00000-00000-00000",
            instance_id="lki_testinstance000000000000",
            instance_name="acme-laptop",
            status="active",
            created_at="2026-11-26T00:04:47.460Z",
        ),
        cache,
    )
    request = _product_request(monkeypatch, keys.validate, path=cache)
    assert request.pop("operation") == "validate"

    status, body = _worker(
        "validate",
        request,
        upstream={"license": {"status": "active", "expires_at": "2027-11-26T00:00:00Z"}},
    )

    assert status == 200, body
    assert set(body) == {"status", "expires_at"}, f"the validate answer changed shape: {sorted(body)}"
    assert body["status"] == "active"
    assert body["expires_at"] == "2027-11-26T00:00:00Z"


def test_the_product_treats_an_inactive_worker_answer_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End to end: the store says disabled, the Worker passes it through, the gate shuts."""
    cache = tmp_path / "licence.json"
    keys.save(
        keys.Activation(
            key="00000-00000-00000-00000-00000",
            instance_id="lki_testinstance000000000000",
            instance_name="acme-laptop",
            status="active",
            created_at="2026-11-26T00:04:47.460Z",
        ),
        cache,
    )
    _status, body = _worker(
        "validate",
        {"key": "00000-00000-00000-00000-00000", "instance_id": "lki_testinstance000000000000"},
        upstream={"license": {"status": "inactive", "expires_at": None}},
    )

    monkeypatch.setattr(keys.urllib.request, "urlopen", lambda *a, **k: _Answer(body))
    checked = keys.validate(path=cache)

    assert checked.kind == "refused", f"an inactive answer was read as {checked.kind!r}"


class _Answer:
    def __init__(self, body: dict[str, Any]) -> None:
        self._raw = json.dumps(body).encode("utf-8")
        self.status = 200

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_the_deactivate_answer_is_the_one_the_product_reads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    status, body = _worker(
        "deactivate",
        {"key": "00000-00000-00000-00000-00000", "instance_id": "lki_testinstance000000000000"},
        upstream={"license": {"status": "inactive"}},
    )
    assert status == 200
    assert body == {"released": True}, f"the deactivate answer changed shape: {body}"


@pytest.mark.parametrize("operation", ["unknown", "activate/extra"])
def test_an_unknown_path_is_refused_by_the_worker(operation: str) -> None:
    status, body = _worker(operation, {"key": "x"}, upstream={})
    assert status == 404
    assert body == {"error": "not_found"}


def test_a_store_refusal_reaches_the_product_as_our_code() -> None:
    """The Worker translates the store's status; the product maps our code to copy."""
    status, body = _worker(
        "validate",
        {"key": "00000-00000-00000-00000-00000", "instance_id": "lki_x"},
        upstream={},
        status=410,
    )
    assert status == 410
    assert body == {"error": keys.REVOKED_OR_EXPIRED}


# ---------------------------------------------------------------------------
# Static rules that are about the repository, not the exchange
# ---------------------------------------------------------------------------


def test_the_worker_ships_the_three_operations() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    for operation in ("activate", "validate", "deactivate"):
        assert f"/v1/licenses/{operation}" in worker, f"the Worker does not forward {operation}"


def test_every_error_code_the_product_maps_exists_in_the_worker() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    for code in (keys.ACTIVATION_LIMIT, keys.NOT_RECOGNISED, keys.ALREADY_RELEASED, keys.REVOKED_OR_EXPIRED):
        assert code in worker, f"the Worker never emits {code}, which the product maps"
    # The product's two extra codes are its own reading of an answer it cannot use.
    assert "upstream_error" in worker


def test_no_provider_name_reaches_a_buyer() -> None:
    worker = WORKER.read_text(encoding="utf-8").lower()
    for name in ("creem", "lemonsqueezy", "lemon squeezy", "paddle", "stripe", "gumroad", "polar"):
        assert name not in worker, f"the Worker names {name}"


def test_the_merchant_key_comes_from_the_environment_only() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    assert "env.API_KEY" in worker, "the Worker must read the key from its secret binding"
    assert "x-api-key" in worker.lower() or "x-api-key" in worker


def test_the_upstream_host_is_not_committed() -> None:
    """Read the COMMITTED file: a deployed machine may hold a real host in its tree."""
    config = subprocess.run(
        ["git", "show", f"HEAD:{CONFIG.relative_to(REPO_ROOT).as_posix()}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert ".invalid" in config, "API_BASE must be a placeholder that fails closed until deployed"
    assert "creem" not in config.lower()


def test_cors_is_restricted_to_one_origin() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    assert "'*'" not in worker, "a wildcard origin lets any page call the relay"
    assert "ALLOWED_ORIGIN" in CONFIG.read_text(encoding="utf-8")
    assert "Access-Control-Allow-Origin" in worker


def test_the_readme_states_what_it_does_not_protect() -> None:
    text = README.read_text(encoding="utf-8")
    section = text.split("What it does NOT protect against", 1)
    assert len(section) == 2, "the README has no 'what it does NOT protect against' section"
    body = section[1].lower()
    for point in ("not drm", "between updates", "single point of failure", "api key"):
        assert point in body, f"the README does not state: {point}"


def test_the_readme_gives_the_deploy_steps_and_the_secret() -> None:
    text = README.read_text(encoding="utf-8")
    assert "wrangler deploy" in text
    assert "wrangler secret put API_KEY" in text
    assert "AITEST_LICENCE_RELAY_URL" in text
    for path in ("/activate", "/validate", "/deactivate"):
        assert path in text


# ---------------------------------------------------------------------------
# t-1506: the deploy's fail-closed states, pinned through the real Worker
# ---------------------------------------------------------------------------


def test_with_no_merchant_secret_the_worker_fails_closed() -> None:
    """No secret, no upstream call: a 503 with our own code, never a pass."""
    status, body = _worker(
        "activate",
        {"key": "00000-00000-00000-00000-00000", "instance_name": "acme-laptop"},
        upstream=UPSTREAM_ACTIVATION,
        env={"API_KEY": ""},
    )

    assert status == 503, f"an unset secret answered {status}"
    assert body == {"error": "upstream_error"}


def test_with_no_upstream_base_the_worker_fails_closed() -> None:
    status, body = _worker(
        "validate",
        {"key": "00000-00000-00000-00000-00000", "instance_id": "lki_x"},
        upstream={},
        env={"API_BASE": ""},
    )

    assert status == 503
    assert body == {"error": "upstream_error"}


@pytest.mark.parametrize("operation", ["unknown", "activate/extra", "", "v1/licenses/activate"])
def test_an_unknown_path_answers_not_found(operation: str) -> None:
    status, body = _worker(operation, {"key": "x"}, upstream={})
    assert status == 404, f"{operation!r} answered {status}"
    assert body == {"error": "not_found"}


PROVIDER_WORDS = ("creem", "lemonsqueezy", "lemon squeezy", "paddle", "stripe", "gumroad", "polar")


@pytest.mark.parametrize("status", [200, 403, 404, 409, 410, 500, 503])
@pytest.mark.parametrize("operation", ["activate", "validate", "deactivate"])
def test_no_response_body_names_the_store(operation: str, status: int) -> None:
    """Every body this relay can emit is buyer-visible; none may name the provider."""
    _code, body = _worker(
        operation,
        {"key": "00000-00000-00000-00000-00000", "instance_name": "acme", "instance_id": "lki_x"},
        upstream=UPSTREAM_ACTIVATION if status == 200 else {"error": "creem says no", "message": "Creem returned 410"},
        status=status,
    )

    rendered = json.dumps(body).lower()
    named = [word for word in PROVIDER_WORDS if word in rendered]
    assert named == [], f"{operation} at {status} names {named} in its body: {body}"


def test_an_upstream_message_never_reaches_the_caller() -> None:
    """The store's own wording can carry its name; ours is a code and nothing else."""
    _status, body = _worker(
        "activate",
        {"key": "00000-00000-00000-00000-00000", "instance_name": "acme"},
        upstream={"error": "licence_limit_reached", "detail": "Contact Creem support for order 123"},
        status=403,
    )

    assert set(body) == {"error"}, f"an upstream field leaked through: {sorted(body)}"


# ---------------------------------------------------------------------------
# t-1508: the store does not use the status codes its reference page implies
# ---------------------------------------------------------------------------

#: The bodies the live test API actually returned on 2026-11-26, recorded verbatim
#: (including the store's "instnace" misspelling). A status-only mapping told a buyer
#: "could not reach the licence service" when the truth was "this key is already in
#: use", so these fixtures are what stops the mapping drifting back.
RECORDED = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "relay" / "store-error-bodies.json").read_text(encoding="utf-8")
)


def test_the_recorded_fixtures_are_the_store_bodies() -> None:
    """Guard the fixture itself: the 400 shapes and the misspelling must survive."""
    cases = {case["what"]: case for case in RECORDED["cases"]}
    limit = cases["the single activation is already used"]
    assert limit["status"] == 400, "the live store answers 400 for a spent activation limit, not 403"
    assert limit["body"]["message"] == "Activation limit reached"
    released = cases["the instance was already released"]
    assert released["status"] == 400, "the live store answers 400 for an already-released instance, not 409"
    assert "instnace" in released["body"]["message"], (
        "the store's misspelling was tidied away, which hides the real body"
    )


@pytest.mark.parametrize("case", RECORDED["cases"], ids=[case["what"] for case in RECORDED["cases"]])
def test_each_recorded_store_body_becomes_our_code(case: dict[str, Any]) -> None:
    """The Worker classifies a real body; the body out is ours alone."""
    body = {
        "key": "00000-00000-00000-00000-00000",
        "instance_name": "acme-laptop",
        "instance_id": "lki_testinstance000000000000",
    }

    status, answer = _worker(case["operation"], body, upstream=case["body"], status=case["status"])

    assert status == case["status"], f"the Worker changed the status: {status}"
    assert answer == {"error": case["expect"]}, f"{case['what']}: {answer}"
    rendered = json.dumps(answer).lower()
    for word in ("activation limit reached", "instnace", "bad request", "license key"):
        assert word not in rendered, f"the store's text reached the caller: {answer}"


@pytest.mark.parametrize("case", RECORDED["cases"], ids=[case["what"] for case in RECORDED["cases"]])
def test_the_product_says_the_right_sentence_for_each_recorded_body(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End to end: the store's real answer, the relay's code, the buyer's sentence."""
    cache = tmp_path / "licence.json"
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))
    keys.save(
        keys.Activation(
            key="00000-00000-00000-00000-00000",
            instance_id="lki_testinstance000000000000",
            instance_name="acme-laptop",
            status="active",
            created_at="2026-11-26T00:04:47.460Z",
        ),
        cache,
    )
    status, answer = _worker(
        case["operation"],
        {"key": "k", "instance_name": "n", "instance_id": "i"},
        upstream=case["body"],
        status=case["status"],
    )

    class _Answer:
        def __init__(self, code: int, payload: dict[str, Any]) -> None:
            self.status = code
            self._raw = json.dumps(payload).encode("utf-8")

        def read(self) -> bytes:
            return self._raw

        def __enter__(self) -> _Answer:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(keys.urllib.request, "urlopen", lambda *a, **k: _Answer(status, answer))

    # The product's own word for "the relay could not classify it" is unreachable.
    expected = keys.UNREACHABLE if case["expect"] == "upstream_error" else case["expect"]

    if case["operation"] == "activate":
        result = keys.activate("00000-00000-00000-00000-00000", path=cache)
        assert not result.ok, f"{case['what']} was accepted"
        assert result.code == expected, f"{case['what']}: {result.code}"
        if case["expect"] != "upstream_error":
            assert "could not reach the licence service" not in result.message.lower()
    else:
        checked = keys.validate(path=cache)
        assert checked.kind in ("refused", "network"), f"{case['what']} was read as {checked.kind!r}"
        assert checked.code == case["expect"], f"{case['what']}: {checked.code}"


def test_the_limit_message_is_the_buyers_sentence_not_ours() -> None:
    """The exact live failure: a 400 'Activation limit reached' must say so."""
    status, answer = _worker(
        "activate",
        {"key": "00000-00000-00000-00000-00000", "instance_name": "acme-laptop"},
        upstream={"status": 400, "error": "Bad Request", "message": "Activation limit reached"},
        status=400,
    )
    assert (status, answer) == (400, {"error": "activation_limit"})


def test_the_relays_unclassified_code_reads_as_no_usable_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`upstream_error` is a code the product must know, not fall through on."""
    cache = tmp_path / "licence.json"
    monkeypatch.setenv(keys.CACHE_ENV, str(cache))
    monkeypatch.setattr(
        keys.urllib.request, "urlopen", lambda *a, **k: _StatusAnswer(500, {"error": keys.UPSTREAM_ERROR})
    )

    result = keys.activate("00000-00000-00000-00000-00000", path=cache)

    assert not result.ok
    assert result.code == keys.UNREACHABLE
    assert result.message == keys.ACTIVATION_MESSAGES[keys.UNREACHABLE]


class _StatusAnswer:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _StatusAnswer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None
