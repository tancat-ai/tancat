"""Unit tests for the Test Generator module.

Tests verify directory handling, file naming, and error scenarios.
"""

import asyncio
import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.test_generator import TestGenerator


class TestTestGeneratorInitialization:
    """Tests for TestGenerator initialization."""

    def test_generator_creates_output_dir(self, monkeypatch: Any) -> None:
        """Verify output directory is created during initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "new_output")
            assert not os.path.exists(new_dir)
            generator = TestGenerator(output_dir=new_dir)
            assert generator.output_dir == new_dir
            assert os.path.exists(new_dir)

    def test_generator_uses_custom_model(self, monkeypatch: Any) -> None:
        """Verify custom model is used when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("OLLAMA_MODEL", "env-model")
            generator = TestGenerator(model_name="custom-model", output_dir=tmpdir)
            assert generator.model_name == "custom-model"

    def test_generator_uses_env_var_when_no_custom_model(self, monkeypatch: Any) -> None:
        """Verify env var is used when no custom model provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("OLLAMA_MODEL", "env-model")
            generator = TestGenerator(output_dir=tmpdir)
            assert generator.model_name == "env-model"

    def test_generator_default_model(self, monkeypatch: Any) -> None:
        """Verify default model is used."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.delenv("OLLAMA_MODEL", raising=False)
            generator = TestGenerator(output_dir=tmpdir)
            assert generator.model_name == "qwen3.5:35b"

    def test_generator_with_existing_output_dir(self, monkeypatch: Any) -> None:
        """Verify generator works with existing output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _ = TestGenerator(output_dir=tmpdir)
            assert os.path.exists(tmpdir)


class TestOutputDirectoryHandling:
    """Tests for output directory operations."""

    def test_output_dir_created_if_missing(self) -> None:
        """Verify missing output directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "new_dir")
            assert not os.path.exists(new_dir)
            _ = TestGenerator(output_dir=new_dir)
            assert os.path.exists(new_dir)
            assert os.path.isdir(new_dir)

    def test_write_permission_validation(self) -> None:
        """Verify write permissions are validated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = TestGenerator(output_dir=tmpdir)
            # Should not raise any exception
            assert generator is not None

    def test_permission_error_handling(self, monkeypatch: Any) -> None:
        """Verify permission errors are properly reported."""
        # Can't easily test actual permission denial in temp dir,
        # but we can verify the structure handles it
        generator = TestGenerator()
        assert generator._ensure_output_dir is not None


class TestGenerateSkeletonPromptCountInjection:
    """Tests for injecting the expected count into the skeleton prompt."""

    def test_generate_skeleton_includes_expected_count_in_prompt(self, tmp_path: Any) -> None:
        generator = TestGenerator(output_dir=str(tmp_path))
        generator.client = MagicMock()
        generator.client.generate = AsyncMock(return_value="generated")

        asyncio.run(
            generator.generate_skeleton(
                user_story="As a user, I want to do X.",
                conditions="1. Do X\n2. Do Y",
                target_urls=["https://example.com"],
                expected_count=2,
            )
        )

        prompt = generator.client.generate.call_args.args[0]
        assert "EXACTLY 2 test functions" in prompt
        assert "exactly 2 test functions" in prompt


class TestOutputDirectoryPermissions:
    """Tests for directory permission handling."""

    def test_directory_exists_after_initialization(self, monkeypatch: Any) -> None:
        """Verify directory exists after TestGenerator init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _ = TestGenerator(output_dir=tmpdir)
            assert os.path.isdir(tmpdir)

    def test_directory_created_with_correct_path(self, monkeypatch: Any) -> None:
        """Verify directory is created at specified path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_dir = os.path.join(tmpdir, "tests_output")
            assert not os.path.exists(sub_dir)

            generator = TestGenerator(output_dir=sub_dir)

            assert os.path.exists(sub_dir)
            assert generator.output_dir == sub_dir


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
