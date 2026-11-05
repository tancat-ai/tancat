"""j-0286: parity of facts between the local surfaces.

The owner settled this on 2026-11-05: wherever a format is offered the facts must
agree, and every difference carries a recorded reason. t-1295 measured the gap -
Streamlit offered six formats, the CLI menu three, and a headless `tancat run`
wrote no report at all - so a run could leave nothing to check.

These tests fail if that comes back:

- every local surface's writer set covers JSON and HTML;
- the CLI menu offers exactly the formats the package has writers for.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.report_formats import (  # noqa: E402
    OUT_OF_SCOPE_SURFACES,
    PARITY_REQUIRED,
    REPORT_FORMATS,
    SURFACE_FORMATS,
)

#: The local surfaces the owner expects at parity. CI is excluded on purpose:
#: its schema is a separate job, and its current gap is named in report_formats.
LOCAL_SURFACES = ("streamlit", "cli_menu", "headless")


def test_every_local_surface_writes_json_and_html() -> None:
    """A run with no JSON and no HTML cannot be checked after the fact."""
    missing = {
        surface: [fmt for fmt in PARITY_REQUIRED if fmt not in SURFACE_FORMATS[surface]]
        for surface in LOCAL_SURFACES
        if any(fmt not in SURFACE_FORMATS[surface] for fmt in PARITY_REQUIRED)
    }
    assert missing == {}, f"surface(s) without a required format: {missing}"


def test_every_declared_surface_uses_known_formats() -> None:
    unknown = {
        surface: [fmt for fmt in formats if fmt not in REPORT_FORMATS]
        for surface, formats in SURFACE_FORMATS.items()
        if any(fmt not in REPORT_FORMATS for fmt in formats)
    }
    assert unknown == {}, f"format(s) with no writer: {unknown}"


def test_the_cli_menu_offers_every_format_the_package_can_write() -> None:
    """The menu's format list equals the set of writers, so a new writer shows up."""
    assert set(SURFACE_FORMATS["cli_menu"]) == set(REPORT_FORMATS)


def test_the_ci_gap_is_recorded_not_silently_dropped() -> None:
    assert "ci_action" in OUT_OF_SCOPE_SURFACES
    assert "report.json" in OUT_OF_SCOPE_SURFACES["ci_action"]


def test_a_headless_run_writes_the_json_and_html_reports(tmp_path: Path) -> None:
    """The hole t-1295 measured: `tancat run` left no report to check."""
    from src.cli.headless import _write_reports

    paths = _write_reports(
        str(tmp_path / "test_eval_001.py"),
        "1. Backpack in cart",
        "def test_01_backpack(page):\n    pass\n",
    )

    assert paths.get("json"), "no JSON report written"
    assert paths.get("html"), "no HTML report written"
    assert Path(paths["json"]).is_file()
    assert Path(paths["html"]).is_file()
    assert Path(paths["json"]).name == "report_local.json"
    assert Path(paths["html"]).name == "report.html"


def test_the_table_matches_the_writers_the_package_actually_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Derived from the code, not from the table (j-0286 review gap 3).

    A writer added without a table entry fails here. The evidence exports are
    found by introspection (every ``export_*`` in src.evidence_export), and the
    report formats by running the real report service into a temp package and
    reading the file names it wrote - so a new file from the service is caught
    too, not just a new function name.
    """
    import src.evidence_export as evidence_export
    from src.pipeline_report_service import PipelineReportService
    from src.pytest_output_parser import RunResult
    from src.usage_meter import UsageMeter

    # Jira is the one metered export (Phase 6e); on a spent free tier the service
    # legitimately refuses to write report_jira.md. Allow it here, so the check
    # measures the WRITERS the package has, not this machine's export budget.
    monkeypatch.setattr(UsageMeter, "assert_export_allowed", lambda self, kind: None)

    found: set[str] = set()
    for name in dir(evidence_export):
        if name.startswith("export_") and callable(getattr(evidence_export, name)):
            key = name.removeprefix("export_")
            found.add({"junit_xml": "junit"}.get(key, key))

    package = tmp_path / "pkg"
    PipelineReportService().build_reports(
        criteria_text="1. Backpack in cart",
        generated_code="def test_01(page):\n    pass\n",
        run_result=RunResult(),
        package_dir=str(package),
        jira_project_key="TEST",
    )
    by_name = {
        "report_local.md": "markdown",
        "report_local.json": "json",
        "report.html": "html",
        "report_jira.md": "jira",
    }
    unknown: list[str] = []
    for path in package.iterdir():
        file_key: str | None = by_name.get(path.name)
        if file_key is None:
            unknown.append(path.name)
            continue
        found.add(file_key)

    assert unknown == [], f"the report service writes file(s) the table does not name: {unknown}"
    assert found == set(REPORT_FORMATS), (
        f"writers in code {sorted(found)} != table {sorted(REPORT_FORMATS)} - "
        "add the format to src/report_formats.py (and to the menu), or remove it from the table"
    )


# ---------------------------------------------------------------------------
# The wiring, not just the writer (j-0286 review gap 2)
# ---------------------------------------------------------------------------


def _fake_pipeline(package: Path) -> Callable[..., Awaitable[None]]:
    """A pipeline stand-in: saves a test file and fills the session, no model."""

    async def run(**kwargs: Any) -> None:
        session: Any = kwargs["session"]
        saved = package / "test_eval_001.py"
        saved.write_text("def test_01_backpack(page):\n    pass\n", encoding="utf-8")
        session.set("pipeline_saved_path", str(saved))
        session.set("pipeline_manifest_path", str(package / "manifest.json"))
        session.set("pipeline_results", "def test_01_backpack(page):\n    pass\n")
        session.set("pipeline_conditions", ["1. Backpack in cart"])
        session.set("pipeline_criteria", "1. Backpack in cart")

    return run


def test_run_writes_the_reports_and_puts_their_paths_in_the_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The regression nothing would catch: run() never calling the writer."""
    import json

    import src.cli.headless as headless

    package = tmp_path / "pkg"
    package.mkdir()
    monkeypatch.setattr(headless, "_run_pipeline_async", _fake_pipeline(package))
    monkeypatch.setattr(headless, "init_storage", lambda **kwargs: None)

    args = headless.build_parser().parse_args(
        ["--story", "add one item to the cart", "--url", "http://localhost:8080", "--json"]
    )
    assert headless.run(args) == 0

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert set(payload["reports"]) >= {"json", "html"}
    for key in ("json", "html"):
        assert Path(payload["reports"][key]).is_file(), f"{key} path in payload does not exist"
    assert (package / "report_local.json").is_file()
    assert (package / "report.html").is_file()


