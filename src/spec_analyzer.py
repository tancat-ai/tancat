"""Spec Analyzer module to derive TestConditions from a test specification."""

import json
import re
from dataclasses import dataclass
from typing import Literal

from src.llm_client import LLMClient

ConditionType = Literal["happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"]
ConditionSrc = Literal["ai", "manual", "automation"]


@dataclass
class TestCondition:
    """A single verifiable condition derived from spec analysis."""

    id: str  # e.g., BC01.02
    type: ConditionType
    text: str
    expected: str
    source: str
    flagged: bool = False
    src: ConditionSrc = "ai"

    def to_dict(self) -> dict:
        """Return dict representation."""
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "expected": self.expected,
            "source": self.source,
            "flagged": self.flagged,
            "src": self.src,
        }


class SpecAnalyzer:
    """Analyzes specifications to derive explicit test conditions."""

    SYSTEM_PROMPT = """You are an expert QA Test Analyst.
Your task is to analyze the provided feature specification and derive a comprehensive list of test conditions.
You must perform four analysis steps mentally, then output a JSON array of test conditions:
1. Extract business rules (logic statements, thresholds, constraints).
2. Map boundary values (at-limit, below-limit, above-limit).
3. Surface ambiguities (spec gaps where behaviour is undefined).
4. Derive specific test conditions.

The condition types are:
- `happy_path` (valid input, all rules pass)
- `boundary` (value at exactly the rule limit and +/-1 unit either side)
- `negative` (invalid input, error path)
- `exploratory` (tester-added, not spec-derivable, e.g. stress test)
- `regression` (parameterised automation, cross-boundary combinations)
- `ambiguity` (spec gap requiring product owner clarification before sign-off)

Output ONLY valid JSON matching this schema:
[
  {
    "id": "A unique ID string like 'TC01.01'",
    "type": "happy_path|boundary|negative|exploratory|regression|ambiguity",
    "text": "Plain English description of the test condition",
    "expected": "Plain English expected result",
    "source": "The specific spec clause that drove this condition",
    "flagged": boolean (true if type is ambiguity, false otherwise),
    "src": "ai"
  }
]
No markdown fences around the JSON. No conversational text.
CRITICAL: Do NOT output trailing commas. The JSON must be strictly valid."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialize with an LLM client."""
        self.llm_client = llm_client or LLMClient()

    def analyze(self, spec_text: str) -> list[TestCondition]:
        """Analyze spec text and return list of test conditions."""
        if not spec_text or not spec_text.strip():
            return []

        prompt = f"Analyze the following specification:\n\n{spec_text}"

        try:
            # We use generate_test (or direct generation) to get the response string.
            response = self.llm_client.generate_test(prompt=prompt, system_prompt=self.SYSTEM_PROMPT, timeout=300)
            return self._parse_response(response)
        except Exception as e:
            raise RuntimeError(f"Spec analysis failed: {str(e)}") from e

    def _parse_response(self, response: str) -> list[TestCondition]:
        """Parse LLM JSON response into TestCondition objects."""
        # Clean markdown if present
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", response)
        json_str = match.group(1) if match else response
        json_str = json_str.strip()

        # Strip trailing commas that break Python's strict json parser
        json_str = re.sub(r",\s*([\]}])", r"\1", json_str)

        if not json_str:
            raise RuntimeError("LLM returned empty or whitespace response")

        try:
            data = json.loads(json_str, strict=False)
            if not isinstance(data, list):
                raise ValueError("Expected a JSON array of conditions")

            conditions = []
            for i, item in enumerate(data):
                item_dict = item if isinstance(item, dict) else {}
                ctype = item_dict.get("type", "happy_path")
                # Ensure type is valid
                if ctype not in ["happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"]:
                    ctype = "happy_path"

                conditions.append(
                    TestCondition(
                        id=item_dict.get("id", f"COND.{i + 1:02d}"),
                        type=ctype,  # type: ignore
                        text=item_dict.get("text", "Unknown condition"),
                        expected=item_dict.get("expected", "Pass"),
                        source=item_dict.get("source", "Implicit"),
                        flagged=item_dict.get("flagged", ctype == "ambiguity"),
                        src=item_dict.get("src", "ai"),
                    )
                )
            return conditions
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse LLM response as JSON: {e}\nResponse was: {json_str[:100]}...") from e
