"""Expected-red baseline for ``scripts/verify_production.py``.

The production gate (``python scripts/verify_production.py``) has been
continuously RED since 2026-08-01. Two gate failures per site are *known*
and expected:

* ``Pipeline resolved all placeholders`` — the pipeline records the
  ``pytest.skip(...)`` lines it emitted for ASSERT targets it could not
  resolve. The count varies run to run (0-4 across 67 historical runs, LLM
  variance), so the baseline records a variance *ceiling*, not an exact
  number.
* ``No pytest.skip`` — the honest-skip consequence of the same unresolved
  ASSERT placeholders.

Without a recorded baseline, nobody can answer "is this run a regression?"
without re-deriving the known-failure set from scratch. This module records
that set in ``scripts/verify_production_baseline.json`` and compares a fresh
run against it:

* a gate that fails and is **not** in the known set → regression (exit 1)
* a known-failing gate that now passes → improvement (report, exit 0)
* the unresolved-placeholder count exceeding the recorded ceiling → regression

The logic here is pure (JSON load + comparison), so it is unit-tested in
``tests/test_verify_baseline.py``; the script itself stays thin.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Matches a trailing dynamic suffix such as ``" (44.1s)"`` or
#: ``" (openai-local/qwen)"``. Only a parenthesised group at the very end is
#: stripped, so static names that contain no trailing parens are untouched.
_DYNAMIC_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")


def stable_gate_key(name: str) -> str:
    """Return the machine-stable identity of a gate name.

    Gate names embed per-run values (durations, provider/model) that differ
    between machines and runs. Stripping the trailing parenthesised suffix
    lets a baseline recorded once match every later run::

        "Test execution (44.1s)"   -> "Test execution"
        "LLM connected (openai-local/qwen)" -> "LLM connected"
        "Test functions >= 5"      -> "Test functions >= 5"
    """
    return _DYNAMIC_SUFFIX.sub("", name).strip()


@dataclass(frozen=True)
class SiteBaseline:
    """Recorded expected-red state for one verified site."""

    known_failing_gates: tuple[str, ...] = ()
    max_unresolved_placeholders: int = 0
    known_unresolved_placeholders: tuple[str, ...] = ()
    expected_min_tests: int = 0
    #: Short-name prefixes of tests expected to fail from the known
    #: unresolved/wrong-ASSERT class (e.g. ``"test_07"``). A failure in a test
    #: that matches none of these is a regression.
    expected_failing_tests: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerifyBaseline:
    """The whole recorded expected-red baseline."""

    version: int
    recorded: str
    recorded_commit: str
    sites: dict[str, SiteBaseline] = field(default_factory=dict)
    note: str = ""


@dataclass
class SiteComparison:
    """Outcome of comparing one site's fresh run against its baseline entry."""

    site_id: str
    new_failures: list[str] = field(default_factory=list)
    tolerated_failures: list[str] = field(default_factory=list)
    fixed_gates: list[str] = field(default_factory=list)
    new_failed_tests: list[str] = field(default_factory=list)
    tolerated_failed_tests: list[str] = field(default_factory=list)
    unresolved_count: int = 0
    unresolved_budget: int = 0

    @property
    def unresolved_over_budget(self) -> int:
        return max(0, self.unresolved_count - self.unresolved_budget)

    @property
    def regressed(self) -> bool:
        return bool(self.new_failures) or bool(self.new_failed_tests) or self.unresolved_over_budget > 0

    @property
    def improved(self) -> bool:
        return bool(self.fixed_gates) and not self.regressed


@dataclass
class BaselineComparison:
    """Aggregate comparison across all verified sites."""

    sites: list[SiteComparison] = field(default_factory=list)

    @property
    def regressed(self) -> bool:
        return any(s.regressed for s in self.sites)

    @property
    def new_failures(self) -> list[str]:
        return [f"{s.site_id}: {name}" for s in self.sites for name in s.new_failures]

    @property
    def tolerated_failures(self) -> list[str]:
        return [f"{s.site_id}: {name}" for s in self.sites for name in s.tolerated_failures]

    @property
    def fixed_gates(self) -> list[str]:
        return [f"{s.site_id}: {name}" for s in self.sites for name in s.fixed_gates]

    @property
    def new_failed_tests(self) -> list[str]:
        return [f"{s.site_id}: {name}" for s in self.sites for name in s.new_failed_tests]


