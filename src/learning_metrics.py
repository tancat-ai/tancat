"""Learning-impact metrics extracted from evidence sidecars (AI-059).

This module is deliberately a pure analyzer.  It does not run Playwright,
invoke an LLM, read the learned store, or mutate production state.  A sidecar
is treated as the unit of analysis (one generated test), while the first
non-passing step is used to measure how far that test progressed.

The ratios returned by :class:`LearningImpactMetrics` are in the range
``0.0..1.0`` (rather than percentages), which makes the primary example
``(1.0 + .4 + 0.0) / 3 == .4666...`` directly representable.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.failure_classifier import FailureCategory, classify_failure

logger = logging.getLogger(__name__)

# Stable output keys.  Keep this list intentionally limited: these are the
# classes which can be compared between controlled baseline legs.
FAILURE_CLASSES: tuple[str, ...] = (
    "locator_failure",
    "assertion_failure",
    "navigation_failure",
    "infrastructure_timeout_failure",
)

_STATUS_PASS = "passed"


@dataclass(frozen=True)
class TestEvidenceMetric:
    """Metrics and classification for one evidence sidecar."""

    test_name: str
    status: str
    total_steps: int
    passed_steps: int
    pass_depth: float
    failure_class: str | None = None
    false_positive: bool = False


@dataclass
class LearningImpactMetrics:
    """Aggregated, store-independent metrics for one evidence directory.

    ``failure_class_breakdown`` counts failed *tests*, not failed steps.  This
    avoids overweighting a test which happened to emit duplicate failure
    records.  Its four keys are always present, including when their count is
    zero.
    """

    mean_pass_depth: float = 0.0
    first_pass_green_rate: float = 0.0
    false_positive_rate: float = 0.0
    failure_class_breakdown: dict[str, int] = field(default_factory=lambda: dict.fromkeys(FAILURE_CLASSES, 0))
    tests_analyzed: int = 0
    tests_passed: int = 0
    false_positive_count: int = 0
    unclassified_failure_count: int = 0
    per_test: list[TestEvidenceMetric] = field(default_factory=list)
    errors: int = 0

    def to_dict(self, *, include_per_test: bool = True) -> dict[str, Any]:
        """Return JSON-serializable metrics.

        ``per_test`` is useful for manual review and is included by default;
        callers persisting a compact run summary can disable it.
        """
        result: dict[str, Any] = {
            "mean_pass_depth": self.mean_pass_depth,
            "first_pass_green_rate": self.first_pass_green_rate,
            "false_positive_rate": self.false_positive_rate,
            "failure_class_breakdown": dict(self.failure_class_breakdown),
            "tests_analyzed": self.tests_analyzed,
            "tests_passed": self.tests_passed,
            "false_positive_count": self.false_positive_count,
            "unclassified_failure_count": self.unclassified_failure_count,
            "errors": self.errors,
        }
        if include_per_test:
            result["per_test"] = [asdict(item) for item in self.per_test]
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LearningImpactMetrics:
        """Load a previously persisted metric payload."""
        breakdown = {name: int((data.get("failure_class_breakdown") or {}).get(name, 0)) for name in FAILURE_CLASSES}
        per_test = [TestEvidenceMetric(**item) for item in data.get("per_test", []) or []]
        return cls(
            mean_pass_depth=float(data.get("mean_pass_depth", 0.0)),
            first_pass_green_rate=float(data.get("first_pass_green_rate", 0.0)),
            false_positive_rate=float(data.get("false_positive_rate", 0.0)),
            failure_class_breakdown=breakdown,
            tests_analyzed=int(data.get("tests_analyzed", 0)),
            tests_passed=int(data.get("tests_passed", 0)),
            false_positive_count=int(data.get("false_positive_count", 0)),
            unclassified_failure_count=int(data.get("unclassified_failure_count", 0)),
            per_test=per_test,
            errors=int(data.get("errors", 0)),
        )


def _status(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _step_result(step: Mapping[str, Any]) -> Mapping[str, Any]:
    result = step.get("result")
    return result if isinstance(result, Mapping) else step


def _step_passed(step: Mapping[str, Any]) -> bool:
    return _status(_step_result(step).get("status")) == _STATUS_PASS


def _test_status(data: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> str:
    test = data.get("test")
    test_map = test if isinstance(test, Mapping) else {}
    explicit = _status(test_map.get("status"))
    if explicit:
        return explicit
    # Older sidecars did not always include test.status.  Deriving it keeps
    # those sidecars measurable without pretending an empty test passed.
    if steps and all(_step_passed(step) for step in steps):
        return _STATUS_PASS
    return "failed"


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return _status(value) in {"1", "true", "yes", "y", "confirmed"}


def _is_false_positive(data: Mapping[str, Any], steps: Sequence[Mapping[str, Any]] = ()) -> bool:
    """Read an explicit manual-review false-positive annotation.

    False positives cannot be inferred from a pass alone: a sidecar has no
    target envelope until a human has reviewed it.  Several equivalent field
    locations are accepted so review tools can annotate either the test
    object or the sidecar root.
    """
    test = data.get("test")
    test_map = test if isinstance(test, Mapping) else {}
    candidates: list[Any] = [
        data.get("false_positive"),
        data.get("is_false_positive"),
        test_map.get("false_positive"),
        test_map.get("is_false_positive"),
    ]
    for key in ("integrity", "review", "manual_review", "quality"):
        nested = data.get(key)
        if isinstance(nested, Mapping):
            candidates.extend((nested.get("false_positive"), nested.get("is_false_positive")))
        nested_test = test_map.get(key)
        if isinstance(nested_test, Mapping):
            candidates.extend((nested_test.get("false_positive"), nested_test.get("is_false_positive")))
    if any(_bool_value(candidate) for candidate in candidates if candidate is not None):
        return True
    for step in steps:
        result = _step_result(step)
        if _bool_value(step.get("false_positive")) or _bool_value(result.get("false_positive")):
            return True
    return False


def _error_text(step: Mapping[str, Any], test_error: str = "") -> str:
    result = _step_result(step)
    parts: list[str] = []
    for source in (result, step):
        for key in ("error", "failure_note", "diagnosis", "message", "traceback", "details"):
            value = source.get(key)
            if value:
                parts.append(str(value))
    if test_error:
        parts.append(test_error)
    return "\n".join(parts)


def _normalise_failure_class(value: Any) -> str | None:
    if value is None:
        return None
    text = _status(value)
    text = re.sub(r"[/\\\s-]+", "_", text)
    aliases = {
        "locator": "locator_failure",
        "locator_timeout": "locator_failure",
        "strict_violation": "locator_failure",
        "locator_failure": "locator_failure",
        "assertion": "assertion_failure",
        "assertion_error": "assertion_failure",
        "assertion_failure": "assertion_failure",
        "navigation": "navigation_failure",
        "navigation_error": "navigation_failure",
        "navigation_failure": "navigation_failure",
        "infrastructure": "infrastructure_timeout_failure",
        "timeout": "infrastructure_timeout_failure",
        "infrastructure_timeout": "infrastructure_timeout_failure",
        "infrastructure_timeout_failure": "infrastructure_timeout_failure",
        "infra_timeout": "infrastructure_timeout_failure",
    }
    return aliases.get(text)


def _declared_total_steps(data: Mapping[str, Any], observed_steps: Sequence[Mapping[str, Any]]) -> int:
    """Use an explicit planned-step count when a sidecar provides one."""
    observed = len(observed_steps)
    test = data.get("test")
    test_map = test if isinstance(test, Mapping) else {}
    for source in (test_map, data):
        for key in ("total_steps", "planned_steps", "expected_steps", "step_count"):
            value = source.get(key)
            if isinstance(value, bool):
                continue
            try:
                declared = int(str(value))
            except TypeError, ValueError:
                continue
            if declared > 0:
                return max(declared, observed)
    # Some hand-authored sidecars retain the original step number even when
    # execution stopped early.  Respect that number when it is available.
    numbers: list[int] = []
    for step in observed_steps:
        try:
            number = int(str(step.get("step")))
        except TypeError, ValueError:
            continue
        if number > 0:
            numbers.append(number)
    return max([observed, *numbers], default=0)


def _classify_step(step: Mapping[str, Any], test_error: str = "") -> str | None:
    result = _step_result(step)
    for source in (result, step):
        for key in ("failure_class", "failure_category", "classification", "failure_type"):
            explicit = _normalise_failure_class(source.get(key))
            if explicit:
                return explicit

    text = _error_text(step, test_error)
    step_type = _status(step.get("type"))
    # Navigation's timeout is a navigation failure, not a locator failure.
    if step_type in {"navigate", "navigation", "goto"}:
        return "navigation_failure"
    classified = classify_failure(text)
    if classified.category in {FailureCategory.LOCATOR_TIMEOUT, FailureCategory.STRICT_VIOLATION}:
        return "locator_failure"
    if re.search(
        r"(?:locator|element).*(?:not found|not visible|not attached|outside viewport)",
        text,
        re.IGNORECASE,
    ):
        return "locator_failure"
    if classified.category == FailureCategory.ASSERTION_FAILURE:
        return "assertion_failure"
    if classified.category == FailureCategory.NAVIGATION_ERROR:
        return "navigation_failure"
    # Generic TimeoutError (without a locator wait) is infrastructure noise.
    if re.search(r"(?:timeout|timed[_ ]?out|browser.*closed|fixture|worker)", text, re.IGNORECASE):
        return "infrastructure_timeout_failure"
    if step_type in {"assert", "assertion", "verify", "expect"}:
        return "assertion_failure"
    return None


def analyze_sidecar(data: Mapping[str, Any]) -> TestEvidenceMetric:
    """Analyze one already-loaded sidecar mapping."""
    raw_steps = data.get("steps")
    steps: list[Mapping[str, Any]] = [
        step for step in (raw_steps if isinstance(raw_steps, list) else []) if isinstance(step, Mapping)
    ]
    test = data.get("test")
    test_map = test if isinstance(test, Mapping) else {}
    status = _test_status(data, steps)
    passed_steps = 0
    first_failure: Mapping[str, Any] | None = None
    for step in steps:
        if first_failure is None and _step_passed(step):
            passed_steps += 1
        elif first_failure is None:
            first_failure = step
    total_steps = _declared_total_steps(data, steps)
    # A test with no steps has no observable progress.  If all emitted steps
    # passed but the test failed in teardown, all observed work still counts.
    pass_depth = (passed_steps / total_steps) if total_steps else 0.0
    test_error = str(
        test_map.get("error", "")
        or test_map.get("failure_note", "")
        or data.get("error", "")
        or data.get("failure_note", "")
        or ""
    )
    failure_class = None
    for source in (test_map, data):
        for key in ("failure_class", "failure_category", "classification", "failure_type"):
            failure_class = _normalise_failure_class(source.get(key))
            if failure_class:
                break
        if failure_class:
            break
    if failure_class is None and first_failure is not None:
        failure_class = _classify_step(first_failure, test_error)
    if failure_class is None and _status(status) not in {_STATUS_PASS, ""}:
        failure_class = _classify_step({}, test_error)
    return TestEvidenceMetric(
        test_name=str(test_map.get("name", data.get("name", "")) or ""),
        status=status,
        total_steps=total_steps,
        passed_steps=passed_steps,
        pass_depth=pass_depth,
        failure_class=failure_class,
        false_positive=_is_false_positive(data, steps),
    )


def analyze_sidecars(
    evidence_dir: str | Path | Iterable[str | Path],
    *,
    include_invalid: bool = False,
) -> LearningImpactMetrics:
    """Extract learning metrics from ``*.evidence.json`` files.

    Corrupt or non-object JSON is skipped and counted in ``errors``.  Set
    ``include_invalid`` to include an invalid payload as a zero-step failed
    test; this is useful when diagnosing a broken evidence writer, but is not
    recommended for comparing learning legs.
    """
    metrics = LearningImpactMetrics()
    if isinstance(evidence_dir, (str, Path)):
        root = Path(evidence_dir)
        if root.is_file():
            sidecars = [root]
        elif root.is_dir():
            sidecars = sorted(root.glob("*.evidence.json"), key=lambda item: item.name)
        else:
            return metrics
    else:
        sidecars = sorted((Path(item) for item in evidence_dir), key=lambda item: item.name)
    for path in sidecars:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("sidecar root must be an object")
            metric = analyze_sidecar(payload)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            metrics.errors += 1
            logger.warning("Skipping invalid evidence sidecar %s: %s", path, exc)
            if not include_invalid:
                continue
            metric = TestEvidenceMetric(path.stem, "failed", 0, 0, 0.0)
        metrics.per_test.append(metric)

    metrics.tests_analyzed = len(metrics.per_test)
    metrics.tests_passed = sum(item.status == _STATUS_PASS for item in metrics.per_test)
    metrics.false_positive_count = sum(item.false_positive for item in metrics.per_test)
    if metrics.tests_analyzed:
        metrics.mean_pass_depth = sum(item.pass_depth for item in metrics.per_test) / metrics.tests_analyzed
        metrics.first_pass_green_rate = metrics.tests_passed / metrics.tests_analyzed
        metrics.false_positive_rate = metrics.false_positive_count / metrics.tests_analyzed
    for item in metrics.per_test:
        if item.status == _STATUS_PASS:
            continue
        if item.failure_class in metrics.failure_class_breakdown:
            metrics.failure_class_breakdown[item.failure_class] += 1
        else:
            metrics.unclassified_failure_count += 1
    return metrics


# Descriptive alias used by scripts and callers that think in terms of an
# extractor rather than an analyzer.
extract_metrics = analyze_sidecars


__all__ = [
    "FAILURE_CLASSES",
    "LearningImpactMetrics",
    "TestEvidenceMetric",
    "analyze_sidecar",
    "analyze_sidecars",
    "extract_metrics",
]
