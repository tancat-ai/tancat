"""Store-key activation (the legacy path), the licence file, and the 12-month window.

The owner approved this design on 2026-11-13 (option A). One product, one key:

- The store key IS the licence on this path. The store keeps no expiry on it - the
  licence is perpetual for the version received - so ``expires_at`` is null and
  is never used to drive anything.
- On first run the product activates the key **once** against
  ``POST /v1/licenses/activate`` (form-encoded), and saves the result. After that
  it makes no further call, ever. There is no periodic check, no phone-home.
- The response must belong to THIS store and product: the ids below are
  hard-coded and a key from anywhere else is refused. The store's own guide
  says that without this check a key from another product unlocks ours.
- The update window is **purchase date + 12 months**, where the purchase date is
  the key's ``created_at`` from the activation response. The package carries its
  own release date. A build released inside the window runs forever with no
  further check; a build released after it is refused at upgrade time (nothing
  on disk changes) and, if someone installs the wheel by hand, refused at startup
  with the exact command to return to the last entitled version.

**This is a boundary for honest buyers, not DRM.** The licence file is plain JSON
on the buyer's own disk, and a determined user can edit ``key_created_at`` or
``release_date`` in it (or edit this module in a fork) and the window will move.
That is accepted: the value of the check is a clear, honest boundary and an
enforceable ToS, not a lock. Pretending otherwise would be the dishonest option.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.licensing.merchant import MERCHANT_OF_RECORD

ACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/activate"

#: The store ids this build accepts keys for. Empty means "not set in
#: this build", and activation then refuses rather than accepting anything: a
#: fail-closed default, so a build shipped before the ids are filled cannot be
#: unlocked by a key from someone else's store.
STORE_ID: str = "471488"
PRODUCT_ID: str = "1521271"
VARIANT_ID: str = "2367450"

#: The date this build was released. Refreshed with each release; it is the
#: package's own date, and the only clock the window uses for "the build".
RELEASE_DATE: date = date(2026, 11, 13)

#: How long a purchase includes updates for.
WINDOW_MONTHS: int = 12

#: Renewal is not sold yet; the copy says what it will be.
RENEWAL_COPY = "Renew at https://tancat.dev/#pricing when a renewal is available, or email hello@tancat.dev."


@dataclass(frozen=True)
class Activation:
    """The result of one activation attempt."""

    ok: bool
    message: str
    licence: dict[str, Any] | None = None


@dataclass(frozen=True)
class WindowDecision:
    """Whether this build may run, and what to say when it may not."""

    allowed: bool
    message: str
    window_end: date | None = None


def _post_form(url: str, fields: dict[str, str], timeout: float = 20.0) -> tuple[int, dict[str, Any], str]:
    """POST *fields* as a form; return (status, json body, error text).

    Isolated so tests never touch the network: they pass their own transport.
    """
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
            body = response.read().decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carries the JSON body
        body = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return 0, {}, str(exc)
    try:
        parsed = json.loads(body) if body.strip() else {}
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}, "" if parsed else body[:200]


Transport = Callable[[str, dict[str, str]], tuple[int, dict[str, Any], str]]


def default_licence_path() -> Path:
    """Where this deployment's licence file lives (the settings dir)."""
    from src.secure_config import _config_dir

    return Path(_config_dir()) / "licence.json"


def read_licence(path: Path | None = None) -> dict[str, Any] | None:
    """The stored licence, or ``None`` when this deployment has never activated."""
    target = path or default_licence_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) else None


def write_licence(data: dict[str, Any], path: Path | None = None) -> Path:
    """Store the licence as plain JSON. Deliberately readable - see the docstring."""
    target = path or default_licence_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def _parse_date(value: Any) -> date | None:
    """Parse an ISO timestamp or date from the store's response, or ``None``."""
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


def add_months(start: date, months: int) -> date:
    """*start* plus *months*, clamped to the end of the target month."""
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = start.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def window_end(purchase_date: date) -> date:
    """The last day a build released inside the update window may be."""
    return add_months(purchase_date, WINDOW_MONTHS)


