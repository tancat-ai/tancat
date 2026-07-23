"""Validator Agent — checks skeleton output for correctness.

The validator inspects the generator's skeleton code and reports
violations.  If violations are found the graph routes back to the
Generator for a retry (up to max_retries).

Checks performed:
1. No real CSS selectors, XPath, or element locators (reuses SkeletonValidator)
2. Placeholder count ≥ 1 (non-empty skeleton)
3. Test function count matches expected_test_count (journey count check)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.skeleton_parser import SkeletonParser
from src.skeleton_validator import SkeletonValidator

if TYPE_CHECKING:
    from src.agents.state import WorkflowState

VALIDATOR_SYSTEM_PROMPT = """You are a skeleton code validator.  Inspect the skeleton below and report any problems.

Check:
1. Are ALL locators in double-brace placeholder format ({{CLICK:...}}, etc.)?
2. Is the test count correct?
3. Are there any real CSS selectors, XPath expressions, or element locators?

If the skeleton is valid, reply with "VALID".
If there are problems, list each issue on its own line, prefixed with "- "."""


class ValidatorAgent:
    """Validator Agent node: check skeleton for correctness."""

    def __init__(self, parser: SkeletonParser | None = None) -> None:
        self._parser = parser or SkeletonParser()
        self._skeleton_validator = SkeletonValidator()

    def __call__(self, state: WorkflowState) -> dict[str, list[str] | int]:
        """Validate the generated skeleton code."""
        errors: list[str] = []
        code = state.skeleton_code

        if not code or not code.strip():
            errors.append("Skeleton code is empty")
            return {"validation_errors": errors, "retry_count": state.retry_count + 1}

        # Check 1: forbidden locator patterns (CSS selectors, XPath, etc.)
        result = self._skeleton_validator.validate(code)
        if not result.is_valid:
            violations_text = "; ".join(result.violations[:5])  # first 5 for brevity
            errors.append(f"Hallucinated CSS/XPath selectors: {violations_text}")

        # Check 2: placeholder count
        placeholders = self._parser.parse_placeholders(code)
        if not placeholders:
            errors.append("Zero placeholders found — LLM wrote real selectors instead of placeholders")

        # Check 3: journey count vs expected
        try:
            code_norm = self._parser.normalise_placeholder_actions(code)
            journeys = self._parser.parse_test_journeys(code_norm)
        except Exception:
            journeys = []
            errors.append("Failed to parse test journeys from skeleton")

        if state.expected_test_count > 0 and len(journeys) != state.expected_test_count:
            errors.append(f"Journey count mismatch: expected {state.expected_test_count}, got {len(journeys)}")

        if errors:
            return {"validation_errors": errors, "retry_count": state.retry_count + 1}

        return {"validation_errors": [], "retry_count": state.retry_count}
