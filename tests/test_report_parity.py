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
from pathlib import Path

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
