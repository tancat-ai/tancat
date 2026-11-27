"""Licence keys: activated once at sale, checked once per update, offline between.

**The design the owner settled (2026-11-26).** A licence is a key the store issues
with the order. It is:

- **activated once**, when the buyer enters it - one call to our licence relay, which
  holds the merchant API key the product must never ship;
- **checked once per update** - the only moment a disabled, revoked or expired key
  surfaces;
- **offline in between** - startup, runs and premium features read the cache this
  module writes, and nothing else is called.

Accepted trade, stated in the docs: with no periodic check, a key the store disables
today goes unnoticed until the next update.

**The relay, never the provider.** Every request goes to our own relay
(``AITEST_LICENCE_RELAY_URL``). The product never holds a merchant API key and never
addresses the store directly, so a provider change touches the relay, not a release.

**Never ask a buyer to pay again.** Every refusal this module can produce says what
happened and what still works; none of them asks for money.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.licensing.window import WINDOW_MONTHS, add_months

__all__ = [
    "CACHE_FILENAME",
    "DEFAULT_RELAY_URL",
    "RELAY_URL_ENV",
    "Activation",
    "ActivationResult",
    "ValidationResult",
    "activate",
    "clear",
    "user_agent",
    "default_instance_name",
    "default_path",
    "deactivate",
    "load",
    "relay_url",
    "save",
    "validate",
]

#: Where the relay lives. One constant; ``AITEST_LICENCE_RELAY_URL`` overrides it for
#: a staging relay or a local test, and nothing else in the product builds a URL.
DEFAULT_RELAY_URL = "https://licence.tancat.dev"

#: The environment variable that points at the licence relay.
RELAY_URL_ENV = "AITEST_LICENCE_RELAY_URL"

#: The environment variable that points at the stored licence.
CACHE_ENV = "AITEST_LICENCE_FILE"

#: The stored licence's file name, inside the settings directory.
CACHE_FILENAME = "licence.json"

#: Seconds to wait for the relay. Activation is a buyer waiting at a prompt; update
#: is a person running a command. Short enough that a dead relay never hangs either.
TIMEOUT_SECONDS = 10.0

#: The relay's error codes, and the copy each one becomes. This is the whole mapping:
#: the relay translates the store's statuses into these, so no provider status appears
#: in the product and no provider name appears in a sentence.
ACTIVATION_LIMIT = "activation_limit"
NOT_RECOGNISED = "not_recognised"
ALREADY_RELEASED = "already_released"
REVOKED_OR_EXPIRED = "revoked_or_expired"
NOT_FOUND = "not_found"
UNREACHABLE = "unreachable"
#: A 403 that did not come from our relay: the edge refused the request before it
#: reached the Worker (Cloudflare answers "error code: 1010" to a default urllib
#: user agent). Our fault, not the buyer's (t-1506).
BLOCKED_AT_EDGE = "blocked_at_edge"
#: The relay's word for "the store failed and I could not name why". It is not a charge
#: refusal and not a dead key, so the product reads it as "no usable answer" (t-1508).
UPSTREAM_ERROR = "upstream_error"
#: The store answered 200 and named the key's state. Only "active" is a pass; the
#: others are refusals a buyer can read, and an unreadable answer is its own kind of
#: refusal rather than a silent pass (t-1505).
INACTIVE = "inactive"
DISABLED = "disabled"
EXPIRED = "expired"
UNKNOWN_STATUS = "unknown_status"

#: Activation refusals. The last one is the network case, and it keeps the buyer on
#: the free tier rather than blocking them.
ACTIVATION_MESSAGES: dict[str, str] = {
    ACTIVATION_LIMIT: (
        "This key has been used on its maximum number of machines. "
        "Release it on the other machine first, or email hello@tancat.dev."
    ),
    NOT_RECOGNISED: "This key is not recognised. Check it against the one in your order email - nothing on this machine has changed.",
    ALREADY_RELEASED: ("This machine was already released from this key. Enter the key again to activate it here."),
    UNREACHABLE: (
        "Could not reach the licence service - the product runs on the free tier until you connect and retry."
    ),
    BLOCKED_AT_EDGE: (
        "The licence service blocked this request before it reached us (edge error 1010). That is a fault at "
        "our end, not with your key - nothing on this machine has changed. Email hello@tancat.dev with this "
        "message and we will fix it; the product runs on the free tier meanwhile."
    ),
}

#: Validation refusals, for the upgrade gate only.
VALIDATION_MESSAGES: dict[str, str] = {
    REVOKED_OR_EXPIRED: "This licence key is no longer active: the store reports it as revoked or expired.",
    INACTIVE: "This licence key is inactive: the store reports it as disabled.",
    DISABLED: "This licence key has been disabled by the store.",
    EXPIRED: "This licence key has expired.",
    NOT_FOUND: "This licence key is no longer recognised by the store.",
    UNKNOWN_STATUS: ("The licence service gave an answer this version does not understand - check for an update."),
    UNREACHABLE: "Could not reach the licence service, so the update check could not be made.",
    BLOCKED_AT_EDGE: (
        "The licence service blocked this request before it reached us (edge error 1010), so the update "
        "check could not be made."
    ),
}

#: A 200 answer's ``status`` word to the refusal it means. Only ``active`` passes,
#: and every other word - including one this build has never seen - is refused.
VALIDATION_STATE_CODES: dict[str, str] = {
    "inactive": INACTIVE,
    "disabled": DISABLED,
    "expired": EXPIRED,
}


@dataclass(frozen=True)
class Activation:
    """What the relay told us at activation, plus when we last asked.

    The cache is the truth between updates: every field here is read from disk by
    :func:`load`, and nothing re-derives it from the network.
    """

    key: str
    instance_id: str
    instance_name: str
    status: str
    created_at: str
    expires_at: str = ""
    activation_limit: int | None = None
    last_checked: str = ""
    tier: str = "pro"

    @property
    def activated_on(self) -> date | None:
        """The calendar date the key was created - the purchase date, in practice."""
        return _as_date(self.created_at)

    @property
    def window_end(self) -> date | None:
        """The last release date this licence's updates cover, or None if unknown."""
        start = self.activated_on
        return add_months(start, WINDOW_MONTHS) if start else None

    @property
    def masked_key(self) -> str:
        """The key with the middle hidden, for a screen someone may photograph."""
        parts = self.key.split("-")
        if len(parts) < 2:
            return "****"
        return f"{parts[0]}-...-{parts[-1]}"

    def as_cache(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActivationResult:
    """The outcome of entering a key."""

    ok: bool
    activation: Activation | None = None
    code: str = ""
    message: str = ""

    @property
    def reachable(self) -> bool:
        """False when the relay could not be reached - the one retryable failure."""
        return self.code != UNREACHABLE


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of the update-time check."""

    kind: str  # "ok" | "refused" | "network" | "none"
    code: str = ""
    message: str = ""
    activation: Activation | None = None

    @property
    def refused(self) -> bool:
        return self.kind == "refused"

    @property
    def reached(self) -> bool:
        return self.kind != "network"


def _as_date(value: object) -> date | None:
    """Parse an ISO date or timestamp, or ``None``."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def default_path() -> Path:
    """Where the stored licence lives: ``AITEST_LICENCE_FILE``, or the settings dir."""
    env_path = os.environ.get(CACHE_ENV, "").strip()
    if env_path:
        return Path(env_path)
    from src.secure_config import _config_dir

    return Path(_config_dir()) / CACHE_FILENAME


def relay_url() -> str:
    """The relay's base address - ours, configurable, never the provider's."""
    return os.environ.get(RELAY_URL_ENV, "").strip() or DEFAULT_RELAY_URL


def user_agent() -> str:
    """The user agent every relay call sends: a versioned product string.

    Cloudflare's edge rejects Python's default ``Python-urllib/3.x`` user agent with
    ``403 error code: 1010`` before the request ever reaches the Worker, so a buyer
    would be told the service could not be reached and no activation would ever work
    (t-1506). Built from ``version_info`` so it cannot drift from the release.
    """
    from src.version_info import installed_version

    version = installed_version() or "unknown"
    return f"TanCat/{version} (+https://tancat.dev)"


def default_instance_name() -> str:
    """A name the buyer can recognise in the store's list of activated machines."""
    try:
        host = socket.gethostname().strip()
    except OSError:  # pragma: no cover - a broken hostname must not stop activation
        host = ""
    return host or "this machine"


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------


def load(path: Path | None = None) -> tuple[Activation | None, Path | None, str]:
    """Read the stored licence. Never touches the network.

    Returns ``(activation, path, problem)``: ``problem`` says why a file that exists
    could not be used, so a caller can show the reason instead of "not present".
    """
    target = path or default_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None, ""
    except PermissionError:
        return (
            None,
            target,
            (
                f"The licence file at {target} could not be read - it exists, but this account has no "
                "permission for it. Delete it and activate the key again."
            ),
        )
    except OSError as exc:
        return None, target, f"The licence file at {target} could not be read: {exc}"

    try:
        data = json.loads(raw)
    except ValueError:
        return None, target, f"The stored licence at {target} is not valid JSON - activate the key again."
    if not isinstance(data, dict) or not data.get("key") or not data.get("instance_id"):
        return None, target, f"The stored licence at {target} is incomplete - activate the key again."

    activation = Activation(
        key=str(data.get("key", "")),
        instance_id=str(data.get("instance_id", "")),
        instance_name=str(data.get("instance_name", "")),
        status=str(data.get("status", "")),
        created_at=str(data.get("created_at", "")),
        expires_at=str(data.get("expires_at", "") or ""),
        activation_limit=data.get("activation_limit") if isinstance(data.get("activation_limit"), int) else None,
        last_checked=str(data.get("last_checked", "")),
        tier=str(data.get("tier") or "pro"),
    )
    return activation, target, ""


def save(activation: Activation, path: Path | None = None) -> Path:
    """Write the licence cache. Best effort: a read-only install keeps running."""
    target = path or default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(activation.as_cache(), indent=2) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:  # pragma: no cover - Windows may refuse; the file is the licence
        pass
    return target


def clear(path: Path | None = None) -> bool:
    """Remove the stored licence. True when a file was removed."""
    target = path or default_path()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# The relay calls
# ---------------------------------------------------------------------------


def _post(operation: str, payload: dict[str, Any], *, timeout: float = TIMEOUT_SECONDS) -> tuple[int, dict[str, Any]]:
    """POST one operation to the relay. Returns ``(status, body)``; 0 means no answer.

    The only outbound call in the licensing path, and it goes to our relay. The
    egress audit classifies this file as OUR-SERVICE by name, not by accident.
    """
    request = urllib.request.Request(
        # The relay address, in the statement itself: the egress audit classifies
        # this call OUR-SERVICE by name, and a call from this file to anywhere else
        # would be FLAGGED.
        f"{relay_url().rstrip('/')}/{operation}",
        data=json.dumps({"operation": operation, **payload}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": user_agent(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - our relay, https
            return int(response.status), _json_body(response.read())
    except urllib.error.HTTPError as exc:
        return int(exc.code), _json_body(exc.read())
    except urllib.error.URLError, TimeoutError, OSError:
        return 0, {}


def _json_body(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError, UnicodeDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _code_for(result: dict[str, Any], status: int, operation: str) -> str:
    """The relay's code, or the HTTP status translated the same way when absent."""
    code = str(result.get("error") or result.get("code") or "").strip()
    if code == UPSTREAM_ERROR:
        return UNREACHABLE
    if code in ACTIVATION_MESSAGES or code in VALIDATION_MESSAGES:
        return code
    if status == 0:
        return UNREACHABLE
    if status == 403:
        # Our relay always answers a 403 with one of its own codes. A 403 with no
        # code came from something in front of it - "error code: 1010" is the edge's
        # answer to a default user agent - and must not be read as the buyer's key
        # being on too many machines (t-1506).
        if not code:
            return BLOCKED_AT_EDGE
        return ACTIVATION_LIMIT if operation == "activate" else REVOKED_OR_EXPIRED
    if status == 404:
        return NOT_RECOGNISED if operation == "activate" else NOT_FOUND
    if status == 409:
        return ALREADY_RELEASED
    if status == 410:
        return REVOKED_OR_EXPIRED
    return UNREACHABLE


def _activation_from(result: dict[str, Any], *, key: str, instance_name: str) -> Activation | None:
    """Read the relay's activation object into our cache shape."""
    body = result.get("activation")
    if not isinstance(body, dict):
        return None
    raw_instance = body.get("instance")
    instance: dict[str, Any] = raw_instance if isinstance(raw_instance, dict) else {}
    return Activation(
        key=str(body.get("key") or key),
        instance_id=str(instance.get("id") or body.get("instance_id") or ""),
        instance_name=str(instance.get("name") or instance_name),
        status=str(body.get("status") or "active"),
        created_at=str(body.get("created_at") or _now_iso()),
        expires_at=str(body.get("expires_at") or ""),
        activation_limit=body.get("activation_limit") if isinstance(body.get("activation_limit"), int) else None,
        last_checked=_now_iso(),
        tier=str(body.get("tier") or "pro"),
    )


def activate(key: str, instance_name: str = "", *, path: Path | None = None) -> ActivationResult:
    """Activate *key* on this machine, once, through the relay.

    On success the licence is cached and used offline from then on. On failure the
    cache is left exactly as it was: a refused activation never takes away a licence
    this machine already holds.
    """
    cleaned = key.strip()
    if not cleaned:
        return ActivationResult(False, code=NOT_RECOGNISED, message=ACTIVATION_MESSAGES[NOT_RECOGNISED])

    name = instance_name.strip() or default_instance_name()
    status, body = _post("activate", {"key": cleaned, "instance_name": name})
    if status == 200:
        activation = _activation_from(body, key=cleaned, instance_name=name)
        if activation is not None and activation.instance_id:
            save(activation, path)
            return ActivationResult(True, activation=activation, message=_activated_sentence(activation))
        code = NOT_RECOGNISED
    else:
        code = _code_for(body, status, "activate")

    message = ACTIVATION_MESSAGES.get(code) or ACTIVATION_MESSAGES[UNREACHABLE]
    return ActivationResult(False, code=code, message=message)


def validate(*, path: Path | None = None) -> ValidationResult:
    """Ask the relay whether the stored key is still active. For the update gate only.

    A network failure is not a refusal: the caller proceeds on the cached licence and
    says the check could not be made.
    """
    activation, _target, problem = load(path)
    if activation is None:
        kind = "none"
        return ValidationResult(kind, code="", message=problem)

    status, body = _post("validate", {"key": activation.key, "instance_id": activation.instance_id})
    if status == 200:
        raw_state = body.get("status")
        state = str(raw_state).strip().lower() if raw_state is not None else ""
        # Only "active" is a pass (t-1505). A missing or unknown word is a refusal of
        # its own kind: an answer this build cannot read must never open the gate,
        # which is exactly how a disabled key used to slip through.
        if state == "active":
            refreshed = Activation(
                key=activation.key,
                instance_id=activation.instance_id,
                instance_name=activation.instance_name,
                status=state,
                created_at=activation.created_at,
                expires_at=str(body.get("expires_at") or activation.expires_at or ""),
                activation_limit=activation.activation_limit,
                last_checked=_now_iso(),
            )
            try:
                save(refreshed, path)
            except OSError:  # pragma: no cover - a read-only install still updates
                pass
            return ValidationResult("ok", "ok", "", refreshed)
        code = VALIDATION_STATE_CODES.get(state, UNKNOWN_STATUS)
    else:
        code = _code_for(body, status, "validate")

    if code in (UNREACHABLE, BLOCKED_AT_EDGE):
        return ValidationResult(
            "network",
            code=code,
            message=VALIDATION_MESSAGES[code],
            activation=activation,
        )
    return ValidationResult(
        "refused",
        code=code,
        message=VALIDATION_MESSAGES.get(code) or VALIDATION_MESSAGES[NOT_FOUND],
        activation=activation,
    )


def deactivate(*, path: Path | None = None) -> tuple[bool, str]:
    """Release this machine from the key, so it can be activated elsewhere.

    The cache is removed whichever way the relay answers - a buyer moving machines
    must not be stuck with a licence they cannot release.
    """
    activation, _target, problem = load(path)
    if activation is None:
        return False, problem or "No licence is stored on this machine."
    status, body = _post("deactivate", {"key": activation.key, "instance_id": activation.instance_id})
    if status == 200:
        clear(path)
        return True, "This machine has been released from the key. The product runs on the free tier here now."
    code = _code_for(body, status, "deactivate")
    if code == UNREACHABLE:
        return False, VALIDATION_MESSAGES[UNREACHABLE] + " Nothing on this machine has changed."
    clear(path)
    return True, "This machine has been released from the key."


def _activated_sentence(activation: Activation) -> str:
    end = activation.window_end.isoformat() if activation.window_end else "the end of the update window"
    return (
        f"Licence key activated on this machine. Updates released up to {end} are included; nothing was charged again."
    )
