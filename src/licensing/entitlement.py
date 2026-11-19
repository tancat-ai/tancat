"""The licence this deployment runs under, and when its window closes (j-0309).

One source: **a signed licence file we issued** (``signed_file.py``), or nothing,
in which case the deployment is Free. There is no store key, no activation call and
no provider anywhere in this path - the product cannot be locked out of a licence
by a payment provider's decisions.

**No function here makes a network call.** The signed file is verified locally
against the public key compiled into the build; the only files touched are the
licence file and the settings directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.licensing.signed_file import SignedLicence, verify_signed_file
from src.licensing.window import RELEASE_DATE, RENEWAL_COPY, WindowDecision

__all__ = [
    "LicenceState",
    "default_last_run_path",
    "default_signed_path",
    "last_running_version",
    "record_running_version",
    "load_signed_licence",
    "resolve",
    "startup_check",
    "upgrade_check",
]

#: Where a signed licence file is looked for, after ``AITEST_LICENCE_FILE``.
SIGNED_FILENAME = "licence.signed.json"

#: The version that last started inside its window. Written on a good start and read
#: by a refusal, so the message can name a version that actually works (t-1470).
LAST_RUN_FILENAME = "last_run.json"


def default_signed_path() -> Path:
    """The settings-dir path for a signed licence file."""
    from src.secure_config import _config_dir

    return Path(_config_dir()) / SIGNED_FILENAME


def default_last_run_path() -> Path:
    """The settings-dir record of the last version that started."""
    from src.secure_config import _config_dir

    return Path(_config_dir()) / LAST_RUN_FILENAME


def record_running_version(version: str, path: Path | None = None) -> None:
    """Remember *version* as the one that started (best effort, never raises)."""
    if not version:
        return
    target = path or default_last_run_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"version": version}), encoding="utf-8")
    except OSError:  # a read-only install still runs; the record is a courtesy
        pass


def last_running_version(path: Path | None = None) -> str:
    """The last version this machine started, or "" when none is recorded."""
    target = path or default_last_run_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return ""
    return str(data.get("version") or "") if isinstance(data, dict) else ""


def _date(value: object) -> date | None:
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


def load_signed_licence(path: Path | None = None) -> tuple[SignedLicence | None, Path | None, str]:
    """Read and verify the signed licence file, if there is one.

    Returns ``(licence, path, problem)``: ``licence`` is None when no file exists
    or when it does not verify, and ``problem`` says which, so the caller can show
    it without guessing.
    """
    env_path = os.environ.get("AITEST_LICENCE_FILE", "").strip()
    target = Path(env_path) if env_path else (path or default_signed_path())
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None, ""
    except OSError as exc:
        return None, target, f"The licence file at {target} could not be read: {exc}"

    result = verify_signed_file(text)
    if not result.valid:
        return None, target, result.reason
    return result.licence, target, ""


@dataclass(frozen=True)
class LicenceState:
    """The licence this deployment holds, and whether a build may run under it."""

    source: str  # "signed" | "none"
    tier: str
    window_end: date | None
    licence: SignedLicence | None = None
    problem: str = ""
    path: Path | None = None

    def allows_build(self, build_date: date) -> bool:
        """True when a build released on *build_date* is inside the update window."""
        return self.window_end is None or build_date <= self.window_end


def resolve() -> LicenceState:
    """The licence in force: the signed file, or Free."""
    signed, path, problem = load_signed_licence()
    if signed is not None:
        return LicenceState("signed", signed.tier, signed.window_end, licence=signed, path=path)
    # path is set when a file was found but refused, so the caller can say which
    # file and why instead of "not present" (t-1466).
    return LicenceState("none", "free", None, problem=problem, path=path)


def _refusal(state: LicenceState, build_date: date, installed_version: str) -> str:
    end = state.window_end.isoformat() if state.window_end else "the end of the update window"
    held_text = (
        f"Version {installed_version} keeps working" if installed_version else "The version you held keeps working"
    )
    return (
        f"This build was released after your update window ended on {end}. {held_text} - "
        f"nothing on disk has changed. To use this build, {RENEWAL_COPY}"
    )


def startup_check(*, build_date: date | None = None, installed_version: str = "") -> WindowDecision:
    """May this build start? The backstop for a wheel installed by hand.

    A Free install (no licence file) is never refused, and the window is only
    consulted for a licence that carries one.
    """
    build = build_date or RELEASE_DATE
    state = resolve()
    if not installed_version:
        # The refusal must name a version that works, as the upgrade path does.
        installed_version = last_running_version()
    if state.source == "none" or state.allows_build(build):
        message = "No licence file: running as Free Community." if state.source == "none" else ""
        return WindowDecision(True, message, state.window_end)
    return WindowDecision(False, _refusal(state, build, installed_version), state.window_end)


def upgrade_check(*, build_date: date | None = None, installed_version: str = "") -> WindowDecision:
    """The gate an upgrade must pass before it replaces the installed version."""
    return startup_check(build_date=build_date, installed_version=installed_version)
