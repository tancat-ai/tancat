"""The one place the product asks "what version am I?".

Two callers need it - ``tancat --version`` and the update check - and both used to
answer ``0.1.0`` from a source checkout, because they only consulted installed
package metadata. A source run therefore printed 0.1.0 and then reported
"1.0.0 is available" against its own tree (j-0313 review).

The order is:

1. **installed metadata** - the version the wheel was built with;
2. **pyproject.toml** next to the source tree - a checkout has no metadata, and
   this is the same number the build will carry;
3. ``"unknown"`` - said out loud rather than guessed. A version that cannot be
   parsed is never compared for "newer", so an unknown current never produces a
   false update notice.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["installed_version", "pyproject_version", "version_is_known"]


def pyproject_version(root: Path | None = None) -> str | None:
    """``[project].version`` from the source tree, or ``None`` when there is no tree."""
    import tomllib

    candidate = (root or Path(__file__).resolve().parents[1]) / "pyproject.toml"
    try:
        with candidate.open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except OSError, KeyError, ValueError:
        return None


def installed_version() -> str:
    """The running version: installed metadata, else the source tree, else 'unknown'."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("tancat")
    except PackageNotFoundError:
        return pyproject_version() or "unknown"


def version_is_known(text: str) -> bool:
    """True when *text* looks like a version (has at least one leading number)."""
    return bool(text) and text.split(".", 1)[0].strip().isdigit()
