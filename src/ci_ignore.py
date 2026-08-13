"""CI ignore-list parsing (``.ai-test-ignore.yml``) — Phase 7 CI/CD integration.

A versioned, human-recorded list of *known-benign* test failures. The CI
integration reports them as "N known-benign ignored" instead of real
failures — the safe mechanism for "button moved but still works" churn
(resolved in grilling 2026-08-13: no silent mutation, explicit human record,
reviewable in git).

Phase 7a scope: parse + validate only. Matching against actual failures
lands with the run phase (7b) — but the matcher is implemented here so it is
unit-testable in isolation.

File format::

    # .ai-test-ignore.yml
    ignores:
      - test: "test_08_checkout*"
        reason: "button moved to new class, verified still functional 2026-08-14"
        match: "Locator '.*' not found"   # optional regex on the failure message
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IgnoreRule:
    """One entry in the ignore list."""

    test: str  # test name glob (fnmatch-style, '*' wildcards)
    reason: str = ""  # why it is known-benign (the human record)
    match: str = ""  # optional regex on the failure message; empty = any failure
    pattern: re.Pattern[str] | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class IgnoreSpec:
    """Parsed ``.ai-test-ignore.yml``."""

    ignores: tuple[IgnoreRule, ...] = ()
    path: str = ""

    @property
    def count(self) -> int:
        return len(self.ignores)

    def matches(self, test_name: str, failure_message: str = "") -> bool:
        """Return True if *test_name* (optionally constrained by *failure_message*)
        matches any rule.

        A rule with an empty ``match`` covers any failure of a matching test;
        a rule with a ``match`` regex only covers failures whose message the
        regex matches.
        """
        for rule in self.ignores:
            if not fnmatch.fnmatch(test_name, rule.test):
                continue
            if rule.pattern is not None and not rule.pattern.search(failure_message or ""):
                continue
            return True
        return False

    def describe(self, test_name: str, failure_message: str = "") -> str | None:
        """Return the matching rule's reason (or the rule's test glob) — used
        in the CI report so an ignore is never silent."""
        for rule in self.ignores:
            if not fnmatch.fnmatch(test_name, rule.test):
                continue
            if rule.pattern is not None and not rule.pattern.search(failure_message or ""):
                continue
            return rule.reason or f"ignored via {rule.test!r}"
        return None


_KEYS: set[str] = {"test", "reason", "match"}


def _parse_rule(item: Any, index: int) -> IgnoreRule:
    if not isinstance(item, dict):
        raise ValueError(f"ignore rule #{index + 1} must be a mapping, got {type(item).__name__}")
    unknown = set(item) - _KEYS
    if unknown:
        raise ValueError(f"ignore rule #{index + 1} has unknown keys: {sorted(unknown)}")
    test = item.get("test")
    if not isinstance(test, str) or not test.strip():
        raise ValueError(f"ignore rule #{index + 1} requires a non-empty 'test' glob")
    reason = item.get("reason", "")
    # A rule without a reason is the rug-sweeping shape — silently ignoring a
    # failure is exactly what the ignore list must never do. Require it.
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(
            f"ignore rule #{index + 1} requires a non-empty 'reason' — "
            "every ignore must record why the failure is known-benign"
        )
    match = item.get("match", "")
    if match and not isinstance(match, str):
        raise ValueError(f"ignore rule #{index + 1} 'match' must be a string")
    pattern: re.Pattern[str] | None = None
    if match:
        try:
            pattern = re.compile(match)
        except re.error as exc:
            raise ValueError(f"ignore rule #{index + 1} has an invalid 'match' regex: {exc}") from exc
    return IgnoreRule(test=test, reason=reason, match=match, pattern=pattern)


def load_ignore_spec(path: str | Path | None) -> IgnoreSpec:
    """Load and validate ``.ai-test-ignore.yml``.

    Raises ``ValueError`` with a clear message on malformed content so the CI
    integration fails fast instead of silently ignoring the wrong things.
    ``None``/missing file yields an empty spec (no ignores).
    """
    if path is None:
        return IgnoreSpec()
    p = Path(path)
    if not p.exists():
        raise ValueError(f"ignore file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {p}: {exc}") from exc
    if raw is None:
        return IgnoreSpec(path=str(p))
    if not isinstance(raw, dict) or "ignores" not in raw:
        raise ValueError(f"{p} must contain an 'ignores' list")
    items = raw["ignores"]
    if not isinstance(items, list):
        raise ValueError(f"{p} 'ignores' must be a list")
    rules = tuple(_parse_rule(item, i) for i, item in enumerate(items))
    return IgnoreSpec(ignores=rules, path=str(p))
