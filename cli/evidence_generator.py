"""
Evidence Generator for AI Playwright Test Generator.

This module handles screenshot capture and evidence generation for:
- Test execution verification
- Bug reproduction evidence
- Visual regression testing
- Test documentation
"""

import io
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cli.config import CaptureLevel
from src.analyzer import AnalyzedTestCase
from src.config import (
    CAPTURE_LEVEL,
    NAMING_CONVENTION,
    SCREENSHOT_DIR,
    STORAGE_MODE,
    ScreenshotNaming,
)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image: Any = None  # type: ignore[no-redef]


@dataclass
class ScreenshotMetadata:
    """Metadata for a single screenshot."""

    test_case_id: str
    timestamp: str
    file_path: str
    capture_stage: str
    description: str = ""
    file_size: int = 0
    dimensions: tuple[int, int] = (0, 0)

    def to_dict(self) -> dict:
        return {
            "test_case_id": self.test_case_id,
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "capture_stage": self.capture_stage,
            "description": self.description,
            "file_size": self.file_size,
            "dimensions": list(self.dimensions),
        }


@dataclass
class EvidenceCollection:
    """Container for collected test evidence."""

    screenshots: list[ScreenshotMetadata] = field(default_factory=list)
    videos: list[dict] = field(default_factory=list)
    console_logs: list[dict] = field(default_factory=list)
    network_requests: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_screenshots": len(self.screenshots),
            "total_videos": len(self.videos),
            "total_log_entries": len(self.console_logs) + len(self.network_requests),
            "screenshots": [s.to_dict() for s in self.screenshots],
            "videos": self.videos,
            "log_entries": self.console_logs,
            "network_requests": self.network_requests,
            "collection_timestamp": datetime.now().isoformat(),
        }


class ScreenshotCapturer:
    """Handle screenshot capture and storage."""

    def __init__(self) -> None:
        self.storage_mode = STORAGE_MODE
        self.naming_convention = NAMING_CONVENTION
        self.capture_level = CAPTURE_LEVEL
        self.screenshots_dir = SCREENSHOT_DIR
        self.screenshot_count = 0
        self.metadata: list[ScreenshotMetadata] = []
        os.makedirs(self.screenshots_dir, exist_ok=True)

    def capture(
        self, page: Any, test_case: AnalyzedTestCase, capture_stage: str, step_description: str = ""
    ) -> str | None:
        """Capture screenshot from page."""
        try:
            screenshot_bytes = page.screenshot(full_page=True)
            filename = self._generate_filename(test_case, capture_stage, step_description)
            filepath = self._save_screenshot(screenshot_bytes, filename, test_case.title)
            file_size = os.path.getsize(filepath)
            screenshot_metadata = ScreenshotMetadata(
                test_case_id=self._generate_case_id(test_case.title),
                timestamp=datetime.now().isoformat(),
                file_path=filepath,
                capture_stage=capture_stage,
                description=step_description or f"{capture_stage} - {test_case.title}",
                file_size=file_size,
                dimensions=self._get_screenshot_dimensions(screenshot_bytes),
            )
            self.metadata.append(screenshot_metadata)
            return filepath

        except Exception as e:
            print(f"Screenshot capture failed: {e}")
            return None

    def _generate_filename(self, test_case: AnalyzedTestCase, capture_stage: str, step_description: str) -> str:
        """Generate screenshot filename based on naming convention."""
        base = test_case.title.lower().replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d")
        self.screenshot_count += 1
        case_number = f"{self.screenshot_count:03d}"

        convention = getattr(self, "naming_convention", ScreenshotNaming.HYBRID)

        if convention == ScreenshotNaming.SEQUENTIAL:
            filename = f"{capture_stage}_{case_number}.png"
        elif convention == ScreenshotNaming.DESCRIPTIVE:
            filename = f"{base}_{timestamp}.png"
        else:
            descriptive_part = base[:20].rstrip("_")
            filename = f"{descriptive_part}_{case_number}_{timestamp}.png"

        return filename

    def _save_screenshot(self, screenshot_bytes: bytes, filename: str, test_title: str) -> str:
        """Save screenshot to disk with proper organization."""
        safe_title = re.sub(r"[^\w\-_\.]", "_", test_title[:30]).lower()

        if self.storage_mode == "organized":
            test_type = safe_title.split("_")[0]
            date_dir = datetime.now().strftime("%Y%m%d")
            path = os.path.join(self.screenshots_dir, test_type, date_dir, filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)

        elif self.storage_mode == "flatten":
            path = os.path.join(self.screenshots_dir, filename)

        else:
            abs_path = os.path.join(self.screenshots_dir, safe_title, filename)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            path = abs_path

        with open(path, "wb") as f:
            f.write(screenshot_bytes)

        return path

    def _get_screenshot_dimensions(self, screenshot_bytes: bytes) -> tuple:
        """Extract dimensions from screenshot bytes."""
        if not PIL_AVAILABLE:
            return (0, 0)
        try:
            img = Image.open(io.BytesIO(screenshot_bytes))
            return img.size
        except Exception:
            return (0, 0)

    def _generate_case_id(self, title: str) -> str:
        """Generate unique test case ID."""
        safe_title = re.sub(r"[^\w]", "_", title.lower().strip()[:30])
        return f"test_{safe_title}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


