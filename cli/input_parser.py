"""
Multi-format Input Parser for AI Playwright Test Generator.

This module provides intelligent parsing of various input formats:
- Plain text: Simple feature descriptions
- Jira copy-paste: With Issue, Summary, Description, Acceptance Criteria
- Gherkin/BDD: Feature, Scenario, Given/When/Then structure
- Bullet points: List of test steps

Designed with hybrid detection (regex-first, LLM fallback) for speed and accuracy.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cli.config import DetectionMode

EVIDENCE_DIR: str = "screenshots"


@dataclass
class TestCase:
    """Represents a single test case extracted from input."""

    title: str
    description: str
    preconditions: list[str] = field(default_factory=list)
    test_data: dict = field(default_factory=dict)
    expected_outcome: str = ""
    test_type: str = "functional"  # happy_path, validation, error_handling, edge_case
    priority: str = "medium"  # high, medium, low

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "description": self.description,
            "preconditions": self.preconditions,
            "test_data": self.test_data,
            "expected_outcome": self.expected_outcome,
            "test_type": self.test_type,
            "priority": self.priority,
            "created_at": datetime.now().isoformat(),
        }

    def to_prompt(self) -> str:
        """Convert to LLM-friendly test prompt."""
        prompt = f"Test: {self.title}\n\n"
        if self.preconditions:
            prompt += f"Preconditions: {'; '.join(self.preconditions)}\n\n"
        prompt += f"Scenario: {self.description}\n\n"
        if self.expected_outcome:
            prompt += f"Expected: {self.expected_outcome}\n"
        return prompt


@dataclass
class ParsedInput:
    """Container for parsed input with metadata."""

    test_cases: list[TestCase]
    source_format: str
    raw_input: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "test_cases": [tc.to_dict() for tc in self.test_cases],
            "source_format": self.source_format,
            "metadata": self.metadata,
            "raw_input_sample": self.raw_input[:200] + "..." if len(self.raw_input) > 200 else self.raw_input,
        }

    def save_to_json(self, output_path: str) -> str:
        """Save parsed input to JSON file."""
        data = self.to_dict()
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        return output_path


class FormatDetector:
    """Auto-detects input format using regex patterns."""

    PATTERNS: dict[str, dict[str, Any]] = {
        "jira": {
            "name": "Jira",
            "patterns": [
                re.compile(r"^(?:Issue|ID|KEY)[:\s]+[\w-]+", re.MULTILINE),
                re.compile(r"^(?:Summary|Title)[:\s]+", re.MULTILINE),
                re.compile(r"^(?:Acceptance\s+Criteria)[:\s]*$", re.MULTILINE),
                re.compile(r"^(?:Description)[:\s]*$", re.MULTILINE),
            ],
        },
        "gherkin": {
            "name": "Gherkin/BDD",
            "patterns": [
                re.compile(r"^Feature:\s+", re.MULTILINE),
                re.compile(r"^Scenario:\s+", re.MULTILINE),
                re.compile(r"^(Given|When|Then|And|But)\s+", re.MULTILINE | re.IGNORECASE),
            ],
        },
        "bullets": {
            "name": "Bullet Points",
            "patterns": [
                re.compile(r"^(?:-|\*|\d+\.)\s+\w+", re.MULTILINE),
            ],
        },
    }

    @classmethod
    def detect(cls, text: str, method: DetectionMode = DetectionMode.AUTO) -> tuple[str, float]:
        """
        Detect input format.

        Returns:
            Tuple of (format_name, confidence_score)
        """
        if method == DetectionMode.EXPLICIT:
            return ("explicit", 1.0)

        if method == DetectionMode.FAST:
            return cls._fast_detect(text)

        if method == DetectionMode.AUTO:
            # Try fast detection first
            format_name, confidence = cls._fast_detect(text)
            if confidence > 0.7:
                return format_name, confidence

            return format_name, confidence

        # Method not found - treat as plain text
        return "plain_text", 0.5

    @classmethod
    def _fast_detect(cls, text: str) -> tuple[str, float]:
        """Quick regex-based detection."""
        # Check for Jira
        jira_matches = 0
        for pattern in cls.PATTERNS["jira"]["patterns"]:
            if pattern.search(text):
                jira_matches += 1
        if jira_matches >= 3:
            return "jira", 0.9

        # Check for Gherkin
        gherkin_matches = 0
        for pattern in cls.PATTERNS["gherkin"]["patterns"]:
            if pattern.search(text):
                gherkin_matches += 1
        if gherkin_matches >= 2:
            return "gherkin", 0.9

        # Check for bullets
        bullet_matches = 0
        for pattern in cls.PATTERNS["bullets"]["patterns"]:
            if pattern.search(text):
                bullet_matches += 1
        if bullet_matches >= 3:
            return "bullets", 0.8

        # Default to plain text
        return "plain_text", 0.5


class PlainTextParser:
    """Parse plain text user stories."""

    @classmethod
    def parse(cls, text: str) -> list[TestCase]:
        """Extract test cases from plain text."""
        test_cases = []

        # Look for user story patterns
        user_story_pattern = re.compile(
            r"(?:As a|I want to|I need to|We need|Users can)\s+.*?(?:so that|in order to)\s+.*?\.?", re.IGNORECASE
        )

        for match in user_story_pattern.finditer(text):
            story = match.group(0)
            test_case = cls._extract_test_case(story)
            test_cases.append(test_case)

        # If no stories found, treat entire text as single scenario
        if not test_cases:
            test_case = TestCase(title="Main Flow", description=text.strip(), test_type="happy_path")
            test_cases.append(test_case)

        return test_cases

    @classmethod
    def _extract_test_case(cls, text: str) -> TestCase:
        """Extract a test case from a user story statement."""
        title_match = re.search(r"I want to\s+([^\s]+(?:\s+[^\s]+)*)", text, re.IGNORECASE)
        description = text.strip()
        title = title_match.group(1) if title_match else "Main Flow"

        return TestCase(title=title.strip(), description=description, test_type="happy_path")


class JiraParser:
    """Parse Jira-style copy-paste format."""

    SECTION_PATTERNS = {
        "issue": re.compile(r"^(?:Issue|ID|KEY)[:\s]+([\w-]+)", re.MULTILINE),
        "summary": re.compile(r"^(?:Summary|Title)[:\s]+(.+)", re.MULTILINE),
        "description": re.compile(
            r"^(?:Description)[:\s]*\n?\s*(.+?)(?=\n(?:Acceptance|Issue|Summary|Key)[:\s]*|$)", re.MULTILINE | re.DOTALL
        ),
        "acceptance_criteria": re.compile(
            r"^(?:Acceptance\s+Criteria)[:\s]*\n?\s*(.+?)(?=\n(?:Issue|Summary|Description|Acceptance)[:\s]*|$)",
            re.MULTILINE | re.DOTALL,
        ),
    }

    @classmethod
    def parse(cls, text: str) -> list[TestCase]:
        """Extract test cases from Jira format."""
        test_cases = []

        # Extract metadata
        issue_match = cls.SECTION_PATTERNS["issue"].search(text)
        summary = cls.SECTION_PATTERNS["summary"].search(text)
        description = cls.SECTION_PATTERNS["description"].search(text)
        acceptance = cls.SECTION_PATTERNS["acceptance_criteria"].search(text)

        metadata = {
            "issue": issue_match.group(1) if issue_match else None,
            "summary": summary.group(1).strip() if summary else None,
        }

        # Generate test cases from acceptance criteria
        if acceptance:
            ac_text = acceptance.group(1).strip()
            test_cases = cls._extract_from_acceptance_criteria(ac_text, metadata)
        elif description:
            # No acceptance criteria, generate from description
            test_case = TestCase(
                title=summary.group(1).strip() if summary else "Main Feature",
                description=description.group(1).strip(),
                test_type="happy_path",
            )
            test_cases.append(test_case)
        else:
            # Minimal Jira format, treat as single test
            test_case = TestCase(title="Main Feature", description=text.strip(), test_type="happy_path")
            test_cases.append(test_case)

        return test_cases

    @classmethod
    def _extract_from_acceptance_criteria(cls, ac_text: str, metadata: dict) -> list[TestCase]:
        """Parse acceptance criteria items."""
        test_cases = []

        # Split by lines (assuming bullet points or numbered items)
        lines = [line.strip() for line in ac_text.split("\n") if line.strip()]

        for line in lines:
            # Remove bullet points and numbering
            clean_line = re.sub(r"^[\-\*\d]+\.\s*", "", line)

            # Determine test type based on keywords
            test_type = cls._determine_test_type(clean_line)

            test_case = TestCase(
                title=cls._generate_title(clean_line, metadata),
                description=clean_line,
                test_type=test_type,
                priority=cls._determine_priority(clean_line),
            )
            test_cases.append(test_case)

        return test_cases

    @classmethod
    def _determine_test_type(cls, line: str) -> str:
        """Determine test case type from acceptance criterion."""
        line_lower = line.lower()

        if any(kw in line_lower for kw in ["error", "invalid", "fail", "exception", "unauthorized"]):
            return "error_handling"
        elif any(kw in line_lower for kw in ["valid", "successful", "successfully", "logged", "redirect"]):
            return "happy_path"
        elif any(kw in line_lower for kw in ["empty", "missing", "null", "none", "not"]):
            return "validation"
        else:
            return "functional"

    @classmethod
    def _generate_title(cls, line: str, metadata: dict) -> str:
        """Generate a concise title from the acceptance criterion."""
        # Take first few words as title
        words = line.split()[:6]
        title = " ".join(words)

        # Add issue key if available
        if metadata.get("issue"):
            title = f"[{metadata['issue']}] {title}"

        return title

    @classmethod
    def _determine_priority(cls, line: str) -> str:
        """Determine test priority from acceptance criterion."""
        line_lower = line.lower()

        if any(kw in line_lower for kw in ["required", "must", "essential", "critical"]):
            return "high"
        elif any(kw in line_lower for kw in ["should", "prefer"]):
            return "medium"
        else:
            return "low"


class GherkinParser:
    """Parse Gherkin/BDD format (Feature, Scenario, Given/When/Then)."""

    @classmethod
    def parse(cls, text: str) -> list[TestCase]:
        """Extract test cases from Gherkin format."""
        test_cases = []

        # Find all scenarios
        scenarios = cls._extract_scenarios(text)

        for scenario in scenarios:
            test_case = cls._scenario_to_test_case(scenario)
            test_cases.append(test_case)

        return test_cases

    @classmethod
    def _extract_scenarios(cls, text: str) -> list[dict]:
        """Extract all scenarios from Gherkin text."""
        scenarios = []
        pattern = re.compile(
            r"^Scenario:\s*(.+?)\n((?:[\s]*(?:Given|When|Then|And|But)\s+.*?)+?)(?=\n(?:Scenario|Feature|@|\Z))",
            re.MULTILINE,
        )

        for match in pattern.finditer(text):
            scenarios.append({"title": match.group(1).strip(), "steps": cls._extract_steps(match.group(2))})

        return scenarios

    @classmethod
    def _extract_steps(cls, steps_text: str) -> list[dict]:
        """Extract and categorize Gherkin steps."""
        steps = []
        pattern = re.compile(r"^(?:Given|When|Then|And|But)\s+(.+)", re.MULTILINE | re.IGNORECASE)

        for match in pattern.finditer(steps_text):
            step_type = match.group(0).split()[0].lower()
            step_text = match.group(1).strip()

            steps.append({"type": step_type, "text": step_text})

        return steps

    @classmethod
    def _scenario_to_test_case(cls, scenario: dict) -> TestCase:
        """Convert a scenario to a TestCase."""
        # Organize steps by type
        given = [s["text"] for s in scenario["steps"] if s["type"] == "given"]
        when = [s["text"] for s in scenario["steps"] if s["type"] == "when"]
        then = [s["text"] for s in scenario["steps"] if s["type"] == "then"]

        # Determine test type
        test_type = "happy_path"
        if any(kw in scenario["title"].lower() for kw in ["invalid", "error", "fail", "exception"]):
            test_type = "error_handling"
        elif any(kw in scenario["title"].lower() for kw in ["valid", "empty", "missing", "boundary"]):
            test_type = "validation"

        test_case = TestCase(
            title=scenario["title"],
            description=f"Given: {'. '.join(given)}\nWhen: {'. '.join(when)}\nThen: {'. '.join(then)}",
            preconditions=given or [],
            test_type=test_type,
        )

        if then:
            test_case.expected_outcome = f"Then: {'. '.join(then)}"

        return test_case


class BulletParser:
    """Parse bullet-point style acceptance criteria."""

    BULLET_REGEX = re.compile(r"^[\-\*\d]+\.\s*(.+)", re.MULTILINE)

    @classmethod
    def parse(cls, text: str) -> list[TestCase]:
        """Extract test cases from bullet-point list."""
        test_cases = []

        matches = cls.BULLET_REGEX.findall(text)

        for match in matches:
            test_case = TestCase(
                title=cls._generate_title(match), description=match.strip(), test_type=cls._determine_test_type(match)
            )
            test_cases.append(test_case)

        return test_cases

    @classmethod
    def _generate_title(cls, line: str) -> str:
        """Generate title from bullet point."""
        return line.split(".")[0][:50] if "." in line else line[:50]

    @classmethod
    def _determine_test_type(cls, line: str) -> str:
        """Determine test type from bullet point."""
        line_lower = line.lower()

        if any(kw in line_lower for kw in ["error", "invalid", "fail"]):
            return "error_handling"
        elif any(kw in line_lower for kw in ["valid", "successful", "redirect"]):
            return "happy_path"
        else:
            return "functional"


class InputParser:
    """Multi-format input parser with auto-detection and fallback."""

    def __init__(self, detection_method: DetectionMode | None = None) -> None:
        """
        Initialize parser.

        Args:
            detection_method: How to detect input format
        """
        self.detection_method: DetectionMode = detection_method or DetectionMode.AUTO

    def parse(self, text: str, explicit_format: str | None = None) -> ParsedInput:
        """
        Parse input text into standardized test cases.

        Args:
            text: Input text to parse
            explicit_format: Optional override for auto-detection

        Returns:
            ParsedInput with test cases and metadata
        """
        # Determine format
        if explicit_format:
            format_name = explicit_format
            confidence = 1.0
        else:
            format_name, confidence = FormatDetector.detect(text, self.detection_method)

        # Select appropriate parser
        test_cases = self._parse_by_format(text, format_name)

        # Create parsed input container
        parsed = ParsedInput(
            test_cases=test_cases,
            source_format=format_name,
            raw_input=text,
            metadata={
                "confidence": confidence,
                "detection_method": self.detection_method.value,
                "timestamp": datetime.now().isoformat(),
            },
        )

        return parsed

    def parse_json(self, json_str: str) -> ParsedInput:
        """Parse JSON string into test cases."""
        data: dict | list = json.loads(json_str)

        test_cases: list[TestCase] = []
        if isinstance(data, list):
            for item in data:
                test_case = TestCase(
                    title=item.get("title", "Test Case"),
                    description=item.get("description", ""),
                    preconditions=item.get("preconditions", []),
                    test_data=item.get("test_data", {}),
                    expected_outcome=item.get("expected_outcome", ""),
                    test_type=item.get("test_type", "functional"),
                    priority=item.get("priority", "medium"),
                )
                test_cases.append(test_case)
        elif isinstance(data, dict):
            # Single test case or wrapper format
            if "test_cases" in data:
                for item in data["test_cases"]:
                    test_case = TestCase(
                        title=item.get("title", "Test Case"),
                        description=item.get("description", ""),
                        preconditions=item.get("preconditions", []),
                        test_data=item.get("test_data", {}),
                        expected_outcome=item.get("expected_outcome", ""),
                        test_type=item.get("test_type", "functional"),
                        priority=item.get("priority", "medium"),
                    )
                    test_cases.append(test_case)
            else:
                test_case = TestCase(
                    title=data.get("title", "Test Case"),
                    description=data.get("description", ""),
                    preconditions=data.get("preconditions", []),
                    test_data=data.get("test_data", {}),
                    expected_outcome=data.get("expected_outcome", ""),
                    test_type=data.get("test_type", "functional"),
                    priority=data.get("priority", "medium"),
                )
                test_cases.append(test_case)

        return ParsedInput(
            test_cases=test_cases, source_format="json", raw_input=json_str, metadata={"auto_generated": True}
        )

    def _parse_by_format(self, text: str, format_name: str) -> list[TestCase]:
        """Route to appropriate parser based on format."""
        parsers: dict[str, type] = {
            "jira": JiraParser,
            "gherkin": GherkinParser,
            "bullets": BulletParser,
            "plain_text": PlainTextParser,
        }

        parser = parsers.get(format_name, PlainTextParser)
        return parser.parse(text)  # type: ignore[attr-defined]

    def parse_and_save(self, text: str, output_dir: str | None = None) -> str:
        """
        Parse input and save results to JSON file.

        Args:
            text: Input text to parse
            output_dir: Directory to save output (default: evidence directory)

        Returns:
            Path to saved JSON file
        """
        parsed = self.parse(text)

        if output_dir:
            output_path = Path(output_dir) / f"parsed_input_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            output_path = Path(EVIDENCE_DIR) / f"parsed_input_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        parsed.save_to_json(str(output_path))
        return str(output_path)


# Convenience functions for common use cases
def parse_jira_format(text: str) -> list[TestCase]:
    """Parse Jira-format input."""
    parser = InputParser()
    return parser.parse(text, explicit_format="jira").test_cases


def parse_gherkin_format(text: str) -> list[TestCase]:
    """Parse Gherkin-format input."""
    parser = InputParser()
    return parser.parse(text, explicit_format="gherkin").test_cases


def parse_bullet_format(text: str) -> list[TestCase]:
    """Parse bullet-point format input."""
    parser = InputParser()
    return parser.parse(text, explicit_format="bullets").test_cases


def parse_plain_text(text: str) -> list[TestCase]:
    """Parse plain text input."""
    parser = InputParser()
    return parser.parse(text).test_cases
