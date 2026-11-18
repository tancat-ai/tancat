"""The update check: one question a day, and it carries nothing about you.

The owner approved this on 2026-11-14, with conditions. Read them as the spec:

- **The product still works fully offline.** TanCat makes two kinds of call and no
  others: one when you activate a licence key (see ``src/licensing/activation.py``)
  and a **version check at most once a day**, if you leave it on. Neither carries
  test data, file names, usage or anything else about the customer - the version
  check sends the request itself and nothing more, and the activation sends the
  key you pasted and a name for the deployment.
- **On by default, with an off switch.** The setting is ``update_check`` in the
  same store as the other preferences; its default is **on** (``True``). When it
  is off there is no call and no notice, ever.
- **Silent on every failure** - offline, DNS failure, 500, a parse error: no
  message, no delay, no retry. The call has a 2-second timeout.
- **A notice only when a newer version is known**, once per version per day, and
  never when the version is unknown.

The check runs in a background thread when the cache is stale, so a run never
waits on the network: a run inside 24 hours makes no call, a stale run starts one
and shows the notice on the next run. ``tancat update --check`` is the manual,
synchronous path.

The feed is ``FEED_URL``: PyPI's JSON for this distribution. The package is not
published yet (the URL answers 404 today), so in practice the check is inert -
every failure is silent by design, and the constant is the single line that
changes when it is published.

**A feed we do not own is an attack surface, not a version.** ``tancat`` is a name
anyone can register on PyPI while it is free. If someone else published it first,
our own check would read THEIR version number and tell every customer to run
``tancat update`` - which would install their package. So an answer is trusted
only when the project's identity is ours: ``info.name`` must be exactly
``tancat``, and at least one project URL or author field must point at
``tancat.dev`` or ``github.com/tancat-ai/tancat``. Anything else is treated as no
answer - silent, like every other failure.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

#: The setting that turns the check on or off. Same store as the other preferences.
UPDATE_CHECK_SETTING = "update_check"
DEFAULT_UPDATE_CHECK = True

#: Where the answer comes from. PyPI's JSON for this distribution; the constant
#: is the one line to change if the feed moves.
FEED_URL = "https://pypi.org/pypi/tancat/json"

#: The project's own identity. An answer from a project that is not this one is
#: refused: while the name is unregistered, anyone could publish under it and our
#: notice would point customers at their package.
FEED_PROJECT_NAME = "tancat"
SITE_HOST = "tancat.dev"
GITHUB_HOST = "github.com"
REPO_PATH = "/tancat-ai/tancat"

#: The call must never hold anything up.
TIMEOUT_S = 2.0

#: At most one call per this window.
CACHE_HOURS = 24

#: The cache lives beside licence.json, in the settings directory.
CACHE_NAME = "update_check.json"

#: Printed once per new version per day. The command is the honest way to upgrade.
NOTICE = "TanCat {latest} is available; you have {current}. Run: tancat update"


@dataclass(frozen=True)
class CheckResult:
    """What a check found, and where the answer came from."""

    current: str
    latest: str | None
    newer: bool
    source: str  # "off" | "cache" | "network" | "error"


def cache_path() -> Path:
    """The cache file, in the settings directory beside ``licence.json``."""
    from src.secure_config import _config_dir

    return Path(_config_dir()) / CACHE_NAME


def _parse_version(text: str) -> tuple[int, ...]:
    """'1.5.0' -> (1, 5, 0); a suffix after the numbers is ignored."""
    parts: list[int] = []
    for chunk in str(text).strip().split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def current_version() -> str:
    """The installed version, or the source-tree fallback."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("tancat")
    except PackageNotFoundError:
        return "0.1.0"


def is_newer(latest: str, current: str) -> bool:
    """True when *latest* is a strictly newer version than *current*."""
    return _parse_version(latest) > _parse_version(current)


def enabled() -> bool:
    """Whether the owner (or the customer) has left the check on."""
    from src.settings_store import load_setting

    value = load_setting(UPDATE_CHECK_SETTING, DEFAULT_UPDATE_CHECK)
    return value if isinstance(value, bool) else DEFAULT_UPDATE_CHECK


def read_cache(path: Path | None = None) -> dict[str, Any]:
    """The last answer, or an empty dict when there is none."""
    target = path or cache_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def write_cache(data: dict[str, Any], path: Path | None = None) -> None:
    """Record an answer. A cache that cannot be written is not an error."""
    target = path or cache_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _published_urls(info: dict[str, Any]) -> list[str]:
    """The project's OWN urls: ``home_page`` and ``project_urls`` VALUES.

    Values only, and parsed as URLs - a key name is not a URL, and a path or a
    query string that merely contains our domain proves nothing.
    """
    urls: list[str] = []
    home = info.get("home_page")
    if isinstance(home, str) and home.strip():
        urls.append(home.strip())
    project_urls = info.get("project_urls")
    if isinstance(project_urls, dict):
        for value in project_urls.values():
            if isinstance(value, str) and value.strip():
                urls.append(value.strip())
    return urls


