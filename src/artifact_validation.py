"""Output artifact validation — AI-043 Layer 1 (deterministic invariants).

Report artifacts (heatmap overlays, Gantt timelines, Plotly charts) must be
truthful to the run that produced them. Unit tests validate the chart
*builders*; this module validates the **rendered artifacts and their source
data** against deterministic invariants:

- Heatmap points are viewport-percentages of the full document (0..100) —
  legacy sidecars recorded raw pixels (e.g. ``x: 273.5``), which the overlay
  treats as 273% and paints off-page.
- Payloads embedded in the shipped HTML must be parseable, finite, and
  internally consistent (aggregated counts == status counts).
- Gantt durations must be finite and non-negative — a single NaN/negative
  ``duration_s`` propagates through the sequential timeline and collapses the
  chart.
- Plotly figures must carry no NaN/None/empty series.

Every function returns ``list[ArtifactIssue]``; an artifact passes when it has
no ``severity == "error"`` issues (warnings are tolerated).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.gantt_utils import GanttEntry, build_gantt_chart, load_gantt_entries
from src.heatmap_utils import generate_suite_heatmap

#: Statuses the heatmap / gantt colour maps understand.
KNOWN_STATUSES: frozenset[str] = frozenset({"passed", "partial_pass", "failed", "skipped", "pending", "unknown"})

_POINT_RANGE = (0.0, 100.0)


@dataclass(frozen=True)
class ArtifactIssue:
    """One violation of an output-artifact invariant."""

    artifact: str  # e.g. "heatmap" / "gantt" / "chart"
    severity: str  # "error" | "warning"
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactValidationResult:
    """Aggregate result of validating a set of artifacts."""

    issues: list[ArtifactIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ArtifactIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ArtifactIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _in_range(value: Any, lo: float, hi: float) -> bool:
    return _finite(value) and lo <= float(value) <= hi


# ---------------------------------------------------------------------------
# Heatmap invariants
# ---------------------------------------------------------------------------


def validate_step_points(points_by_url: dict[str, list[dict[str, Any]]]) -> list[ArtifactIssue]:
    """Validate extracted step points (the data the overlay renders).

    Invariants (I1/I5/I6):
    - coordinates are finite percentages of the full document in [0, 100]
    - ``status`` is a known status (colour map can render it)
    - ``run_count`` is a positive number
    """
    issues: list[ArtifactIssue] = []
    for url, points in points_by_url.items():
        for idx, point in enumerate(points):
            x, y = point.get("x"), point.get("y")
            if not _in_range(x, *_POINT_RANGE):
                issues.append(
                    ArtifactIssue(
                        artifact="heatmap",
                        severity="error",
                        message=f"point {idx} on {url!r} has out-of-range x={x!r} (expected % of document in [0, 100])",
                        context={"url": url, "point_index": idx, "x": x, "y": y},
                    )
                )
            if not _in_range(y, *_POINT_RANGE):
                issues.append(
                    ArtifactIssue(
                        artifact="heatmap",
                        severity="error",
                        message=f"point {idx} on {url!r} has out-of-range y={y!r} (expected % of document in [0, 100])",
                        context={"url": url, "point_index": idx, "y": y},
                    )
                )
            status = point.get("status")
            if status is not None and status not in KNOWN_STATUSES:
                issues.append(
                    ArtifactIssue(
                        artifact="heatmap",
                        severity="warning",
                        message=f"point {idx} on {url!r} has unknown status {status!r}",
                        context={"url": url, "point_index": idx, "status": status},
                    )
                )
            run_count = point.get("run_count", 1)
            if not (isinstance(run_count, (int, float)) and run_count >= 1):
                issues.append(
                    ArtifactIssue(
                        artifact="heatmap",
                        severity="warning",
                        message=f"point {idx} on {url!r} has invalid run_count={run_count!r}",
                        context={"url": url, "point_index": idx, "run_count": run_count},
                    )
                )
    return issues


def _extract_js_payload(html: str, var_name: str) -> Any | None:
    """Extract a JSON payload embedded as ``const <var> = ...;`` in the heatmap HTML."""
    match = re.search(rf"const {re.escape(var_name)} = (.*?);\n", html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def _count_statuses(statuses: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in statuses:
        key = str(s)
        counts[key] = counts.get(key, 0) + 1
    return counts


def validate_suite_heatmap(evidence_dir: Path, page_url: str) -> list[ArtifactIssue]:
    """Render the suite heatmap for one URL and validate it end-to-end.

    Runs the real ``generate_suite_heatmap`` (the shipped artifact), extracts
    the embedded ``allPoints`` / ``aggregated`` payloads and checks:

    - payloads are present and parseable
    - every rendered point has finite in-range % coordinates and a known status
    - aggregated elements are internally consistent (counts add up, position
      in range) and match the rendered summary stats
    - a background screenshot is embedded whenever points exist
    """
    issues: list[ArtifactIssue] = []
    if not evidence_dir.exists():
        return [
            ArtifactIssue(
                artifact="heatmap",
                severity="error",
                message=f"evidence directory not found: {evidence_dir}",
            )
        ]

    html = generate_suite_heatmap(evidence_dir=evidence_dir, page_url=page_url)

    # Legitimately-empty render (no sidecars for this URL) is valid.
    if "No evidence points" in html:
        return issues

    points = _extract_js_payload(html, "allPoints")
    aggregated = _extract_js_payload(html, "aggregated")
    if not isinstance(points, list):
        return [
            ArtifactIssue(
                artifact="heatmap",
                severity="error",
                message=f"allPoints payload unparseable for {page_url!r}",
                context={"url": page_url},
            )
        ]
    if not isinstance(aggregated, list):
        return [
            ArtifactIssue(
                artifact="heatmap",
                severity="error",
                message=f"aggregated payload unparseable for {page_url!r}",
                context={"url": page_url},
            )
        ]

    issues.extend(validate_step_points({"<html payload>": points}))

    # I5: payload numbers must be finite (json.dumps emits NaN literals → broken JS).
    if any(not _finite(v) for p in points for v in (p.get("x"), p.get("y"), p.get("run_count", 1))):
        issues.append(
            ArtifactIssue(
                artifact="heatmap",
                severity="error",
                message=f"non-finite number in allPoints payload for {page_url!r}",
                context={"url": page_url},
            )
        )

    # Aggregated-element internal consistency.
    for elem in aggregated:
        if not isinstance(elem, dict):
            continue
        statuses: list[Any] = elem.get("statuses", [])
        total = elem.get("total")
        counts = _count_statuses(statuses)
        if total != len(statuses):
            issues.append(
                ArtifactIssue(
                    artifact="heatmap",
                    severity="error",
                    message=f"aggregated element at {elem.get('x')},{elem.get('y')} total={total} != {len(statuses)} statuses",
                )
            )
        if counts.get("passed", 0) + counts.get("partial_pass", 0) + counts.get("failed", 0) + counts.get(
            "skipped", 0
        ) != len(statuses):
            issues.append(
                ArtifactIssue(
                    artifact="heatmap",
                    severity="error",
                    message=f"aggregated element at {elem.get('x')},{elem.get('y')} status counts do not sum to total",
                )
            )
        if not _in_range(elem.get("x"), *_POINT_RANGE) or not _in_range(elem.get("y"), *_POINT_RANGE):
            issues.append(
                ArtifactIssue(
                    artifact="heatmap",
                    severity="error",
                    message=f"aggregated element position out of range: x={elem.get('x')!r} y={elem.get('y')!r}",
                )
            )

    # Summary stats in the HTML must match the payload.
    total_match = re.search(r"<strong>Total:</strong> (\d+) evidence points", html)
    if total_match and int(total_match.group(1)) != len(points):
        issues.append(
            ArtifactIssue(
                artifact="heatmap",
                severity="error",
                message=f"rendered total {total_match.group(1)} != payload points {len(points)}",
            )
        )

    # Background screenshot: points without a background render on a placeholder
    # box — misleading (markers positioned against an imaginary 16:9 frame).
    if points and "No screenshot available" in html:
        issues.append(
            ArtifactIssue(
                artifact="heatmap",
                severity="warning",
                message=f"points rendered without a background screenshot for {page_url!r}",
                context={"url": page_url},
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Gantt invariants
# ---------------------------------------------------------------------------


def validate_gantt_entries(entries: Iterable[GanttEntry]) -> list[ArtifactIssue]:
    """Validate loaded Gantt entries.

    Invariants (G1/G3):
    - ``duration_s`` is finite and >= 0 (NaN/negative collapses the timeline)
    - status is a known status (colour map can render it)
    """
    issues: list[ArtifactIssue] = []
    for entry in entries:
        if not _finite(entry.duration_s) or entry.duration_s < 0:
            issues.append(
                ArtifactIssue(
                    artifact="gantt",
                    severity="error",
                    message=f"{entry.condition_ref} has invalid duration_s={entry.duration_s!r}",
                    context={"condition_ref": entry.condition_ref, "duration_s": entry.duration_s},
                )
            )
        if entry.status not in KNOWN_STATUSES:
            issues.append(
                ArtifactIssue(
                    artifact="gantt",
                    severity="warning",
                    message=f"{entry.condition_ref} has unknown status {entry.status!r}",
                    context={"condition_ref": entry.condition_ref, "status": entry.status},
                )
            )
    return issues


def validate_gantt_chart(entries: list[GanttEntry]) -> list[ArtifactIssue]:
    """Build the real Gantt figure and validate its rendered data.

    Checks every bar's ``base`` (start) and ``x`` (duration) are finite and
    non-negative — a NaN/negative anywhere means the sequential timeline is
    broken.
    """
    issues: list[ArtifactIssue] = []
    if not entries:
        return issues
    fig = build_gantt_chart(entries)
    for trace in fig.data:
        base_raw = getattr(trace, "base", None)
        x_raw = getattr(trace, "x", None)
        base = list(base_raw) if base_raw is not None else []
        x = list(x_raw) if x_raw is not None else []
        for b in base:
            if not _finite(b) or b < 0:
                issues.append(
                    ArtifactIssue(
                        artifact="gantt",
                        severity="error",
                        message=f"bar start (base) out of range: {b!r}",
                    )
                )
        for v in x:
            if not _finite(v) or v < 0:
                issues.append(
                    ArtifactIssue(
                        artifact="gantt",
                        severity="error",
                        message=f"bar duration out of range: {v!r}",
                    )
                )
        if not base or not x or len(base) != len(x):
            issues.append(
                ArtifactIssue(
                    artifact="gantt",
                    severity="error",
                    message="gantt trace has empty or mismatched base/x arrays",
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Generic Plotly figure invariants
# ---------------------------------------------------------------------------


def validate_plotly_figure(fig: Any, artifact: str) -> list[ArtifactIssue]:
    """Generic chart sanity: no NaN/None/empty series in any trace."""
    issues: list[ArtifactIssue] = []
    try:
        traces = list(fig.data)
    except Exception as exc:
        return [
            ArtifactIssue(
                artifact=artifact,
                severity="error",
                message=f"figure has no readable data: {exc}",
            )
        ]
    if not traces:
        issues.append(
            ArtifactIssue(
                artifact=artifact,
                severity="error",
                message="figure contains no traces",
            )
        )
        return issues
    for idx, trace in enumerate(traces):
        for attr in ("x", "y", "base", "values", "labels"):
            raw = getattr(trace, attr, None)
            values = list(raw) if raw is not None else []
            for v in values:
                if v is None:
                    issues.append(
                        ArtifactIssue(
                            artifact=artifact,
                            severity="error",
                            message=f"trace {idx} has None in {attr}",
                            context={"trace_index": idx, "attr": attr},
                        )
                    )
                elif isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isfinite(v):
                    issues.append(
                        ArtifactIssue(
                            artifact=artifact,
                            severity="error",
                            message=f"trace {idx} has non-finite value in {attr}: {v!r}",
                            context={"trace_index": idx, "attr": attr},
                        )
                    )
    return issues


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def validate_evidence_artifacts(evidence_dir: Path, page_urls: list[str]) -> ArtifactValidationResult:
    """Run every Layer-1 invariant against one evidence directory."""
    issues: list[ArtifactIssue] = []

    for url in page_urls:
        issues.extend(validate_suite_heatmap(evidence_dir, url))

    entries = load_gantt_entries(evidence_dir)
    issues.extend(validate_gantt_entries(entries))
    issues.extend(validate_gantt_chart(entries))

    return ArtifactValidationResult(issues=issues)
