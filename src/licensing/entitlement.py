"""The licence this deployment runs under, and when its update window closes.

One source, and it is a **cache on this machine**: the key the buyer activated, the
instance the store knows us by, and the date the key was created (the purchase date,
in practice). Everything else reads that cache.

Three moments, no others (owner, 2026-11-26):

- **activation** - once, at the prompt, through our relay (``activation.py``);
- **update** - once per upgrade, through the same relay;
- **between them** - nothing. Startup, runs and premium features read the cache, so
  the product works offline and a store outage cannot stop a paid deployment.

Accepted trade: with no periodic check, a key the store disables today is noticed at
the next update, not before. That sentence is in the buyer documents, not only here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.licensing import activation as store
from src.licensing.activation import Activation
from src.licensing.window import RELEASE_DATE, RENEWAL_COPY, WindowDecision

__all__ = [
    "LicenceState",
    "default_last_run_path",
    "default_licence_path",
    "last_running_version",
    "load_licence",
    "record_running_version",
    "resolve",
    "startup_check",
    "upgrade_check",
]

#: The version that last started inside its window. Written on a good start and read
#: by a refusal, so the message can name a version that actually works (t-1470).
LAST_RUN_FILENAME = "last_run.json"


def default_licence_path() -> Path:
    """The settings-dir path of the stored licence."""
    return store.default_path()


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


def load_licence(path: Path | None = None) -> tuple[Activation | None, Path | None, str]:
    """Read the stored licence. Never touches the network."""
    return store.load(path)


@dataclass(frozen=True)
class LicenceState:
    """The licence this machine holds, and whether a build may run under it."""

    source: str  # "activated" | "none"
    tier: str
    window_end: date | None
    activation: Activation | None = None
    problem: str = ""
    path: Path | None = None

    @property
    def activated_on(self) -> date | None:
        """The date the key was created: the purchase date, in practice."""
        return self.activation.activated_on if self.activation is not None else None

    def allows_build(self, build_date: date) -> bool:
        """True when a build released on *build_date* is inside the update window."""
        return self.window_end is None or build_date <= self.window_end


def resolve() -> LicenceState:
    """The licence in force: the activated key on this machine, or Free."""
    activation, path, problem = load_licence()
    if activation is not None:
        return LicenceState(
            "activated",
            activation.tier,
            activation.window_end,
            activation=activation,
            path=path,
        )
    # path is set when a file was found but unusable, so the caller can say which
    # file and why instead of "not present".
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
    """May this build start? Reads the cache only - startup never calls out.

    A Free install is never refused, and the window is only consulted for a licence
    that carries one.
    """
    build = build_date or RELEASE_DATE
    state = resolve()
    if not installed_version:
        installed_version = last_running_version()
    if state.source == "none" or state.allows_build(build):
        message = "No licence: running as Free Community." if state.source == "none" else ""
        return WindowDecision(True, message, state.window_end)
    return WindowDecision(False, _refusal(state, build, installed_version), state.window_end)


def upgrade_check(*, build_date: date | None = None, installed_version: str = "") -> WindowDecision:
    """The gate an upgrade must pass: the store's answer, then the window.

    This is the **only** moment a disabled, revoked or expired key surfaces, and the
    only moment the relay is called after activation. If the relay cannot be reached
    the upgrade proceeds on the cached licence and says the check could not be made -
    our network never blocks a buyer.
    """
    build = build_date or RELEASE_DATE
    state = resolve()
    if not installed_version:
        installed_version = last_running_version()

    if state.source == "none":
        return WindowDecision(True, "No licence: running as Free Community.", None)

    checked = store.validate()
    if checked.refused:
        held = (
            f"Version {installed_version} keeps working" if installed_version else "The version you held keeps working"
        )
        return WindowDecision(
            False,
            f"{checked.message} The upgrade was not installed. {held} - nothing on disk has changed.",
            state.window_end,
        )

    if not state.allows_build(build):
        refusal = _refusal(state, build, installed_version)
        if checked.kind == "network":
            return WindowDecision(False, f"{checked.message} {refusal}", state.window_end)
        return WindowDecision(False, refusal, state.window_end)

    if checked.kind == "network":
        return WindowDecision(
            True,
            f"{checked.message} Proceeding on the licence stored on this machine.",
            state.window_end,
        )
    return WindowDecision(True, "", state.window_end)
