"""Which licence this deployment runs under, and when the window closes (j-0309).

Two sources, one precedence rule:

1. **A signed licence file we issued** (``signed_file.py``) - verified offline,
   and the source of truth for the tier and the update window.
2. **The legacy store key** (``activation.py``) - kept working exactly as it does
   today, because buyers hold those keys and Lemon Squeezy's activation service is
   still answering. It is the fallback, not the future.

**A valid signed file wins when present.** If one is present but does not verify,
it is *reported* rather than swallowed, and the legacy key is still honoured: an
independent proof of purchase should not stop working because a file was corrupted
in an email client. Both cases are visible in ``source`` and ``problem``.

**The window** comes from the signed file's ``window_end``. The legacy path keeps
its own rule (purchase date + 12 months, recorded at activation) until the store
goes; nothing here re-derives one from the other.

**No call is made by any function in this module.** The signed-file path imports no
network module; the legacy path only reads the local file that activation wrote.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.licensing import activation
from src.licensing.merchant import MERCHANT_OF_RECORD
from src.licensing.signed_file import SignedLicence, verify_signed_file

__all__ = [
    "MIGRATION_PARAGRAPH",
    "LicenceState",
    "default_signed_path",
    "load_signed_licence",
    "resolve",
    "startup_check",
    "upgrade_check",
]

#: What a buyer who already holds a store key is told. One paragraph, printed by
#: ``tancat licence status`` and reproduced in the user docs.
MIGRATION_PARAGRAPH = (
    f"If you already hold a {MERCHANT_OF_RECORD} key, nothing changes: your key keeps working exactly "
    "as it does today, and activation still happens once. When you receive a signed licence file from "
    "us, save it where the product looks for it (the path `tancat licence status` prints) and it is "
    "used in preference to the key - verified offline, with no call to anyone. You can keep the key "
    "file as a backup; it is simply no longer the first source."
)

#: Where a signed licence file is looked for, after ``AITEST_LICENCE_FILE``.
SIGNED_FILENAME = "licence.signed.json"


def _date(value: object) -> date | None:
    """Parse an ISO date or timestamp written by the activation path."""
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


def default_signed_path() -> Path:
    """The settings-dir path for a signed licence file."""
    from src.secure_config import _config_dir

    return Path(_config_dir()) / SIGNED_FILENAME


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

    source: str  # "signed" | "legacy" | "none"
    tier: str
    window_end: date | None
    licence: SignedLicence | None = None
    problem: str = ""
    path: Path | None = None

    def allows_build(self, build_date: date) -> bool:
        """True when a build released on *build_date* is inside the update window."""
        return self.window_end is None or build_date <= self.window_end


def resolve(build_date: date | None = None) -> LicenceState:
    """The licence in force: signed file first, legacy key second, Free otherwise."""
    signed, path, problem = load_signed_licence()
    if signed is not None:
        return LicenceState("signed", signed.tier, signed.window_end, licence=signed, path=path)

    legacy = activation.read_licence()
    if legacy:
        decision = activation.entitlement(legacy, build_date=build_date)
        purchased = _date(legacy.get("key_created_at"))
        end = decision.window_end or (activation.window_end(purchased) if purchased else None)
        tier = str(legacy.get("tier") or "pro")
        return LicenceState("legacy", tier, end, problem=problem, path=activation.default_licence_path())

    return LicenceState("none", "free", None, problem=problem)


def _refusal(state: LicenceState, build_date: date, installed_version: str) -> str:
    end = state.window_end.isoformat() if state.window_end else "the end of the update window"
    held_text = (
        f"Version {installed_version} keeps working" if installed_version else "The version you held keeps working"
    )
    return (
        f"This build was released after your update window ended on {end}. {held_text} - "
        f"nothing on disk has changed. To use this build, {activation.RENEWAL_COPY}"
    )


def startup_check(*, build_date: date | None = None, installed_version: str = "") -> activation.WindowDecision:
    """May this build start? The backstop for a wheel installed by hand.

    A Free install (no licence at all) is never refused, and the window is only
    ever consulted for a licence that carries one.
    """
    build = build_date or activation.RELEASE_DATE
    state = resolve(build_date=build)
    if not installed_version:
        # The activation path records the version the buyer is running; use it so
        # the refusal names something they can go back to.
        stored = activation.read_licence() or {}
        installed_version = str(stored.get("installed_version") or "")
    if state.source == "none" or state.allows_build(build):
        message = "No licence file: running as Free Community." if state.source == "none" else ""
        return activation.WindowDecision(True, message, state.window_end)
    return activation.WindowDecision(False, _refusal(state, build, installed_version), state.window_end)


def upgrade_check(*, build_date: date | None = None, installed_version: str = "") -> activation.WindowDecision:
    """The gate an upgrade must pass before it replaces the installed version."""
    return startup_check(build_date=build_date, installed_version=installed_version)
