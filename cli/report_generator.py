"""
Report Generator for AI Playwright Test Generator.

This module handles generation of test reports including:
- Jira-compatible test execution reports with screenshots
- Test execution summaries
- Evidence documentation for test cases
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cli.config import ReportFormat
from src.analyzer import AnalyzedTestCase
from src.config import JIRA_PROJECT_KEY


@dataclass
class JiraTestCase:
    """Represents a test case for Jira import."""

    key: str
    summary: str
    description: str
    test_steps: str
    expected_results: str
    screenshots: list[str] = field(default_factory=list)
    execution_status: str = "UNEXECUTED"
    attachments: list[str] = field(default_factory=list)
    custom_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "summary": self.summary,
            "description": self.description,
            "test_steps": self.test_steps,
            "expected_results": self.expected_results,
            "execution_status": self.execution_status,
            "attachments": self.attachments,
            "custom_fields": self.custom_fields,
        }


@dataclass
class TestExecutionResult:
    """Result of a test execution."""

    test_case: AnalyzedTestCase
    execution_time: float
    status: str  # PASSED, FAILED, BLOCKED, SKIPPED
    failure_reason: str | None = None
    screenshots: list[str] = field(default_factory=list)
    console_logs: list[str] = field(default_factory=list)
    network_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "test_case_id": self.test_case.title,
            "execution_time": f"{self.execution_time:.2f}s",
            "status": self.status,
            "failure_reason": self.failure_reason,
            "screenshots": self.screenshots,
            "console_logs": self.console_logs,
            "network_errors": self.network_errors,
            "timestamp": datetime.now().isoformat(),
        }


class JiraReportGenerator:
    """Generate Jira-compatible test reports."""

    def __init__(self, output_dir: str = "jira_reports"):
        self.output_dir = output_dir
        self.test_cases: list[JiraTestCase] = []
        os.makedirs(output_dir, exist_ok=True)

    def create_test_case(
        self, analyzed_case: AnalyzedTestCase, screenshot_paths: list[str] | None = None
    ) -> JiraTestCase:
        """Create a Jira test case from analyzed test case."""
        screenshot_paths = screenshot_paths or []

        # Generate unique key
        key = f"{JIRA_PROJECT_KEY}-TC-{len(self.test_cases) + 1:04d}".upper()

        # Format test steps
        test_steps = self._format_test_steps(analyzed_case)

        # Format expected results
        expected_results = self._format_expected_results(analyzed_case)

        test_case = JiraTestCase(
            key=key,
            summary=analyzed_case.title,
            description=analyzed_case.description,
            test_steps=test_steps,
            expected_results=expected_results,
            screenshots=screenshot_paths,
        )

        self.test_cases.append(test_case)
        return test_case

    def _format_test_steps(self, analyzed_case: AnalyzedTestCase) -> str:
        """Format test steps for Jira."""
        lines = ["<h2>Test Steps</h2>"]

        # Add preconditions if any
        if analyzed_case.preconditions:
            lines.append("<h3>Preconditions</h3>")
            for precondition in analyzed_case.preconditions:
                lines.append(f"<ul><li>{precondition}</li></ul>")

        # Add identified actions/steps
        if analyzed_case.identified_actions:
            lines.append("<h3>Actions to Perform</h3>")
            for action in analyzed_case.identified_actions:
                lines.append(f"<ul><li>{action}</li></ul>")

        # Add test data if specified
        if analyzed_case.test_data:
            lines.append("<h3>Test Data</h3>")
            for field_name, value in analyzed_case.test_data.items():
                lines.append(f"<ul><li><strong>{field_name}:</strong> {value}</li></ul>")

        # Add suggested data from analysis
        if analyzed_case.suggested_data:
            lines.append("<h3>Suggested Data</h3>")
            for field_name, value in analyzed_case.suggested_data.items():
                lines.append(f"<ul><li><strong>{field_name}:</strong> {value}</li></ul>")

        return "\n".join(lines)

    def _format_expected_results(self, analyzed_case: AnalyzedTestCase) -> str:
        """Format expected results for Jira."""
        lines = ["<h2>Expected Results</h2>"]

        if analyzed_case.expected_outcome:
            lines.append(f"<p><strong>Expected Outcome:</strong> {analyzed_case.expected_outcome}</p>")

        if analyzed_case.identified_expectations:
            lines.append("<h3>Specific Expectations</h3>")
            for expectation in analyzed_case.identified_expectations:
                lines.append(f"<ul><li>{expectation}</li></ul>")

        return "\n".join(lines)

    def add_execution_result(self, test_case: JiraTestCase, result: TestExecutionResult) -> None:
        """Add execution result to test case."""
        test_case.execution_status = result.status
        test_case.screenshots.extend(result.screenshots)
        if result.failure_reason:
            test_case.custom_fields["failure_reason"] = result.failure_reason

    def generate_confluence_html(self, output_path: str) -> str:
        """Generate Confluence-compatible HTML report."""
        html_parts = [
            """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Test Execution Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f6f7;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 5px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        }
        h1 {
            color: #172b4d;
            border-bottom: 2px solid #36a642;
            padding-bottom: 10px;
        }
        .summary-section {
            background: #f4f5f7;
            padding: 15px;
            border-radius: 3px;
            margin-bottom: 20px;
        }
        .test-case {
            border: 1px solid #dfe1e6;
            border-radius: 3px;
            margin-bottom: 20px;
        }
        .test-header {
            background: #36a642;
            color: white;
            padding: 10px 15px;
            font-weight: bold;
        }
        .test-content {
            padding: 15px;
        }
        .step {
            margin-bottom: 10px;
            padding: 10px;
            background: #fafbfc;
            border-left: 3px solid #36a642;
        }
        .expected {
            background: #e3f2fd;
            padding: 10px;
            margin-top: 10px;
            border-left: 3px solid #2196f3;
        }
        .screenshot {
            max-width: 100%;
            max-height: 400px;
            border: 1px solid #ddd;
            border-radius: 3px;
            margin: 10px 0;
        }
        .status-passed { background: #d4edda; color: #155724; }
        .status-failed { background: #f8d7da; color: #721c24; }
        .status-blocked { background: #fff3cd; color: #856404; }
        .status-skipped { background: #e2e3e5; color: #383d41; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧪 Test Execution Report</h1>
        <p>Generated: """
            + datetime.now().isoformat()
            + """</p>
"""
        ]

        # Add summary
        passed = sum(1 for tc in self.test_cases if tc.execution_status == "PASSED")
        failed = sum(1 for tc in self.test_cases if tc.execution_status == "FAILED")
        skipped = sum(1 for tc in self.test_cases if tc.execution_status == "SKIPPED")

        html_parts.extend(
            [
                f"""
        <div class="summary-section">
            <h2>Summary</h2>
            <p><strong>Total Tests:</strong> {len(self.test_cases)}</p>
            <p class="status-passed"><strong>Passed:</strong> {passed}</p>
            <p class="status-failed"><strong>Failed:</strong> {failed}</p>
            <p class="status-skipped"><strong>Skipped:</strong> {skipped}</p>
        </div>
"""
            ]
        )

        # Add test cases
        for tc in self.test_cases:
            status_class = f"status-{tc.execution_status.lower()}"

            html_parts.extend(
                [
                    f"""
        <div class="test-case">
            <div class="test-header {status_class}">
                {tc.key} - {tc.summary}
                <span style="float:right">{tc.execution_status}</span>
            </div>
            <div class="test-content">
                <p>{tc.description}</p>
                <div class="step">{tc.test_steps}</div>
                <div class="expected">{tc.expected_results}</div>
"""
                ]
            )

            # Add screenshots
            if tc.screenshots:
                html_parts.append("<h3>Execution Screenshots</h3>")
                for screenshot in tc.screenshots:
                    screenshot_name = os.path.basename(screenshot)
                    html_parts.append(f'<img class="screenshot" src="{screenshot}" alt="{screenshot_name}">')
                    html_parts.append(f"<p><em>{screenshot_name}</em></p>")

            html_parts.append("            </div>\n        </div>\n")

        html_parts.extend(
            [
                """
    </div>
</body>
</html>"""
            ]
        )

        html_content = "".join(html_parts)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_path

    def generate_jira_xml(self, output_path: str) -> str:
        """Generate Jira XML import format."""
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<root>"]

        for tc in self.test_cases:
            screenshots_xml = "\n".join(f"<screenshot>{os.path.basename(s)}</screenshot>" for s in tc.screenshots)

            xml_parts.extend(
                [
                    f'<testCase key="{tc.key}">',
                    f"<summary>{re.sub(r'<[^>]+>', '', tc.summary)}</summary>",
                    f"<description><![CDATA[{tc.description}]]></description>",
                    f"<testSteps><![CDATA[{tc.test_steps}]]></testSteps>",
                    f"<expectedResults><![CDATA[{tc.expected_results}]]></expectedResults>",
                    f"<executionStatus>{tc.execution_status}</executionStatus>",
                    f"<attachments>{screenshots_xml}</attachments>",
                    "</testCase>",
                ]
            )

        xml_parts.append("</root>")

        xml_content = "\n".join(xml_parts)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        return output_path

    def save_test_cases(self, format: ReportFormat = ReportFormat.CONFLUENCE) -> str:
        """Save test cases in specified format."""
        if format == ReportFormat.CONFLUENCE:
            return self.generate_confluence_html(
                os.path.join(self.output_dir, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            )
        elif format == ReportFormat.JIRA_XML:
            return self.generate_jira_xml(
                os.path.join(self.output_dir, f"test_cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml")
            )
        elif format == ReportFormat.JSON:
            return self._save_json(
                os.path.join(self.output_dir, f"test_cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            )
        elif format == ReportFormat.MARKDOWN:
            return self._save_markdown(
                os.path.join(self.output_dir, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
            )
        elif format == ReportFormat.LOCAL:
            return self._save_local(
                os.path.join(self.output_dir, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            )
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _save_json(self, output_path: str) -> str:
        """Save test cases as JSON."""
        data = {"generated_at": datetime.now().isoformat(), "test_cases": [tc.to_dict() for tc in self.test_cases]}

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return output_path

    def _save_local(self, output_path: str) -> str:
        """Generate a local report with relative screenshot paths."""
        # Use the same HTML format as Confluence, but with relative paths
        return self.generate_confluence_html(output_path)

    def _save_markdown(self, output_path: str) -> str:
        """Save test cases as Markdown."""
        lines = [
            "# Test Execution Report",
            f"\nGenerated: {datetime.now().isoformat()}",
            "",
            "## Summary",
            "",
        ]

        passed = sum(1 for tc in self.test_cases if tc.execution_status == "PASSED")
        failed = sum(1 for tc in self.test_cases if tc.execution_status == "FAILED")

        lines.extend(
            [
                f"- **Total Tests:** {len(self.test_cases)}",
                f"- **Passed:** {passed}",
                f"- **Failed:** {failed}",
                "",
                "## Test Cases",
                "",
            ]
        )

        for tc in self.test_cases:
            lines.extend(
                [
                    f"### {tc.key} - {tc.summary}",
                    "",
                    f"{tc.description}",
                    "",
                    "#### Test Steps",
                    "",
                    tc.test_steps.replace("<ol><li>", "- ").replace("</li><ol><li>", "- ").replace("</li></ol>", ""),
                    "",
                    "#### Expected Results",
                    "",
                    tc.expected_results.replace("<h3>Specific Expectations</h3>", "")
                    .replace("<ul><li>", "- ")
                    .replace("</li></ul>", ""),
                    "",
                    "---",
                    "",
                ]
            )

        content = "\n".join(lines)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path
