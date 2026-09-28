"""Load and parse evidence JSON files from generated test packages.

Evidence JSON files are written by EvidenceTracker at runtime and contain
rich diagnostic context for failed steps: failure notes, suggested
alternative locators, available interactive elements, and screenshot paths.

This module provides utilities to load that data so it can be merged into
reports and displayed in the CLI debug view.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_evidence_for_package(package_dir: str) -> dict[str, dict[str, Any]]:
    """Load all evidence JSON files from a test package directory.

    Scans ``<package_dir>/evidence/`` for ``*.evidence.json`` files and
    returns a dict mapping test name (derived from filename) to the full
    evidence payload.

    Args:
        package_dir: Path to the test package directory (containing the
            generated test file and an ``evidence/`` subdirectory).

    Returns:
        Dict mapping test name stem to evidence dict.  For example:

        .. code-block:: python

            {
                "test_01_navigate_to_category[chromium]": {
                    "schema_version": "1.0",
                    "test": {...},
                    "steps": [...],
                    ...
                }
            }
    """
    evidence_dir = Path(package_dir) / "evidence"
    if not evidence_dir.is_dir():
        logger.debug("No evidence directory at %s", evidence_dir)
        return {}

    result: dict[str, dict[str, Any]] = {}
    for filepath in sorted(evidence_dir.glob("*.evidence.json")):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            # Key is the filename without the .evidence.json suffix
            test_name = filepath.stem.replace(".evidence", "")
            result[test_name] = data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load evidence file %s: %s", filepath.name, exc)

    logger.info("Loaded %d evidence file(s) from %s", len(result), evidence_dir)
    return result


def get_failure_diagnostics(evidence: dict[str, Any]) -> dict[str, Any]:
    """Extract failure diagnostics from a single evidence payload.

    Walks all steps in the evidence and collects diagnostic information
    for any failed steps.

    Args:
        evidence: A single evidence dict (as returned by
            :func:`load_evidence_for_package`).

    Returns:
        A dict with the following keys:

        - ``failed_steps`` (list[dict]) – per-step failure details
        - ``page_url`` (str) – URL of the page at end of test
        - ``page_title`` (str | None) – page title from last diagnosis
        - ``test_status`` (str) – overall test status
        - ``test_duration_s`` (float) – test duration in seconds
        - ``condition_ref`` (str) – test case reference ID
        - ``story_ref`` (str) – user story reference ID
    """
    test_info = evidence.get("test", {})
    page_info = evidence.get("page", {})
    steps = evidence.get("steps", [])

    failed_steps: list[dict[str, Any]] = []
    last_title: str | None = None

    for step in steps:
        result = step.get("result", {})
        if result.get("status") != "failed":
            continue

        diagnosis = result.get("diagnosis")
        failure_note = result.get("failure_note")

        step_diag: dict[str, Any] = {
            "step_number": step.get("step"),
            "step_type": step.get("type"),
            "label": step.get("label"),
            "locator": step.get("locator"),
            "error": result.get("error", ""),
            "error_summary": result.get("error", "")[:500],
            "failure_note": failure_note,
        }

        if diagnosis:
            step_diag["page_url_at_failure"] = diagnosis.get("url", "")
            step_diag["page_title_at_failure"] = diagnosis.get("title", "")
            step_diag["suggested_locators"] = diagnosis.get("suggested_locators", [])
            step_diag["available_elements"] = diagnosis.get("available_elements", [])
            last_title = diagnosis.get("title")
        else:
            step_diag["suggested_locators"] = []
            step_diag["available_elements"] = []

        failed_steps.append(step_diag)

    return {
        "failed_steps": failed_steps,
        "page_url": page_info.get("url", ""),
        "page_title": last_title,
        "test_status": test_info.get("status", "unknown"),
        "test_duration_s": test_info.get("duration_s", 0.0),
        "condition_ref": test_info.get("condition_ref", ""),
        "story_ref": test_info.get("story_ref", ""),
    }


def get_screenshot_paths(evidence: dict[str, Any]) -> list[str]:
    """Return screenshot paths from failed steps.

    Args:
        evidence: A single evidence dict.

    Returns:
        List of relative screenshot paths for steps that failed.
    """
    paths: list[str] = []
    for step in evidence.get("steps", []):
        result = step.get("result", {})
        if result.get("status") == "failed" and step.get("screenshot"):
            paths.append(step["screenshot"])
    return paths


def match_evidence_to_test(
    evidence_map: dict[str, dict[str, Any]],
    test_name: str,
) -> dict[str, Any] | None:
    """Find the best-matching evidence payload for a test name.

    Test names in pytest output may include parameterization suffixes like
    ``[chromium]``. This function tries exact match first, then falls back
    to prefix matching.

    Args:
        evidence_map: Output of :func:`load_evidence_for_package`.
        test_name: The test name to look up (e.g. ``test_01_navigate_to_category``).

    Returns:
        The matching evidence dict, or ``None`` if not found.
    """
    # Exact match
    if test_name in evidence_map:
        return evidence_map[test_name]

    # Strip common pytest suffixes and try again
    base_name = test_name.split("[", 1)[0]
    if base_name in evidence_map:
        return evidence_map[base_name]

    # Prefix match (handles parameterized names)
    for key, val in evidence_map.items():
        if key.startswith(base_name):
            return val

    return None


def load_verification_strength(package_dir: str | Path) -> dict[str, dict[str, Any]]:
    """Load the emitted per-test verification verdicts (B-100).

    Reads ``<package_dir>/verification_strength.json`` written by
    ``PipelineArtifactWriter`` and returns it keyed by test name. A missing or
    malformed file returns ``{}`` -- an older package without the emit-side
    verdict is not an error.

    Args:
        package_dir: Test package directory (the directory holding the
            generated ``test_*.py`` and ``verification_strength.json``).

    Returns:
        Dict mapping test name to its verdict dict.
    """
    path = Path(package_dir) / "verification_strength.json"
    if not path.is_file():
        logger.debug("No verification_strength.json at %s", path)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load %s: %s", path.name, exc)
        return {}
    verdicts = payload.get("verdicts", [])
    if not isinstance(verdicts, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for verdict in verdicts:
        if isinstance(verdict, dict) and verdict.get("test_name"):
            result[str(verdict["test_name"])] = verdict
    return result


def match_verification_to_test(
    verdicts: dict[str, dict[str, Any]],
    test_name: str,
) -> dict[str, Any] | None:
    """Find the verdict for a runtime test name (B-100).

    Mirrors :func:`match_evidence_to_test`: pytest emits ``test_01_x[chromium]``
    while the pipeline's verdict key is ``test_01_x``.
    """
    if test_name in verdicts:
        return verdicts[test_name]

    base_name = test_name.split("[", 1)[0]
    if base_name in verdicts:
        return verdicts[base_name]

    for key, verdict in verdicts.items():
        if key.startswith(base_name):
            return verdict

    return None


def get_verification(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return the B-100 verification verdict from an evidence payload.

    Returns ``{}`` when the sidecar predates the field, so report rendering
    stays backward compatible.
    """
    test_info = evidence.get("test", {})
    verification = test_info.get("verification", {})
    return verification if isinstance(verification, dict) else {}
