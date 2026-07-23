"""Unit tests for ValidatorAgent."""

from __future__ import annotations

import pytest

from src.agents.state import WorkflowState
from src.agents.validator import ValidatorAgent


@pytest.fixture
def validator() -> ValidatorAgent:
    return ValidatorAgent()


class TestValidatorAgent:
    """Test ValidatorAgent with various skeleton inputs."""

    def test_valid_skeleton(self, validator: ValidatorAgent) -> None:
        """A skeleton with only placeholders passes validation."""
        state = WorkflowState(
            skeleton_code=(
                "import pytest\n"
                "from playwright.sync_api import Page\n\n"
                "@pytest.mark.evidence(condition_ref='TC-01', story_ref='S01')\n"
                "def test_01_login(page, evidence_tracker):\n"
                "    {{GOTO:login}}\n"
                "    {{FILL:username:admin}}\n"
                "    {{CLICK:login button}}\n"
                "    {{ASSERT:welcome message}}\n"
            ),
            expected_test_count=1,
        )
        result = validator(state)
        assert result["validation_errors"] == []

    def test_empty_skeleton(self, validator: ValidatorAgent) -> None:
        """Empty skeleton triggers validation error."""
        state = WorkflowState(skeleton_code="", expected_test_count=1)
        result = validator(state)
        errors: list[str] = result["validation_errors"]  # type: ignore[assignment]
        assert len(errors) >= 1
        assert any("empty" in e.lower() for e in errors)

    def test_hallucinated_css_selectors(self, validator: ValidatorAgent) -> None:
        """Skeleton with real CSS selectors fails validation."""
        state = WorkflowState(
            skeleton_code=(
                "import pytest\n"
                "from playwright.sync_api import Page\n\n"
                "def test_01_login(page):\n"
                '    page.locator("#username").fill("admin")\n'
                '    page.locator(".btn.login").click()\n'
            ),
            expected_test_count=1,
        )
        result = validator(state)
        errors2: list[str] = result["validation_errors"]  # type: ignore[assignment]
        assert len(errors2) >= 1

    def test_zero_placeholders(self, validator: ValidatorAgent) -> None:
        """Skeleton without any placeholders fails validation."""
        state = WorkflowState(
            skeleton_code=(
                "import pytest\n"
                "from playwright.sync_api import Page\n\n"
                "def test_01(page, evidence_tracker):\n"
                "    evidence_tracker.navigate('http://example.com')\n"
            ),
            expected_test_count=1,
        )
        result = validator(state)
        errors: list[str] = result["validation_errors"]  # type: ignore[assignment]
        assert len(errors) >= 1
        assert any("placeholder" in e.lower() for e in errors)

    def test_journey_count_mismatch(self, validator: ValidatorAgent) -> None:
        """Mismatch between expected and actual test count fails."""
        state = WorkflowState(
            skeleton_code=(
                "import pytest\n"
                "from playwright.sync_api import Page\n\n"
                "def test_01_one(page, evidence_tracker):\n"
                "    {{CLICK:button}}\n"
            ),
            expected_test_count=3,
        )
        result = validator(state)
        errors2: list[str] = result["validation_errors"]  # type: ignore[assignment]
        assert len(errors2) >= 1
        assert any("count" in e.lower() for e in errors2)

    def test_increments_retry_count(self, validator: ValidatorAgent) -> None:
        """Validator increments retry_count on failure."""
        state = WorkflowState(skeleton_code="", expected_test_count=1, retry_count=0)
        result = validator(state)
        assert result["retry_count"] == 1

    def test_preserves_retry_count_on_success(self, validator: ValidatorAgent) -> None:
        """Validator preserves retry_count on success (does not reset)."""
        state = WorkflowState(
            skeleton_code=("def test_01_login(page, evidence_tracker):\n    {{CLICK:button}}\n"),
            expected_test_count=1,
            retry_count=5,
        )
        result = validator(state)
        # retry_count preserved on success
        assert result["retry_count"] == 5
