"""Guard: the dependency licence record is current with ``uv.lock``.

``docs/licenses/DEPENDENCIES.md`` is generated from the lock (see
``scripts/maintenance/licence_record.py``). A lock bump, a dropped dependency,
a version change or a hand-edit of the tables that is not regenerated makes the
record wrong, which matters because it is the licence evidence a customer or
store review reads. These tests pin the committed record as current and pin the
guard that catches each kind of drift.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GUARD_SCRIPT = PROJECT_ROOT / "scripts" / "maintenance" / "licence_record.py"


def _load_guard() -> Any:
    spec = importlib.util.spec_from_file_location("licence_record", GUARD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record_text() -> str:
    return (PROJECT_ROOT / "docs" / "licenses" / "DEPENDENCIES.md").read_text(encoding="utf-8")


def test_committed_record_matches_uv_lock() -> None:
    """The record in the repo must describe the packages in uv.lock."""
    guard = _load_guard()
    assert guard.check() == []


def test_version_drift_is_detected() -> None:
    """A dependency bumped in the lock but not in the record fails the guard."""
    guard = _load_guard()
    text = _record_text()
    stale = text.replace("| playwright | 1.63.0 |", "| playwright | 1.62.0 |", 1)
    assert stale != text

    problems = guard.check(stale)

    assert any("playwright" in p and "1.62.0" in p for p in problems), problems


def test_dropped_dependency_left_in_the_record_is_detected() -> None:
    """A dependency removed from the lock but still listed fails the guard."""
    guard = _load_guard()
    text = _record_text()
    header = "| Package | Version | Licence | URL |\n|---|---|---|---|\n"
    stale = text.replace(
        header,
        header + "| openai | 3.13.0 | Apache-2.0 | https://github.com/openai/openai-python |\n",
        1,
    )
    assert stale != text

    problems = guard.check(stale)

    assert any("openai" in p for p in problems), problems


def test_missing_package_is_detected() -> None:
    """A lock package absent from the appendix fails the guard."""
    guard = _load_guard()
    text = _record_text()
    stale = text.replace("| altair | 6.2.2 | BSD License | https://github.com/vega/altair |\n", "", 1)
    assert stale != text

    problems = guard.check(stale)

    assert any("altair" in p for p in problems), problems


def test_wrong_appendix_count_is_detected() -> None:
    """A stale package count in the appendix title fails the guard."""
    guard = _load_guard()
    text = _record_text()
    match = re.search(r"## Appendix: full locked set \((\d+) entries\)", text)
    assert match is not None, "the appendix title is missing from the record"
    actual = match.group(1)
    wrong = str(int(actual) + 6)
    stale = text.replace(f"({actual} entries)", f"({wrong} entries)", 1)
    assert stale != text

    problems = guard.check(stale)

    assert any(wrong in p and actual in p for p in problems), problems