def test_a_report_failure_does_not_fail_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    import src.cli.headless as headless
    from src.pipeline_report_service import PipelineReportService

    package = tmp_path / "pkg"
    package.mkdir()
    monkeypatch.setattr(headless, "_run_pipeline_async", _fake_pipeline(package))
    monkeypatch.setattr(headless, "init_storage", lambda **kwargs: None)

    def boom(self: object, **kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(PipelineReportService, "build_reports", boom)

    args = headless.build_parser().parse_args(
        ["--story", "add one item to the cart", "--url", "http://localhost:8080", "--json"]
    )
    assert headless.run(args) == 0

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["reports"] == {}


# ---------------------------------------------------------------------------
# The menu's evidence exports are not empty (j-0286 blocker)
# ---------------------------------------------------------------------------


def test_the_menu_exports_build_the_index_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unbuilt EvidenceIndex() is why the three exports came out empty."""
    import src.cli.pipeline_runner as pipeline_runner
    import src.evidence_index as evidence_index

    built: list[int] = []

    class FakeIndex:
        def build_or_refresh(self) -> int:
            built.append(1)
            return 1

    monkeypatch.setattr(evidence_index, "EvidenceIndex", FakeIndex)
    package = tmp_path / "pkg"
    (package / "evidence").mkdir(parents=True)

    pipeline_runner._export_evidence_formats(package)

    assert built == [1], "the exports opened the index without refreshing it"


def test_the_menu_exports_are_not_empty_for_a_package_with_evidence(tmp_path: Path) -> None:
    """Header-only CSV / empty NDJSON / 0-test JUnit can no longer pass."""
    import json

    from src.cli.pipeline_runner import _export_evidence_formats
    from src.evidence_index import EvidenceIndex
    from src.sqlite_persistence import SQLitePersistence

    base = tmp_path / "generated_tests"
    package = base / "test_pkg_2026-11-05"
    evidence = package / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "test_cart[chromium].evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "test": {
                    "name": "test_cart[chromium]",
                    "condition_ref": "TC01.06",
                    "story_ref": "S06",
                    "status": "failed",
                    "duration_s": 1.5,
                },
                "page": {"url": "https://automationexercise.com/view_cart"},
                "steps": [{"step": 1, "type": "click", "label": "add to cart"}],
                "page_expectations": [],
            }
        ),
        encoding="utf-8",
    )

    index = EvidenceIndex(db=SQLitePersistence(db_path=tmp_path / "idx.sqlite"))
    assert index.build_or_refresh(base_dir=base) == 1

    written = _export_evidence_formats(package, index=index)

    assert set(written) == {"csv", "ndjson", "junit"}
    csv_text = (package / "report_evidence.csv").read_text(encoding="utf-8")
    assert "test_cart[chromium]" in csv_text
    assert len(csv_text.strip().splitlines()) >= 2  # header AND a row
    ndjson_lines = (package / "report_evidence.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert ndjson_lines, "NDJSON export is empty"
    xml_text = (package / "report_evidence.xml").read_text(encoding="utf-8")
    assert "<testcase" in xml_text