def entitlement(licence: dict[str, Any] | None, build_date: date | None = None) -> WindowDecision:
    """Whether *build_date* is inside the licence's update window.

    No licence means Free: the open core still runs, and ``allowed`` is True for
    the free claims. The window only ever decides whether a **paid build** may
    run, so a missing or unreadable purchase date is reported, not guessed.
    """
    build = build_date or RELEASE_DATE
    if not licence:
        return WindowDecision(True, "No licence file: running as Free Community.", None)
    purchased = _parse_date(licence.get("key_created_at"))
    if purchased is None:
        return WindowDecision(
            True,
            "The licence file does not record a purchase date, so the update window cannot be "
            "checked. Running as licensed; re-activate the key to record it.",
            None,
        )
    end = window_end(purchased)
    if build <= end:
        return WindowDecision(
            True, f"Build {build.isoformat()} is inside the update window (to {end.isoformat()}).", end
        )
    return WindowDecision(False, "", end)


def startup_check(
    licence: dict[str, Any] | None = None,
    *,
    build_date: date | None = None,
    installed_version: str = "",
) -> WindowDecision:
    """The backstop: may this build start?

    A build released after the window refuses to start and names the window end,
    the installed version that keeps working, and how to renew. Nothing is
    modified - the buyer's existing install is untouched.
    """
    stored = licence if licence is not None else read_licence()
    decision = entitlement(stored, build_date=build_date)
    if decision.allowed:
        return decision
    end = decision.window_end.isoformat() if decision.window_end else "the end of the update window"
    held = installed_version or str((stored or {}).get("installed_version") or "")
    held_text = f"Version {held} keeps working" if held else "The version you held keeps working"
    message = (
        f"This build was released after your update window ended on {end}. {held_text} - "
        f"nothing on disk has changed. To use this build, {RENEWAL_COPY}"
    )
    return WindowDecision(False, message, decision.window_end)


def upgrade_check(
    licence: dict[str, Any] | None = None,
    *,
    build_date: date | None = None,
    installed_version: str = "",
) -> WindowDecision:
    """The gate an upgrade must pass before it replaces the installed version.

    Same rule as :func:`startup_check`, but it runs BEFORE anything is installed,
    so a refusal leaves the working install exactly as it was.
    """
    return startup_check(licence, build_date=build_date, installed_version=installed_version)


def _refusal(status: int, body: dict[str, Any], error_text: str) -> str:
    """The buyer-facing sentence for a failed activation (spec 1.4)."""
    key = body.get("license_key") or {}
    key = key if isinstance(key, dict) else {}
    status_text = str(key.get("status") or "").lower()
    if status == 404 or body.get("activated") is False and not key:
        return (
            f"That key was not recognised. Check it against the receipt email from {MERCHANT_OF_RECORD} - "
            "the key is long and easy to mistype. If it still fails, email hello@tancat.dev with the "
            "order number."
        )
    if status_text == "expired":
        return (
            "This key has expired. TanCat Pro keys do not normally expire - email hello@tancat.dev and "
            "we will sort it out."
        )
    if status_text == "disabled":
        return "This key has been disabled. Email hello@tancat.dev - this is usually a refund or a duplicate order."
    if status == 422:
        return "We could not read that key. Paste the whole key from the receipt, with no spaces."
    if status == 429:
        return "Too many activation attempts. Wait a minute and try again."
    usage = int(key.get("activation_usage") or 0)
    limit = int(key.get("activation_limit") or 0)
    if limit and usage >= limit:
        return (
            "This key has already been activated the maximum number of times. Deactivate the old "
            f"deployment in your {MERCHANT_OF_RECORD} account, or email hello@tancat.dev and we will reset it."
        )
    if status == 0 or status >= 500:
        detail = f" ({error_text})" if error_text else ""
        return (
            f"Activation needs one connection to {MERCHANT_OF_RECORD}. Your machine could not reach it just "
            f"now{detail}. Your existing licence (if any) still works offline; try again in a minute."
        )
    return (
        f"{MERCHANT_OF_RECORD} did not activate that key. Check it against the receipt email, or email "
        "hello@tancat.dev with the order number."
    )


def _ids_configured() -> bool:
    return bool(STORE_ID.strip() and PRODUCT_ID.strip())


