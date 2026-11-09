"""j-0296 / d-0148: the CI surface reports the same facts as the other surfaces.

The nightly issue used to be hand-written prose inside the workflow - a title, a
run link, a date and "re-run it" - so the one CI artefact a person reads carried
no counts and no failing test, and could only drift from the report. These tests
hold the CI surface to the same rule as the others: one source (report.json),
two readers (the issue body and the PR comment), and the JSON + HTML artefacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "action"))

import issue_body  # type: ignore[import-not-found]  # noqa: E402
import report as ci_report  # type: ignore[import-not-found]  # noqa: E402


def _junit(tmp_path: Path) -> Path:
    """A junit.xml with two passes and two named failures."""
    path = tmp_path / "junit.xml"
    path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite tests="4" failures="2" errors="0" skipped="0" time="3.5">
    <testcase name="test_01_login[chromium]" classname="test_login" />
    <testcase name="test_02_cart[chromium]" classname="test_cart" />
    <testcase name="test_03_checkout[chromium]" classname="test_checkout">
      <failure message="Locator '#pay' not found">trace</failure>
    </testcase>
    <testcase name="test_04_confirm[chromium]" classname="test_confirm">
      <failure message="expected 'ok' but got 'no'">trace</failure>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )
    return path


def _run_report(tmp_path: Path) -> dict[str, Any]:
    out = tmp_path / "results"
    assert ci_report.main(["--mode", "run-existing", "--junit", str(_junit(tmp_path)), "--output", str(out)]) == 0
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def test_the_issue_body_carries_the_counts_and_the_failing_test_names(tmp_path: Path) -> None:
    """The old body had neither - it was prose typed into the workflow."""
    payload = _run_report(tmp_path)

    body = issue_body.render_issue_body(
        [{**payload, "_report_path": "ci-results/report.json"}],
        run_url="https://example.test/actions/runs/42",
        date="2026-11-06",
    )

    assert "4 (2 passed · 2 failed · 0 errors · 0 skipped)" in body, body
    assert "test_03_checkout[chromium]" in body
    assert "test_04_confirm[chromium]" in body
    assert "https://example.test/actions/runs/42" in body
    assert "2026-11-06" in body
    # The same file the comment and the HTML artefact come from.
    assert "report.json" in body


def test_a_run_with_no_report_still_announces_itself() -> None:
    """A run that died before writing a report must still file a useful issue."""
    body = issue_body.render_issue_body([], run_url="https://example.test/actions/runs/7", date="2026-11-06")

    assert "No report reached this job" in body
    assert "https://example.test/actions/runs/7" in body
    assert "Run workflow" in body


def test_the_ci_surface_ships_json_and_html(tmp_path: Path) -> None:
    """Reusing the product's writers: report.json and report.html, not prose alone."""
    out = tmp_path / "results"
    assert ci_report.main(["--mode", "run-existing", "--junit", str(_junit(tmp_path)), "--output", str(out)]) == 0

    assert (out / "report.json").is_file()
    assert (out / "report.md").is_file()
    html_path = out / "report.html"
    assert html_path.is_file(), "the CI run left no HTML artefact"
    html = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "test_03_checkout[chromium]" in html, "the HTML does not name the failing test"

    from src.report_formats import PARITY_REQUIRED, SURFACE_FORMATS

    written = {"markdown", "json", "html"}
    assert written == set(SURFACE_FORMATS["ci_action"])
    assert set(PARITY_REQUIRED) <= written