class EvidenceGenerator:
    """Generate comprehensive test evidence package."""

    def __init__(self, capture_level: CaptureLevel | None = None) -> None:
        self.capture_level = capture_level or CAPTURE_LEVEL
        self.capturer = ScreenshotCapturer()
        self.evidence: EvidenceCollection = EvidenceCollection()
        self.test_cases_processed = 0

    def capture_test_evidence(
        self, page: Any, test_case: AnalyzedTestCase, capture_stage: str = "step", step_description: str = ""
    ) -> str | None:
        """Capture evidence for a specific test stage."""
        should_capture = self._should_capture(capture_stage)
        if not should_capture:
            return None

        filepath = self.capturer.capture(page, test_case, capture_stage, step_description)

        if filepath:
            self.evidence.screenshots.append(
                ScreenshotMetadata(
                    test_case_id=self.capturer._generate_case_id(test_case.title),
                    timestamp=datetime.now().isoformat(),
                    file_path=filepath,
                    capture_stage=capture_stage,
                    description=step_description or f"{capture_stage} - {test_case.title}",
                    file_size=os.path.getsize(filepath),
                    dimensions=self.capturer._get_screenshot_dimensions(page.screenshot(full_page=True)),
                )
            )

        return filepath

    def _should_capture(self, capture_stage: str) -> bool:
        """Determine if capture is needed based on capture level."""
        if self.capture_level == CaptureLevel.BASIC:
            return capture_stage in ["entry", "outcome"]
        elif self.capture_level == CaptureLevel.STANDARD:
            return capture_stage in ["entry", "step", "outcome"]
        elif self.capture_level == CaptureLevel.THOROUGH:
            return True
        return True

    def generate_evidence_summary(self) -> dict:
        """Generate a summary of collected evidence."""
        return self.evidence.to_dict()

    def generate_evidence(self) -> None:
        """Generate evidence package."""
        print(f"   Generated {len(self.evidence.screenshots)} screenshots")

    def create_visual_report(self, output_path: str, test_cases: list[AnalyzedTestCase]) -> str:
        """Create a visual HTML report of test evidence."""
        html_content = self._generate_html_report(test_cases)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return output_path

    def _generate_html_report(self, test_cases: list[AnalyzedTestCase]) -> str:
        """Generate HTML report content."""
        html_parts = [
            """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Evidence Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        .test-case {
            background: white;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .test-header {
            background: #007bff;
            color: white;
            padding: 15px;
        }
        .test-body {
            padding: 15px;
        }
        .screenshot {
            max-width: 100%;
            border-radius: 4px;
            margin: 10px 0;
            border: 1px solid #ddd;
        }
        .metadata {
            color: #666;
            font-size: 14px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Test Evidence Report</h1>
        <p>Generated: """
            + datetime.now().isoformat()
            + """</p>
"""
        ]

        for case in test_cases:
            html_parts.extend(
                [
                    f'''
        <div class="test-case" id="{self.capturer._generate_case_id(case.title)}">
            <div class="test-header">
                <h2>{case.title}</h2>
                <div class="metadata">
                    Type: {case.test_type or "General"} |
                    Complexity: {case.estimated_complexity} |
                    Confidence: {case.analysis_confidence:.1%}
                </div>
            </div>
            <div class="test-body">
                <p><strong>Description:</strong> {case.description}</p>
                <p><strong>Expected Outcome:</strong> {case.expected_outcome}</p>
                <div class="metadata">
                    Actions: {", ".join(case.identified_actions) or "None"} |
                    Expectations: {", ".join(case.identified_expectations) or "None"}
                </div>
            </div>
        </div>
'''
                ]
            )

        html_parts.extend(
            [
                """
    </div>
</body>
</html>"""
            ]
        )

        return "".join(html_parts)

    def create_evidence_zip(self, output_path: str) -> str:
        """Create a zip archive of evidence files."""
        import zipfile

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for screenshot in self.evidence.screenshots:
                rel_path = os.path.relpath(screenshot.file_path)
                zipf.write(screenshot.file_path, rel_path)

            summary_json = os.path.join(self.capturer.screenshots_dir, "evidence_summary.json")
            with open(summary_json, "w") as f:
                import json

                json.dump(self.generate_evidence_summary(), f, indent=2)
            zipf.write(summary_json, "evidence_summary.json")

        return output_path


