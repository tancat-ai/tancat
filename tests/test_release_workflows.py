"""Workflow-shape guards for the release path and the CI review fixes (t-0453).

These read the workflow YAML directly — no GitHub, no network. They pin the
decisions the CI review (t-0408) called out, so a later edit cannot silently
undo them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _load(name: str) -> dict[Any, Any]:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{name} did not parse to a mapping"
    return data


def _triggers(doc: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML parses the bare key ``on:`` as the boolean True (YAML 1.1), so the
    # mapping's keys are Any rather than str.
    triggers = doc.get("on", doc.get(True))
    return triggers if isinstance(triggers, dict) else {}


def test_release_workflow_is_tag_driven_and_gated() -> None:
    doc = _load("release.yml")
    tags = _triggers(doc)["push"]["tags"]
    assert "v*" in tags
    # The moving Action tag must not re-trigger a release when it is re-pointed.
    assert "!v1" in tags
    jobs = doc["jobs"]
    assert jobs["gates"]["uses"] == "./.github/workflows/ci.yml"
    for job in ("build", "release", "move-v1"):
        assert job in jobs, f"release.yml is missing the {job} job"
    assert jobs["build"]["needs"] == "gates"
    assert jobs["release"]["needs"] == "build"
    assert jobs["move-v1"]["needs"] == "release"


def test_ci_is_reusable_and_graph_freshness_is_gone() -> None:
    doc = _load("ci.yml")
    assert "workflow_call" in _triggers(doc)
    # graphify-out/ is gitignored, so the job could never see a graph on CI.
    assert "graph-freshness" not in doc["jobs"]


def test_ci_test_job_builds_and_exercises_the_wheel() -> None:
    doc = _load("ci.yml")
    steps = doc["jobs"]["test"]["steps"]
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    assert "uv build" in runs
    assert "tancat --help" in runs


def test_action_selftest_runs_on_prs_with_per_job_permissions() -> None:
    doc = _load("ci-cd-action.yml")
    assert "pull_request" in _triggers(doc)
    core = doc["jobs"]["action-self-test-core"]
    assert "pull_request" in core["if"]
    assert core["permissions"] == {"contents": "read"}
    full = doc["jobs"]["action-self-test-full"]
    assert full["permissions"] == {"contents": "read", "issues": "write"}


def test_mypy_parity_uses_the_pr_base_and_full_history() -> None:
    doc = _load("ci.yml")
    steps = doc["jobs"]["type-check"]["steps"]
    body = "\n".join(str(step.get("run", "")) for step in steps)
    assert "github.event.pull_request.base.sha" in body
    checkout = next(step for step in steps if str(step.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0
