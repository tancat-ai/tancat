"""Utilities for building pytest run commands in the Streamlit UI flow."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol


class RunTestLike(Protocol):
    """Protocol for minimal per-test run result data."""

    name: str
    status: str
    file_path: str


def get_failed_nodeids(run_results: Sequence[RunTestLike] | None) -> list[str]:
    """Return unique pytest nodeids for tests that failed in the previous run."""
    if run_results is None:
        return []

    nodeids: list[str] = []
    seen: set[str] = set()
    for result in run_results:
        if result.status.lower() not in {"failed", "error"}:
            continue
        nodeid = f"{result.file_path}::{result.name}"
        if nodeid in seen:
            continue
        seen.add(nodeid)
        nodeids.append(nodeid)
    return nodeids


def extract_failed_nodeids_from_raw_output(raw_output: str) -> list[str]:
    """Extract failed nodeids directly from raw pytest output lines."""
    failed_line_pattern = re.compile(r"(\S+\.py::\S+)\s+FAILED")
    nodeids: list[str] = []
    seen: set[str] = set()
    for line in raw_output.splitlines():
        match = failed_line_pattern.search(line)
        if match is None:
            continue
        nodeid = match.group(1)
        if nodeid in seen:
            continue
        seen.add(nodeid)
        nodeids.append(nodeid)
    return nodeids


def build_pytest_run_command(saved_path: str, failed_nodeids: Sequence[str] | None = None) -> list[str]:
    """Build the pytest command for full or failed-only execution in the UI flow."""
    command = [
        "pytest",
        "-o",
        "addopts=",
        "--browser=chromium",
        "--screenshot=only-on-failure",
        "-v",
        "--tb=short",
    ]
    if failed_nodeids:
        command.extend(failed_nodeids)
    else:
        command.append(saved_path)
    return command