class BugEvidenceGenerator:
    """Generate evidence for bug reporting."""

    def __init__(self) -> None:
        self.bug_evidence: list[dict] = []
        self.capturer = ScreenshotCapturer()

    def capture_bug_evidence(self, page: Any, description: str) -> dict:
        """Capture evidence for a bug reproduction."""
        evidence: dict = {
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "screenshot": None,
            "url": getattr(page, "url", "N/A"),
            "console_logs": [],
            "network_errors": [],
        }

        try:
            screenshot_path = self.capturer.capture(
                page,
                AnalyzedTestCase(
                    title="Bug_Report",
                    description=description,
                    preconditions=[],
                    test_data={},
                    expected_outcome="Bug reproduction",
                ),
                capture_stage="bug",
            )
            evidence["screenshot"] = screenshot_path
        except Exception:
            pass

        self.bug_evidence.append(evidence)
        return evidence

    def generate_bug_report(self, output_path: str) -> str:
        """Generate a bug report document."""
        lines = [
            "=" * 60,
            "BUG REPORT - AI Generated Evidence",
            "=" * 60,
            f"Generated: {datetime.now().isoformat()}",
            "",
        ]

        for i, bug in enumerate(self.bug_evidence, 1):
            lines.extend(
                [
                    f"--- Bug #{i} ---",
                    f"Description: {bug['description']}",
                    f"Timestamp: {bug['timestamp']}",
                    f"URL at time of bug: {bug['url']}",
                    f"Screenshot: {bug['screenshot'] or 'N/A'}",
                    "",
                ]
            )

        lines.append("=" * 60)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path


def capture_screenshot(page: Any, test_case: AnalyzedTestCase, capture_stage: str = "step") -> str | None:
    """Capture a single screenshot."""
    generator = EvidenceGenerator()
    return generator.capture_test_evidence(page, test_case, capture_stage)


def generate_test_evidence(test_cases: list[AnalyzedTestCase], output_path: str) -> str:
    """Generate comprehensive evidence report."""
    generator = EvidenceGenerator()
    return generator.create_visual_report(output_path, test_cases)
