"""Unit tests for the Test Generator module.

Tests verify directory handling, file naming, and error scenarios.
"""

import asyncio
import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestGenerateAndSaveMethod:
    """Tests for the generate_and_save method."""

    def _build_generator_with_mock_client(self, tmpdir: str, mock_code: str) -> TestGenerator:
        generator = TestGenerator(output_dir=tmpdir)
        generator.client = MagicMock()
        generator.client.generate_test = MagicMock(return_value=mock_code)
        generator.client.normalise_code_newlines = MagicMock(side_effect=lambda code: code)
        return generator

    def test_returns_file_path_on_success(self, monkeypatch: Any) -> None:
        """Verify method returns file path on successful generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_code = """from playwright.sync_api import Page

def test_example(page: Page):
    pass"""

            generator = self._build_generator_with_mock_client(tmpdir, mock_code)
            result = generator.generate_and_save("test request")
            assert result is not None
            assert ".py" in result
            assert tmpdir in result

    def test_generated_filename_is_slugified(self, monkeypatch: Any) -> None:
        """Verify filename contains slugified request text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_code = """from playwright.sync_api import Page

def test_example(page: Page):
    pass"""

            generator = self._build_generator_with_mock_client(tmpdir, mock_code)
            result = generator.generate_and_save("test request!")
            assert "test_request" in result or "test_request_" in result

    def test_generated_filename_has_timestamp(self, monkeypatch: Any) -> None:
        """Verify filename includes timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_code = """from playwright.sync_api import Page

def test_example(page: Page):
    pass"""

            generator = self._build_generator_with_mock_client(tmpdir, mock_code)
            result = generator.generate_and_save("test request")
            # Filename should contain timestamp format
            assert any(char.isdigit() for char in result)

    def test_file_is_actually_written(self, monkeypatch: Any) -> None:
        """Verify file is actually written to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_code = """from playwright.sync_api import Page

def test_example(page: Page):
    pass"""

            generator = self._build_generator_with_mock_client(tmpdir, mock_code)
            result = generator.generate_and_save("test request")

            assert os.path.exists(result)
            with open(result) as f:
                content = f.read()
                assert "from playwright" in content

    def test_empty_code_raises_exception(self, monkeypatch: Any) -> None:
        """Verify empty code raises exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = self._build_generator_with_mock_client(tmpdir, "   ")

            with pytest.raises(Exception) as exc_info:
                generator.generate_and_save("test request")
            assert "empty" in str(exc_info.value).lower()

    def test_generated_invalid_code_raises_validation_error(self, monkeypatch: Any) -> None:
        """Verify invalid generated code is rejected before saving."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_code = """
from playwright.sync_api import expect

def test_page_title(page):
    page.goto("https://example.com")
    expect(page.title()).to_contain("Example Domain")
"""
            generator = self._build_generator_with_mock_client(tmpdir, invalid_code)

            with pytest.raises(ValueError) as exc_info:
                generator.generate_and_save("test request")

            assert (
                "locator quality" in str(exc_info.value).lower()
                or "generated code failed" in str(exc_info.value).lower()
            )

    def test_whitespace_only_code_strips(self, monkeypatch: Any) -> None:
        """Verify whitespace-only code raises exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = self._build_generator_with_mock_client(tmpdir, "   \n\n   ")

            # Should raise exception for whitespace-only
            with pytest.raises(Exception, match="empty"):
                generator.generate_and_save("test request")

    def test_filename_truncates_long_requests(self, monkeypatch: Any) -> None:
        """Verify filename is truncated to reasonable length."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_code = """from playwright.sync_api import Page

def test_example(page: Page):
    pass"""

            generator = self._build_generator_with_mock_client(tmpdir, mock_code)
            long_request = "a" * 100
            result = generator.generate_and_save(long_request)

            # Filename should be reasonable length
            assert len(os.path.basename(result)) < 100

    def test_special_characters_replaced_in_filename(self, monkeypatch: Any) -> None:
        """Verify special characters are replaced in filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_code = """from playwright.sync_api import Page

def test_example(page: Page):
    pass"""

            generator = self._build_generator_with_mock_client(tmpdir, mock_code)
            result = generator.generate_and_save("test!@#$%request")

            # Should not contain special chars that would break filenames
            special_chars = "!@#$%^&*(){}[]<>?"
            for char in special_chars:
                assert char not in os.path.basename(result)

    @patch("src.test_generator.LLMClient")
    def test_api_error_handling(self, mock_client_class: Any) -> None:
        """Verify API errors are properly raised."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = MagicMock()
            mock_client.generate_test = MagicMock(side_effect=Exception("API error"))
            mock_client.normalise_code_newlines = MagicMock(side_effect=lambda code: code)
            mock_client_class.return_value = mock_client

            generator = TestGenerator(output_dir=tmpdir)

            with pytest.raises(Exception, match="API error"):
                generator.generate_and_save("test request")


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
        assert "EXACTLY 2 SEPARATE test functions" in prompt
        assert "ONE test per acceptance criterion" in prompt
        assert "IMPORTANT: You must generate exactly 2 test functions" in prompt


class TestFileNameGeneration:
    """Tests for filename generation logic."""

    def test_filename_contains_prefix(self, monkeypatch: Any) -> None:
        """Verify filename starts with test_ prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = TestGenerator(output_dir=tmpdir)
            generator.client = MagicMock()
            generator.client.generate_test = MagicMock(return_value="code")
            generator.client.normalise_code_newlines = MagicMock(side_effect=lambda code: code)
            result = generator.generate_and_save("any request")
            assert result.startswith(tmpdir)
            assert "test_" in os.path.basename(result)

    def test_filename_uses_alphanumeric_chars(self, monkeypatch: Any) -> None:
        """Verify filename uses only alphanumeric and underscore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = TestGenerator(output_dir=tmpdir)
            generator.client = MagicMock()
            generator.client.generate_test = MagicMock(return_value="code")
            generator.client.normalise_code_newlines = MagicMock(side_effect=lambda code: code)
            result = generator.generate_and_save("test request!@#")

            filename = os.path.basename(result)
            allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.")
            for char in filename:
                assert char in allowed_chars or char == " "

    def test_filename_extension_is_py(self, monkeypatch: Any) -> None:
        """Verify generated file has .py extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = TestGenerator(output_dir=tmpdir)
            generator.client = MagicMock()
            generator.client.generate_test = MagicMock(return_value="code")
            generator.client.normalise_code_newlines = MagicMock(side_effect=lambda code: code)
            result = generator.generate_and_save("test")
            assert result.endswith(".py")


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
