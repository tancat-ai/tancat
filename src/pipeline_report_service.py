"""Build report artifacts for generated pipeline test packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.coverage_utils import build_coverage_analysis
from src.pytest_output_parser import RunResult
from src.report_utils import build_report_dicts, generate_html_report, generate_jira_report, generate_local_report


@dataclass(frozen=True)
class PipelineReportBundle:
    """Report content and saved paths for one pipeline run."""

    coverage_rows: list[dict]
    local_report: str
    jira_report: str
    html_report: str
    local_report_path: str = ""
    jira_report_path: str = ""
    html_report_path: str = ""


class PipelineReportService:
    """Create report artifacts from generated code and pytest run results."""

    def build_reports(
        self,
        *,
        criteria_text: str,
        generated_code: str,
        run_result: RunResult,
        package_dir: str = "",
    ) -> PipelineReportBundle:
        """Return generated report strings and optionally save them into the package."""
        criteria_lines = [line.strip() for line in criteria_text.splitlines() if line.strip()]
        coverage_analysis = build_coverage_analysis(criteria_lines, generated_code)
        coverage_rows = build_report_dicts(coverage_analysis, run_result, package_dir=package_dir)
        local_report = generate_local_report(coverage_rows)
        jira_report = generate_jira_report(coverage_rows)
        html_report = generate_html_report(coverage_rows)

        local_report_path = ""
        jira_report_path = ""
        html_report_path = ""
        if package_dir:
            package_path = Path(package_dir)
            package_path.mkdir(parents=True, exist_ok=True)
            local_path = package_path / "report_local.md"
            jira_path = package_path / "report_jira.md"
            html_path = package_path / "report.html"
            local_path.write_text(local_report, encoding="utf-8")
            jira_path.write_text(jira_report, encoding="utf-8")
            html_path.write_text(html_report, encoding="utf-8")
            local_report_path = str(local_path.absolute())
            jira_report_path = str(jira_path.absolute())
            html_report_path = str(html_path.absolute())

        return PipelineReportBundle(
            coverage_rows=coverage_rows,
            local_report=local_report,
            jira_report=jira_report,
            html_report=html_report,
            local_report_path=local_report_path,
            jira_report_path=jira_report_path,
            html_report_path=html_report_path,
        )
