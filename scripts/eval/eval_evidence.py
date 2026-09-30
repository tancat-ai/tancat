"""Keep and re-read one held-out eval run's evidence (B-093).

A run whose evidence is deleted is a run nobody can re-score. The 2026-09-24
held-out measure wrote its log and emitted tests to ``scratch/`` and they were
later deleted, so the 38 misses could no longer be classified per placeholder.
This module gives a run **one known place** to keep its evidence, reads it back,
and reports exactly what is missing when a run finished without it.

Layout, one directory per run::

    <run-dir>/
      manifest.json               metadata + the gate numbers this run recorded
      summary.txt                 the human summary (HarnessReport.to_summary)
      results.json                per-placeholder result (HarnessReport.to_dict)
      verification_strength.json  the product's per-test verdicts (may be absent)
      emitted/test_eval_001.py    the emitted test files, one per story
      junit/test_eval_001.xml     per-test outcomes (pytest --junitxml)
      pytest/test_eval_001.log    raw pytest output, one per story

``scripts/eval/rescore.py`` reads this directory and recomputes the gate numbers
with no model call, no browser and no live site: gate 1 is static (emitted code
vs golden keys) and gate 2 is re-applied from the kept per-test outcomes.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
RESULTS_FILENAME = "results.json"
SUMMARY_FILENAME = "summary.txt"
VERDICTS_FILENAME = "verification_strength.json"
EMITTED_DIR = "emitted"
JUNIT_DIR = "junit"
PYTEST_LOG_DIR = "pytest"


class MissingEvidenceError(RuntimeError):
    """Raised when a run directory cannot be re-scored because evidence is gone.

    The message names every missing item, so a reader is told the score cannot
    be recomputed instead of silently reading a zero.
    """


def emitted_filename(story_id: str) -> str:
    """Return the per-story emitted test filename (B-094 slug rule)."""
    slug = re.sub(r"[^a-z0-9]+", "_", story_id.lower()).strip("_")
    return f"test_{slug}.py"


@dataclass
class RunEvidence:
    """One run's kept evidence, read back from disk."""

    run_dir: Path
    manifest: dict[str, Any] = field(default_factory=dict)
    code_map: dict[str, str] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    verdict_map: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    summary: str = ""

    def per_test(self, story_id: str) -> dict[str, str]:
        """Return the kept per-test outcomes for *story_id* (empty if none)."""
        path = self.run_dir / JUNIT_DIR / emitted_filename(story_id).replace(".py", ".xml")
        if not path.is_file():
            return {}
        from eval_runner import _parse_junit_xml

        return _parse_junit_xml(path)


