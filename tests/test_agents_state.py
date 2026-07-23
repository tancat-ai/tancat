"""Unit tests for WorkflowState serialisation and defaults."""

from __future__ import annotations

from src.agents.state import WorkflowState


class TestWorkflowState:
    """Test WorkflowState Pydantic model."""

    def test_defaults(self) -> None:
        """All fields have sensible defaults."""
        state = WorkflowState()
        assert state.user_story == ""
        assert state.conditions == ""
        assert state.target_urls == []
        assert state.expected_test_count == 0
        assert state.raw_dom_snapshot == ""
        assert state.test_plan == ""
        assert state.skeleton_code == ""
        assert state.validation_errors == []
        assert state.retry_count == 0
        assert state.max_retries == 2

    def test_create_with_data(self) -> None:
        """Can create with full field data."""
        state = WorkflowState(
            user_story="As a user I want to log in",
            conditions="1. User enters credentials\n2. User clicks login",
            target_urls=["http://example.com/login"],
            expected_test_count=2,
            max_retries=1,
        )
        assert state.expected_test_count == 2
        assert state.max_retries == 1
        assert state.target_urls == ["http://example.com/login"]
        assert state.retry_count == 0  # default

    def test_serialise_roundtrip(self) -> None:
        """WorkflowState survives JSON roundtrip."""
        state = WorkflowState(
            user_story="test",
            conditions="1. something",
            expected_test_count=1,
            skeleton_code="def test_01(): pass",
            validation_errors=["error 1"],
            retry_count=1,
        )
        json_str = state.model_dump_json()
        restored = WorkflowState.model_validate_json(json_str)
        assert restored.user_story == "test"
        assert restored.expected_test_count == 1
        assert restored.skeleton_code == "def test_01(): pass"
        assert restored.validation_errors == ["error 1"]
        assert restored.retry_count == 1
