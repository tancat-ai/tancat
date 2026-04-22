"""Keyword-based test case analyzer (fast, no LLM required).

Extracted from ``cli/story_analyzer.py`` so that the CLI layer can
delegate to ``src/`` modules instead of maintaining duplicate logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AnalyzedTestCase:
    """Enhanced test case with keyword-analysis results."""

    title: str
    description: str
    preconditions: list[str] = field(default_factory=list)
    test_data: dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    test_type: str = "functional"
    priority: str = "medium"
    identified_actions: list[str] = field(default_factory=list)
    identified_expectations: list[str] = field(default_factory=list)
    suggested_data: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    estimated_complexity: str = "low"
    analysis_confidence: float = 1.0

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
            "identified_actions": self.identified_actions,
            "identified_expectations": self.identified_expectations,
            "suggested_data": self.suggested_data,
            "estimated_complexity": self.estimated_complexity,
            "analysis_confidence": self.analysis_confidence,
            "created_at": datetime.now().isoformat(),
        }


COMMON_PRECONDITIONS: list[str] = [
    "login",
    "authentication",
    "be logged in",
    "be authenticated",
    "create account",
    "register",
    "sign up",
    "navigate to login",
]

COMMON_POSTCONDITIONS: list[str] = ["logout", "clear form", "reset", "navigate to home", "go home"]


@dataclass
class AnalysisResult:
    """Container for analysis results."""

    analyzed_test_cases: list[AnalyzedTestCase]
    analysis_summary: dict = field(default_factory=dict)
    detected_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "analyzed_test_cases": [tc.to_dict() for tc in self.analyzed_test_cases],
            "analysis_summary": self.analysis_summary,
            "detected_patterns": self.detected_patterns,
            "analysis_timestamp": datetime.now().isoformat(),
        }


class KeywordAnalyzer:
    """Analyze text for key test elements using keywords."""

    ACTION_KEYWORDS: dict[str, list[str]] = {
        "navigation": ["click", "navigate", "go to", "open", "enter", "load"],
        "data_interaction": ["enter", "type", "fill", "input", "upload", "download"],
        "confirmation": ["confirm", "approve", "accept", "decline", "reject"],
        "search": ["search", "find", "query", "lookup"],
        "filter": ["filter", "sort", "sort by", "order by"],
        "form": ["submit", "save", "create", "update", "delete", "edit"],
    }

    EXPECTATION_KEYWORDS: dict[str, list[str]] = {
        "success": ["success", "successfully", "valid", "approved", "confirmed"],
        "error": ["error", "fail", "failed", "invalid", "unauthorized", "forbidden"],
        "redirect": ["redirect", "navigate", "go to", "go to", "move to"],
        "state_change": ["updated", "saved", "created", "deleted", "modified"],
        "visibility": ["visible", "appear", "show", "display", "highlighted"],
        "content": ["contains", "includes", "displays", "shows", "presents"],
    }

    DATA_PATTERNS: dict[str, str] = {
        "email": r"\b[\w.-]+@[\w.-]+\.\w+\b",
        "username": r"\b(?:user|account|member)\s*[:\s]*\s*\w+\b",
        "password": r"\b(?:password|pwd)\s*[:\s]*\s*\S+",
        "name": r"\b(?:full\s*name|first\s*name|last\s*name|display\s*name)\s*[:\s]*\s*[\w\s]+",
        "url": r"https?://[^\s]+",
        "id": r"\b(?:id|key)\s*[:\s]*\s*[\w-]+\b",
        "amount": r"\b(?:amount|total|price|cost)\s*[:\s]*\s*[£$€]?\d+([.,]\d+)?\b",
    }

    DATA_CATEGORIES: dict[str, list[str]] = {
        "auth": ["login", "logout", "register", "sign up", "password", "email"],
        "form": ["form", "submit", "field", "input", "entry"],
        "navigation": ["page", "screen", "view", "dashboard", "menu"],
        "data": ["data", "record", "item", "item", "resource", "object"],
        "error": ["error", "invalid", "failure", "exception", "unauthorized"],
    }

    LOW_COMPLEXITY_KEYWORDS: list[str] = ["view", "display", "show", "navigate to", "open"]
    MEDIUM_COMPLEXITY_KEYWORDS: list[str] = ["enter", "fill", "click", "submit", "select", "filter"]
    HIGH_COMPLEXITY_KEYWORDS: list[str] = [
        "validate",
        "verify",
        "assert",
        "compare",
        "calculate",
        "process",
        "integrate",
    ]

    @classmethod
    def identify_actions(cls, text: str) -> list[str]:
        """Identify action types from text."""
        text_lower = text.lower()
        actions = []

        for action_type, keywords in cls.ACTION_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                actions.append(action_type)

        if not actions and any(kw in text_lower for kw in ["click", "enter", "select", "choose"]):
            actions.append("general")

        return actions

    @classmethod
    def identify_expectations(cls, text: str) -> list[str]:
        """Identify expected outcomes from text."""
        text_lower = text.lower()
        expectations = []

        for exp_type, keywords in cls.EXPECTATION_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                expectations.append(exp_type)

        return expectations or ["result_display"]

    @classmethod
    def suggest_data(cls, text: str) -> dict[str, Any]:
        """Suggest test data based on content."""
        text_lower = text.lower()
        suggested_data: dict[str, Any] = {}

        categories = []
        for category, keywords in cls.DATA_CATEGORIES.items():
            if any(kw in text_lower for kw in keywords):
                categories.append(category)

        if "email" in text_lower or "register" in text_lower or "login" in text_lower:
            suggested_data["email"] = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com"
            suggested_data["password"] = "TestP@ssw0rd123!"

        if "form" in categories or "submit" in text_lower:
            suggested_data["form_data"] = {
                "name": "Test User",
                "email": suggested_data.get("email", "test@example.com"),
            }

        if any(kw in text_lower for kw in ["payment", "price", "cost", "amount"]):
            suggested_data["amount"] = "99.99"
            suggested_data["currency"] = "USD"

        return suggested_data if suggested_data else {}

    @classmethod
    def estimate_complexity(cls, text: str) -> str:
        """Estimate test complexity."""
        text_lower = text.lower()

        low_count = sum(1 for kw in cls.LOW_COMPLEXITY_KEYWORDS if kw in text_lower)
        medium_count = sum(1 for kw in cls.MEDIUM_COMPLEXITY_KEYWORDS if kw in text_lower)
        high_count = sum(1 for kw in cls.HIGH_COMPLEXITY_KEYWORDS if kw in text_lower)

        total = low_count + medium_count + high_count

        if total == 0:
            return "low"

        if high_count > medium_count:
            return "high"
        elif high_count > 0 or medium_count >= 3:
            return "medium"
        else:
            return "low"

    @classmethod
    def analyze_parsed(cls, parsed: object) -> AnalysisResult:
        """Analyze a ParsedInput object and return AnalysisResult.

        Args:
            parsed: ParsedInput from cli.input_parser.InputParser

        Returns:
            AnalysisResult with analyzed test cases.
        """
        analyzed_cases: list[AnalyzedTestCase] = []
        detected_patterns: list[str] = []

        if hasattr(parsed, "test_cases") and parsed.test_cases:  # type: ignore[attr-defined]
            for tc in parsed.test_cases:  # type: ignore[attr-defined]
                title = tc.title if hasattr(tc, "title") else tc.name if hasattr(tc, "name") else "Untitled"  # type: ignore[attr-defined]
                desc = tc.description if hasattr(tc, "description") else tc.step if hasattr(tc, "step") else ""  # type: ignore[attr-defined]
                analyzed = cls.analyze(title, desc)
                analyzed_cases.append(analyzed)
                detected_patterns.extend(analyzed.identified_actions)
        elif hasattr(parsed, "story"):
            story = parsed.story if hasattr(parsed, "story") else str(parsed)  # type: ignore[attr-defined]
            title = "User Story"
            analyzed = cls.analyze(title, str(story))
            analyzed_cases.append(analyzed)
            detected_patterns.extend(analyzed.identified_actions)
        else:
            story = str(parsed)
            title = "Input"
            analyzed = cls.analyze(title, story)
            analyzed_cases.append(analyzed)
            detected_patterns.extend(analyzed.identified_actions)

        return AnalysisResult(
            analyzed_test_cases=analyzed_cases,
            analysis_summary={
                "total_cases": len(analyzed_cases),
                "complexity_distribution": {},
                "requires_auth": False,
            },
            detected_patterns=detected_patterns,
        )

    @classmethod
    def analyze(cls, title: str, description: str) -> AnalyzedTestCase:
        """Analyze a single test case and return enriched result.

        Args:
            title: Test case title
            description: Test case description

        Returns:
            AnalyzedTestCase with identified actions, expectations, data, and complexity.
        """
        actions = cls.identify_actions(description)
        expectations = cls.identify_expectations(description)
        suggested_data = cls.suggest_data(description)
        complexity = cls.estimate_complexity(description)

        base_confidence = 1.0
        if not actions:
            base_confidence -= 0.2
        if not expectations:
            base_confidence -= 0.2
        if not suggested_data:
            base_confidence -= 0.1

        return AnalyzedTestCase(
            title=title,
            description=description,
            identified_actions=actions,
            identified_expectations=expectations,
            suggested_data=suggested_data,
            estimated_complexity=complexity,
            analysis_confidence=max(0.5, base_confidence),
        )