def load_baseline(path: Path) -> VerifyBaseline:
    """Load and parse a baseline JSON file.

    Raises:
        FileNotFoundError: if *path* does not exist.
        ValueError: if the file is not valid JSON or is missing required keys.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - message passthrough
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    return parse_baseline(data, source=str(path))


def parse_baseline(data: Any, source: str = "<inline>") -> VerifyBaseline:
    """Validate and convert a parsed baseline mapping into a :class:`VerifyBaseline`."""
    if not isinstance(data, dict):
        raise ValueError(f"{source}: baseline must be a JSON object")
    raw_sites = data.get("sites")
    if not isinstance(raw_sites, dict) or not raw_sites:
        raise ValueError(f"{source}: 'sites' must be a non-empty object")
    sites: dict[str, SiteBaseline] = {}
    for site_id, entry in raw_sites.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{source}: sites.{site_id} must be an object")
        gates = entry.get("known_failing_gates", [])
        if not isinstance(gates, list) or not all(isinstance(g, str) for g in gates):
            raise ValueError(f"{source}: sites.{site_id}.known_failing_gates must be a list of strings")
        unresolved = entry.get("known_unresolved_placeholders", [])
        if not isinstance(unresolved, list) or not all(isinstance(u, str) for u in unresolved):
            raise ValueError(f"{source}: sites.{site_id}.known_unresolved_placeholders must be a list of strings")
        budget = entry.get("max_unresolved_placeholders", 0)
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
            raise ValueError(f"{source}: sites.{site_id}.max_unresolved_placeholders must be a non-negative int")
        expected_min_tests = entry.get("expected_min_tests", 0)
        if not isinstance(expected_min_tests, int) or isinstance(expected_min_tests, bool) or expected_min_tests < 0:
            raise ValueError(f"{source}: sites.{site_id}.expected_min_tests must be a non-negative int")
        expected_failing = entry.get("expected_failing_tests", [])
        if not isinstance(expected_failing, list) or not all(isinstance(t, str) for t in expected_failing):
            raise ValueError(f"{source}: sites.{site_id}.expected_failing_tests must be a list of strings")
        sites[str(site_id)] = SiteBaseline(
            known_failing_gates=tuple(stable_gate_key(g) for g in gates),
            max_unresolved_placeholders=budget,
            known_unresolved_placeholders=tuple(unresolved),
            expected_min_tests=expected_min_tests,
            expected_failing_tests=tuple(expected_failing),
        )
    return VerifyBaseline(
        version=int(data.get("version", 1)),
        recorded=str(data.get("recorded", "")),
        recorded_commit=str(data.get("recorded_commit", "")),
        sites=sites,
        note=str(data.get("note", "")),
    )


def short_test_name(node_id: str) -> str:
    """Return the parameter-free short name of a pytest node id.

    ``"generated_tests/x/test_a.py::test_07_example[chromium]"`` ->
    ``"test_07_example"``.
    """
    name = node_id.rsplit("::", 1)[-1]
    return name.split("[", 1)[0]


def _matches_expected(test_name: str, expected_prefixes: tuple[str, ...]) -> bool:
    return any(test_name.startswith(prefix) for prefix in expected_prefixes)


def compare_site(
    site_id: str,
    gates: list[tuple[str, bool]],
    unresolved_placeholders: list[str],
    baseline: SiteBaseline,
    failed_tests: list[str] | None = None,
) -> SiteComparison:
    """Compare one site's fresh run against its baseline entry.

    Args:
        site_id: Site identifier (for reporting).
        gates: ``(gate_name, passed)`` pairs from the fresh run.
        unresolved_placeholders: Pipeline-reported unresolved placeholders
            (one entry per emitted ``pytest.skip`` line).
        baseline: The recorded expected-red state for this site.
        failed_tests: Short names of tests that failed at execution
            (e.g. ``test_07_example``). A test whose name matches no recorded
            ``expected_failing_tests`` prefix is a regression.

    Returns:
        A :class:`SiteComparison`; ``.regressed`` is True when a gate failed
        that the baseline did not expect to fail, an unexpected test failed,
        or the unresolved count exceeded the recorded ceiling.
    """
    known = set(baseline.known_failing_gates)
    comparison = SiteComparison(
        site_id=site_id,
        unresolved_count=len(unresolved_placeholders),
        unresolved_budget=baseline.max_unresolved_placeholders,
    )
    for raw_name in failed_tests or []:
        name = short_test_name(raw_name)
        if _matches_expected(name, baseline.expected_failing_tests):
            comparison.tolerated_failed_tests.append(name)
        else:
            comparison.new_failed_tests.append(name)

    for name, passed in gates:
        key = stable_gate_key(name)
        if passed:
            if key in known:
                comparison.fixed_gates.append(key)
        elif key in known:
            comparison.tolerated_failures.append(key)
        elif key == "Test execution" and comparison.tolerated_failed_tests and not comparison.new_failed_tests:
            # The execution gate failed, but every failing test is a recorded
            # known-fragile one — tolerate the gate, not the whole gate name.
            comparison.tolerated_failures.append(key)
        else:
            comparison.new_failures.append(key)
    return comparison


def compare_run(
    baseline: VerifyBaseline,
    runs: dict[str, tuple[list[tuple[str, bool]], list[str], list[str]]],
) -> BaselineComparison:
    """Compare every site in *runs* against *baseline*.

    Args:
        baseline: Loaded expected-red baseline.
        runs: ``site_id -> (gates, unresolved_placeholders, failed_tests)``.

    Sites present in *runs* but absent from the baseline are compared against
    an empty :class:`SiteBaseline` — any failure there is a regression (the
    baseline never tolerated it).
    """
    result = BaselineComparison()
    for site_id, (gates, unresolved, failed_tests) in runs.items():
        entry = baseline.sites.get(site_id, SiteBaseline())
        result.sites.append(compare_site(site_id, gates, unresolved, entry, failed_tests))
    return result