def _workflow(name: str) -> str:
    return (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def _step_block(workflow: str, step_name: str) -> str:
    """The YAML text of one step, from its ``- name:`` to the next one."""
    start = workflow.index(f"- name: {step_name}")
    rest = workflow[start:]
    end = rest.find("\n      - name:", 1)
    return rest if end == -1 else rest[:end]


def test_a_missing_leg_still_produces_an_announcement() -> None:
    """d-0150: the summary exits 3; without always() the comment step is skipped."""
    workflow = _workflow("eval-harness.yml")

    summary = _step_block(workflow, "Generate markdown summary")
    assert "continue-on-error: true" in summary, "a missing leg would abort the job before the comment"

    comment = _step_block(workflow, "Post summary as PR comment")
    assert "always()" in comment, "a red dispatch would post no comment at all"


def test_the_nightly_issue_body_is_generated_not_typed() -> None:
    """The workflow must call the generator; prose in YAML is the defect."""
    workflow = _workflow("ci-cd-action.yml")

    assert "action/issue_body.py" in workflow
    body = _step_block(workflow, "File issue on failure (forced visibility)")
    for stale in ("Re-run: Actions", "The forced nightly full self-test"):
        assert stale not in body, f"hand-written prose is back in the issue step: {stale!r}"


@pytest.mark.parametrize("name", ["ci-cd-action.yml", "eval-harness.yml"])
def test_the_changed_workflows_are_parseable(name: str) -> None:
    yaml = pytest.importorskip("yaml")
    assert isinstance(yaml.safe_load(_workflow(name)), dict)


# -- j-0296 blockers: the interpreter the workflow uses, and HTML agreement ---


def _html_stat(html: str, label: str) -> int:
    """The number in the HTML stat tile for *label*."""
    marker = f"<div class='stat-label'>{label}</div>"
    head = html[: html.index(marker)]
    value = head[head.rindex("<div class='stat-value'>") + len("<div class='stat-value'>") :]
    return int(value.split("<", 1)[0])


def test_the_html_totals_agree_with_the_report_it_was_built_from(tmp_path: Path) -> None:
    """The old HTML said 3 tests / 1 passed for a report that says 4 / 2."""
    out = tmp_path / "results"
    assert ci_report.main(["--mode", "run-existing", "--junit", str(_junit(tmp_path)), "--output", str(out)]) == 0

    payload = json.loads((out / "report.json").read_text(encoding="utf-8"))
    html = (out / "report.html").read_text(encoding="utf-8")
    tests = payload["tests"]

    assert _html_stat(html, "Total Tests") == tests["total"], "the HTML total disagrees with report.json"
    assert _html_stat(html, "Passed") == tests["passed"], "the HTML passed count disagrees with report.json"
    assert _html_stat(html, "Failed") == tests["failed"] + tests["errors"]
    assert _html_stat(html, "Pending") == tests["skipped"]
    # The named failures are still listed, so the HTML is not only counts.
    assert "test_03_checkout[chromium]" in html


def test_the_issue_body_labels_rows_by_mode_not_by_folder() -> None:
    body = issue_body.render_issue_body(
        [
            {
                "mode": "run-existing",
                "tests": {"total": 2, "passed": 1, "failed": 1, "errors": 0, "skipped": 0},
                "failed_tests": [{"test": "test_cart", "message": "boom"}],
                "_report_path": "ci-results/report.json",
            }
        ],
        run_url="https://example.test/runs/1",
        date="2026-11-06",
    )

    assert "test_cart` (run-existing)" in body
    assert "ci-results" not in body, "the row still labels the artifact folder"
    assert "one leg" in body, "a single report must not imply the whole six-mode run"


def test_the_nightly_generator_runs_under_an_interpreter_that_can_parse_it() -> None:
    """j-0296 blocker: bare ``python3`` on the runner could not run this repo.

    The finding: ``action/issue_body.py`` (like 75 other places in the tree) used
    PEP 758's ``except A, B:`` - a SyntaxError below 3.14. Ruff's formatter here
    targets 3.14 and normalises that form back, so "write parentheses everywhere"
    is not a remedy the tree can hold: the interpreter must be pinned. The repo is
    3.14-only anyway (four modules use t-strings).

    So the guard is on the workflow, not on the syntax: the job that runs the
    generator must set up Python 3.14 before it does, and the module must parse
    under that grammar.
    """
    import ast

    generator = REPO_ROOT / "action" / "issue_body.py"
    ast.parse(generator.read_text(encoding="utf-8"), filename=str(generator), feature_version=(3, 14))

    workflow = _workflow("ci-cd-action.yml")
    generator_step = workflow.index("action/issue_body.py")
    setup_step = workflow.rfind('python-version: "3.14"')
    assert setup_step != -1, "the nightly job does not pin Python 3.14 - a bare python3 cannot parse this repo"
    assert setup_step < generator_step, "the generator runs before the interpreter is set up"

    # Any workflow that runs a repo MODULE must pin 3.14 (or go through uv).
    # Inline ``python - <<PY`` stubs are exempt: they are the workflow's own few
    # lines, not the repo's code.
    import re

    for name in ("ci.yml", "eval-harness.yml", "action-self-test-full.yml", "ci-cd-action.yml", "pages-deploy.yml"):
        text = _workflow(name)
        if re.search(r"python3?\s+(action|scripts|src|cli)/", text):
            assert 'python-version: "3.14"' in text or "uv run" in text, (
                f"{name} runs a repo module without pinning 3.14 or going through uv"
            )