def _is_our_hostname(url: str) -> bool:
    """True only for a real tancat.dev host (or subdomain) or our GitHub repo path.

    The hostname is parsed, never substring-matched: ``tancat.dev.evil.com`` and
    ``evil.com/tancat.dev`` both contain our domain as text and both are refused.
    """
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url if "//" in url else f"https://{url}")
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if host == SITE_HOST or host.endswith(f".{SITE_HOST}"):
        return True
    path = parts.path.lower().rstrip("/")
    return host == GITHUB_HOST and (path == REPO_PATH or path.startswith(REPO_PATH + "/"))


def identity_matches(payload: dict[str, Any]) -> bool:
    """True only when the feed describes THIS project.

    ``info.name`` must match exactly, and at least one published URL must have
    OUR hostname: ``tancat.dev`` (or a subdomain of it), or
    ``github.com/tancat-ai/tancat``. A feed we do not own is refused - see the
    module docstring: it is an attack surface, not a version. Spoofing a domain as
    text (``tancat.dev.evil.com``, ``evil.com/tancat.dev``) is refused too, because
    the hostname is parsed rather than searched for.
    """
    info = payload.get("info")
    if not isinstance(info, dict):
        return False
    name = info.get("name")
    if not isinstance(name, str) or name.strip().lower() != FEED_PROJECT_NAME:
        return False
    return any(_is_our_hostname(url) for url in _published_urls(info))


def _fetch(url: str, timeout: float = TIMEOUT_S) -> str | None:
    """Ask the feed for the latest version. Any failure, or a feed that is not
    ours, is ``None`` - silently."""
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError, OSError, ValueError, TimeoutError:
        return None
    if not isinstance(payload, dict) or not identity_matches(payload):
        return None
    info = payload.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    return str(version).strip() if version else None


def _fresh(cache: dict[str, Any], now: datetime) -> bool:
    stamp = cache.get("last_checked_at")
    if not isinstance(stamp, str) or not stamp:
        return False
    try:
        checked = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return now - checked < timedelta(hours=CACHE_HOURS)


def check(
    *,
    force: bool = False,
    now: datetime | None = None,
    fetcher: Any = None,
    path: Path | None = None,
) -> CheckResult:
    """Run the check for real, honouring the setting and the daily cache.

    ``force`` is the manual ``--check`` path: it bypasses the cache but still
    respects the off switch (off means never).
    """
    moment = now or datetime.now(UTC)
    current = current_version()
    if not enabled():
        return CheckResult(current, None, False, "off")

    cache = read_cache(path)
    if not force and _fresh(cache, moment):
        latest = cache.get("latest_version")
        latest_text = str(latest) if latest else None
        return CheckResult(current, latest_text, bool(latest_text and is_newer(latest_text, current)), "cache")

    fetch = fetcher or _fetch
    latest = fetch(FEED_URL)
    cache["last_checked_at"] = moment.isoformat()
    if latest:
        cache["latest_version"] = latest
    write_cache(cache, path)
    if not latest:
        return CheckResult(current, None, False, "error")
    return CheckResult(current, latest, is_newer(latest, current), "network")


def _notice_fresh(cache: dict[str, Any], latest: str, now: datetime) -> bool:
    if str(cache.get("notified_version") or "") != latest:
        return False
    stamp = cache.get("notified_at")
    if not isinstance(stamp, str) or not stamp:
        return True
    try:
        told = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    return now - told < timedelta(hours=CACHE_HOURS)


def notice_text(latest: str | None, current: str | None = None) -> str:
    """The one line a person sees, or an empty string."""
    if not latest:
        return ""
    return NOTICE.format(latest=latest, current=current or current_version())


def notice(*, now: datetime | None = None, path: Path | None = None, mark: bool = True) -> str:
    """The notice for this run, from the cache only - never a network call.

    Returns the one line, or an empty string. Records that this version was shown
    so the same line is not repeated more than once a day.
    """
    moment = now or datetime.now(UTC)
    if not enabled():
        return ""
    cache = read_cache(path)
    latest = cache.get("latest_version")
    if not latest:
        return ""
    latest_text = str(latest)
    current = current_version()
    if not is_newer(latest_text, current):
        return ""
    if _notice_fresh(cache, latest_text, moment):
        return ""
    if mark:
        cache["notified_version"] = latest_text
        cache["notified_at"] = moment.isoformat()
        write_cache(cache, path)
    return notice_text(latest_text, current)


def refresh_in_background(path: Path | None = None) -> None:
    """Start the daily check off the main thread, so no command ever waits."""
    if not enabled():
        return
    cache = read_cache(path)
    if _fresh(cache, datetime.now(UTC)):
        return

    thread = threading.Thread(target=lambda: check(path=path), name="tanCat-update-check", daemon=True)
    thread.start()


def upgrade_command() -> str:
    """The command a person runs to upgrade - printed, never shelled out."""
    return "pip install --upgrade tancat   (or: uv tool upgrade tancat)"


__all__ = [
    "CACHE_HOURS",
    "CACHE_NAME",
    "CheckResult",
    "DEFAULT_UPDATE_CHECK",
    "FEED_PROJECT_NAME",
    "FEED_URL",
    "GITHUB_HOST",
    "REPO_PATH",
    "SITE_HOST",
    "identity_matches",
    "NOTICE",
    "TIMEOUT_S",
    "UPDATE_CHECK_SETTING",
    "cache_path",
    "check",
    "current_version",
    "enabled",
    "is_newer",
    "notice",
    "notice_text",
    "read_cache",
    "refresh_in_background",
    "upgrade_command",
    "write_cache",
]