def activate(
    key: str,
    instance_name: str = "TanCat deployment",
    *,
    transport: Transport | None = None,
    path: Path | None = None,
    now: datetime | None = None,
) -> Activation:
    """Activate *key* once, and store the licence.

    Failure never drops an existing licence: nothing is written unless the
    response is a valid activation for THIS store and product.
    """
    licence_key = (key or "").strip()
    if not licence_key:
        return Activation(False, "Paste the whole key from the receipt, with no spaces.")

    if not _ids_configured():
        missing = [name for name, value in (("store_id", STORE_ID), ("product_id", PRODUCT_ID)) if not value.strip()]
        return Activation(
            False,
            "This build cannot activate a key yet: it has no "
            + " or ".join(missing)
            + " compiled in, and accepting an unverified key would unlock TanCat with any store's "
            "licence. Set the ids in src/licensing/activation.py.",
        )

    post = transport or _post_form
    status, body, error_text = post(ACTIVATE_URL, {"license_key": licence_key, "instance_name": instance_name})

    # A refused or failed request is answered from its own status before the
    # response's meta is trusted: a 404/422/limit body carries nothing to verify.
    if status == 0 or status >= 400:
        return Activation(False, _refusal(status, body, error_text))

    meta = body.get("meta") or {}
    meta = meta if isinstance(meta, dict) else {}
    returned_store = str(meta.get("store_id") or "")
    returned_product = str(meta.get("product_id") or "")
    variant = str(meta.get("variant_id") or "")
    if returned_store != STORE_ID.strip():
        return Activation(
            False,
            f"That key belongs to a different store (the key's store is {returned_store or 'unknown'}). "
            "TanCat accepts only keys from its own store; email hello@tancat.dev if you bought TanCat "
            "and see this.",
        )
    if returned_product != PRODUCT_ID.strip():
        return Activation(
            False,
            f"That key belongs to a different product (the key's product is {returned_product or 'unknown'}). "
            "TanCat accepts only keys for its own product; email hello@tancat.dev if you bought TanCat "
            "and see this.",
        )
    if VARIANT_ID.strip() and not variant:
        # A response with no variant id cannot be shown to be ours; refuse it
        # rather than let an omitted field pass for a match.
        return Activation(
            False,
            "That key's response did not say which product variant it is for, so TanCat cannot "
            "confirm it belongs to this product. Email hello@tancat.dev with the order number.",
        )
    if VARIANT_ID.strip() and variant and variant != VARIANT_ID.strip():
        return Activation(
            False,
            f"That key is for a different product variant (the key's variant is {variant or 'unknown'}). "
            "Email hello@tancat.dev.",
        )

    if not body.get("activated"):
        return Activation(False, _refusal(status, body, error_text))

    key_obj = body.get("license_key") or {}
    key_obj = key_obj if isinstance(key_obj, dict) else {}
    instance = body.get("instance") or {}
    instance = instance if isinstance(instance, dict) else {}
    created = _parse_date(key_obj.get("created_at"))
    if created is None:
        return Activation(
            False,
            f"{MERCHANT_OF_RECORD} activated the key but did not return its purchase date, and the update "
            "window is measured from that date. Email hello@tancat.dev with the order number.",
        )

    stamp = (now or datetime.now(UTC)).isoformat()
    licence = {
        "key": str(key_obj.get("key") or licence_key),
        "instance_id": str(instance.get("id") or ""),
        "instance_name": instance_name,
        "key_created_at": created.isoformat(),
        "store_id": returned_store,
        "product_id": returned_product,
        "variant_id": variant,
        "activated_at": stamp,
        "last_seen_at": stamp,
        # The store keeps no expiry on our keys; the field is recorded so a
        # reader can see we looked, and is never used to drive the window.
        "expires_at": key_obj.get("expires_at"),
        "release_date": RELEASE_DATE.isoformat(),
    }
    write_licence(licence, path)
    end = window_end(created)
    return Activation(
        True,
        f"Activated. This licence includes all updates released up to {end.isoformat()}.",
        licence,
    )


def touch_last_seen(path: Path | None = None, *, now: datetime | None = None) -> None:
    """Record that the product ran - a local timestamp, no network call."""
    licence = read_licence(path)
    if not licence:
        return
    licence["last_seen_at"] = (now or datetime.now(UTC)).isoformat()
    write_licence(licence, path)


__all__ = [
    "ACTIVATE_URL",
    "Activation",
    "PRODUCT_ID",
    "RELEASE_DATE",
    "RENEWAL_COPY",
    "STORE_ID",
    "VARIANT_ID",
    "WINDOW_MONTHS",
    "WindowDecision",
    "activate",
    "add_months",
    "default_licence_path",
    "entitlement",
    "read_licence",
    "startup_check",
    "touch_last_seen",
    "upgrade_check",
    "window_end",
    "write_licence",
]