def write_run_evidence(
    run_dir: str | Path,
    *,
    code_map: dict[str, str],
    results: list[Any],
    verdict_map: dict[str, list[dict[str, Any]]] | None = None,
    summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Write one run's evidence into *run_dir* and return the directory.

    The emitted tests, the per-placeholder result, the summary and the manifest
    are written here; ``run_full_validation`` writes ``junit/`` and ``pytest/``
    while the tests execute (see :func:`verify_run_evidence`).
    """
    from eval_metrics import HarnessReport

    run_dir = Path(run_dir)
    emitted_dir = run_dir / EMITTED_DIR
    emitted_dir.mkdir(parents=True, exist_ok=True)
    for story_id, code in code_map.items():
        (emitted_dir / emitted_filename(story_id)).write_text(code, encoding="utf-8")

    report = HarnessReport(stories=results)
    (run_dir / RESULTS_FILENAME).write_text(
        json.dumps(report.to_dict(), indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    if summary:
        (run_dir / SUMMARY_FILENAME).write_text(summary, encoding="utf-8")

    if verdict_map:
        (run_dir / VERDICTS_FILENAME).write_text(
            json.dumps(
                {"generated_at": datetime.now(UTC).isoformat(), "stories": verdict_map},
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    manifest: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "stories": sorted(code_map),
        "gate1_accuracy_pct": round(report.resolution_accuracy(), 1),
        "gate1_placeholders_total": report.total_placeholders,
        "gate1_placeholders_correct": report.correct_resolutions,
        "gate2_false_greens": report.total_false_positives,
        "tests_executed": report.total_tests_executed,
        "tests_passed": report.total_tests_passed,
    }
    manifest.update(metadata or {})
    (run_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    return run_dir


def verify_run_evidence(run_dir: str | Path) -> list[str]:
    """Return every item a run directory is missing (empty = complete).

    The guard the harness and the re-score tool both use: a run that finished
    without keeping this evidence cannot be re-scored, and that must be said
    plainly rather than read as a zero.
    """
    run_dir = Path(run_dir)
    problems: list[str] = []
    if not run_dir.is_dir():
        return [f"run directory does not exist: {run_dir}"]

    manifest_path = run_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        problems.append(f"missing {MANIFEST_FILENAME}")
    if not (run_dir / RESULTS_FILENAME).is_file():
        problems.append(f"missing {RESULTS_FILENAME}")

    emitted_dir = run_dir / EMITTED_DIR
    emitted = sorted(emitted_dir.glob("test_*.py")) if emitted_dir.is_dir() else []
    if not emitted:
        problems.append(f"missing emitted test files under {EMITTED_DIR}/")

    # A full run executes tests, so it must keep the per-test outcomes. A
    # static/resolver run has none by design.
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            problems.append(f"unreadable {MANIFEST_FILENAME}")
            manifest = {}
        if str(manifest.get("mode", "")) == "full":
            junit_dir = run_dir / JUNIT_DIR
            junit = sorted(junit_dir.glob("*.xml")) if junit_dir.is_dir() else []
            if not junit:
                problems.append(f"missing per-test outcomes under {JUNIT_DIR}/ (mode=full)")

    return problems


def read_run_evidence(run_dir: str | Path) -> RunEvidence:
    """Read a run's kept evidence, or raise :class:`MissingEvidenceError`.

    The error names every missing item so the caller can say the score cannot
    be recomputed, and why.
    """
    run_dir = Path(run_dir)
    problems = verify_run_evidence(run_dir)
    if problems:
        raise MissingEvidenceError(f"Cannot recompute the score for {run_dir}: " + "; ".join(problems))

    manifest = json.loads((run_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    results = json.loads((run_dir / RESULTS_FILENAME).read_text(encoding="utf-8"))

    # The story ids live in results.json; the emitted filename is derived from
    # the id, so no filename reverse-engineering is needed.
    code_map: dict[str, str] = {}
    for story in results.get("stories", []):
        story_id = str(story.get("story_id", ""))
        if not story_id:
            continue
        path = run_dir / EMITTED_DIR / emitted_filename(story_id)
        if path.is_file():
            code_map[story_id] = path.read_text(encoding="utf-8")

    verdict_map: dict[str, list[dict[str, Any]]] = {}
    verdicts_path = run_dir / VERDICTS_FILENAME
    if verdicts_path.is_file():
        payload = json.loads(verdicts_path.read_text(encoding="utf-8"))
        stories = payload.get("stories", {}) if isinstance(payload, dict) else {}
        if isinstance(stories, dict):
            verdict_map = {str(k): list(v) for k, v in stories.items() if isinstance(v, list)}

    summary_path = run_dir / SUMMARY_FILENAME
    summary = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else ""

    return RunEvidence(
        run_dir=run_dir,
        manifest=manifest,
        code_map=code_map,
        results=results,
        verdict_map=verdict_map,
        summary=summary,
    )


__all__ = [
    "EMITTED_DIR",
    "JUNIT_DIR",
    "MANIFEST_FILENAME",
    "PYTEST_LOG_DIR",
    "RESULTS_FILENAME",
    "SUMMARY_FILENAME",
    "VERDICTS_FILENAME",
    "MissingEvidenceError",
    "RunEvidence",
    "emitted_filename",
    "read_run_evidence",
    "verify_run_evidence",
    "write_run_evidence",
]
