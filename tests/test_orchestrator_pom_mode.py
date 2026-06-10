"""Tests for pom_mode wiring through TestOrchestrator and PipelineRunResult."""

from __future__ import annotations

from src.orchestrator import PipelineRunResult, TestOrchestrator
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.test_generator import TestGenerator


class TestPipelineRunResultPomMode:
    """PipelineRunResult carries pom_mode with backward-compatible default."""

    def test_default_pom_mode_is_false(self) -> None:
        result = PipelineRunResult()
        assert result.pom_mode is False

    def test_pom_mode_can_be_set_true(self) -> None:
        result = PipelineRunResult(pom_mode=True)
        assert result.pom_mode is True

    def test_pom_mode_explicit_false(self) -> None:
        result = PipelineRunResult(pom_mode=False)
        assert result.pom_mode is False


class TestTestOrchestratorPomMode:
    """TestOrchestrator accepts and forwards pom_mode."""

    def test_default_pom_mode_is_false(self) -> None:
        """TestOrchestrator defaults to pom_mode=False for backward compatibility."""
        orchestrator = TestOrchestrator(test_generator=TestGenerator(client=None))
        assert orchestrator._pom_mode is False

    def test_pom_mode_true_forwarded(self) -> None:
        """pom_mode=True is stored and forwarded to PlaceholderOrchestrator."""
        orchestrator = TestOrchestrator(
            test_generator=TestGenerator(client=None),
            pom_mode=True,
        )
        assert orchestrator._pom_mode is True
        assert orchestrator._placeholder_orchestrator.pom_mode is True

    def test_pom_mode_false_explicit(self) -> None:
        """Explicit pom_mode=False works."""
        orchestrator = TestOrchestrator(
            test_generator=TestGenerator(client=None),
            pom_mode=False,
        )
        assert orchestrator._pom_mode is False
        assert orchestrator._placeholder_orchestrator.pom_mode is False

    def test_placeholder_orchestrator_receives_pom_mode(self) -> None:
        """PlaceholderOrchestrator is created with the correct pom_mode."""
        for mode in (True, False):
            orchestrator = TestOrchestrator(
                test_generator=TestGenerator(client=None),
                pom_mode=mode,
            )
            assert orchestrator._placeholder_orchestrator.pom_mode is mode

    def test_last_result_carries_pom_mode_attribute(self) -> None:
        """last_result can be a PipelineRunResult with pom_mode."""
        orchestrator = TestOrchestrator(
            test_generator=TestGenerator(client=None),
            pom_mode=True,
        )
        # last_result starts as None, but the type allows PipelineRunResult
        assert orchestrator.last_result is None
        # Verify the type is correct
        orchestrator.last_result = PipelineRunResult(pom_mode=True)
        assert orchestrator.last_result.pom_mode is True


class TestPomModeBackwardCompatibility:
    """Ensure existing code without pom_mode continues to work."""

    def test_orchestrator_without_pom_mode_kwarg(self) -> None:
        """Calling TestOrchestrator without pom_mode works (backward compatible)."""
        # This mimics existing code that doesn't pass pom_mode
        orchestrator = TestOrchestrator(test_generator=TestGenerator(client=None))
        assert orchestrator._pom_mode is False
        assert orchestrator._placeholder_orchestrator.pom_mode is False

    def test_pipeline_run_result_without_pom_mode(self) -> None:
        """PipelineRunResult() without pom_mode defaults to False."""
        result = PipelineRunResult()
        assert result.pom_mode is False

    def test_placeholder_orchestrator_default(self) -> None:
        """PlaceholderOrchestrator defaults to pom_mode=False."""
        po = PlaceholderOrchestrator()
        assert po.pom_mode is False
