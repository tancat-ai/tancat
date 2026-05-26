"""Unit tests for the LLM client module.

Tests verify prompt formatting, response parsing, and error handling.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.llm_client import LLMClient
from src.llm_providers import ChatCompletion


class TestLLMClientInitialization:
    """Tests for LLMClient initialization and configuration."""

    def test_client_initialization_with_custom_model(self) -> None:
        """Verify client initializes with custom model name."""
        client = LLMClient(model="custom-model")
        assert client.model == "custom-model"

    def test_client_uses_session_model_when_explicit_model_not_provided(self) -> None:
        """Verify session-selected model is reused by later implicit clients."""
        LLMClient.set_session_provider("lm-studio", "http://localhost:1234", "session-model")
        try:
            client = LLMClient(provider_name="lm-studio")
            assert client.model == "session-model"
        finally:
            LLMClient._session_provider = None
            LLMClient._session_base_url = None
            LLMClient._session_model = None

    @patch("src.llm_client.auto_detect_provider")
    def test_openai_local_uses_available_model_instead_of_cloud_default(
        self,
        mock_auto_detect_provider: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify local OpenAI-compatible servers do not fall back to gpt-4o."""
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        mock_provider = MagicMock()
        mock_provider.provider_name = "openai-local"
        mock_provider.list_models.return_value = ["local-qwen"]
        mock_auto_detect_provider.return_value = mock_provider

        client = LLMClient()

        assert client.model == "local-qwen"


class TestOllamaProviderIntegration:
    """Tests for the Ollama provider wrapper using the official Ollama client."""

    @patch("httpx.Client")
    def test_uses_official_ollama_client(self, mock_client_class: MagicMock) -> None:
        """Verify the provider uses httpx to call Ollama."""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        # The implementation uses response.json()
        mock_response.json.return_value = {
            "message": {"content": "generated code"},
            "model": "qwen3.5:9b",
            "eval_count": 15,  # simplified
        }
        # We need to simulate the response for /api/chat
        mock_instance.post.return_value = mock_response
        mock_client_class.return_value = mock_instance

        from src.llm_providers import ChatMessage, OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")
        result = provider.complete([ChatMessage(role="user", content="Say hello")], model="qwen3.5:9b")

        mock_instance.post.assert_called_once()
        assert result.content == "generated code"
        assert result.model == "qwen3.5:9b"

    def test_client_uses_env_var_when_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify client uses OLLAMA_MODEL environment variable."""
        monkeypatch.setenv("OLLAMA_MODEL", "env-model")
        client = LLMClient(provider_name="ollama")
        assert client.model == "env-model"

    def test_client_uses_default_model_when_no_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify client uses default model when no env var is set."""
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        client = LLMClient(provider_name="ollama")
        assert client.model == "qwen2.5:7b"

    def test_client_default_url(self) -> None:
        """Verify client uses correct default URL."""
        client = LLMClient(provider_name="ollama")
        assert client._provider.base_url == "http://localhost:11434"

    def test_ollama_list_models_uses_model_field(self) -> None:
        """Verify Ollama list_models reads model ids from the response."""
        from src.llm_providers import OllamaProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": [{"name": "qwen3.5:27b"}]}
        mock_client.get.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            provider = OllamaProvider(base_url="http://localhost:11434")
            result = provider.list_models()

        assert result == ["qwen3.5:27b"]

    def test_client_system_prompt_is_set(self) -> None:
        """Verify system prompt is properly initialized."""
        client = LLMClient()
        assert client.system_instruction is not None
        assert "Playwright" in client.system_instruction


class TestGenerateTestMethod:
    """Tests for the generate_test method."""

    def test_raises_error_on_empty_request(self) -> None:
        """Verify ValueError is raised for empty request."""
        client = LLMClient()
        with pytest.raises(ValueError) as exc_info:
            client.generate_test("")
        assert "empty" in str(exc_info.value).lower()

    @patch("src.llm_client.auto_detect_provider")
    def test_generate_test_calls_api_correctly(self, mock_auto_detect_provider: MagicMock) -> None:
        """Verify API call is made with correct payload."""
        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.provider_name = "ollama"
        mock_provider.list_models.return_value = []
        mock_provider.complete.return_value = ChatCompletion(content="test code", model="qwen3.5:35b")
        mock_auto_detect_provider.return_value = mock_provider

        client = LLMClient()
        _ = client.generate_test("test scenario")

        # Verify the provider's complete method was called
        mock_provider.complete.assert_called_once()
        call_args = mock_provider.complete.call_args
        print(f"DEBUG: call_args = {call_args}")
        assert call_args[1]["model"] == "qwen2.5:7b"  # Default model for ollama
        # Check that the prompt contains our test scenario
        messages = call_args[1]["messages"]
        assert len(messages) == 3  # system + user + assistant (added after completion)
        assert messages[1].role == "user"
        assert "test scenario" in messages[1].content

    @patch("src.llm_client.auto_detect_provider")
    def test_generate_test_returns_extracted_code(self, mock_auto_detect_provider: MagicMock) -> None:
        """Verify extracted code is returned."""
        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.provider_name = "ollama"
        mock_provider.complete.return_value = ChatCompletion(content="```python\ntest code\n```", model="qwen3.5:35b")
        mock_auto_detect_provider.return_value = mock_provider

        client = LLMClient()
        result = client.generate_test("test scenario")

        assert result == "test code"

    @patch("src.llm_client.auto_detect_provider")
    def test_generate_test_with_trailing_newline(self, mock_auto_detect_provider: MagicMock) -> None:
        """Verify code with trailing newline is handled correctly."""
        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.provider_name = "ollama"
        mock_provider.complete.return_value = ChatCompletion(content="```python\ntest code\n```", model="qwen3.5:35b")
        mock_auto_detect_provider.return_value = mock_provider

        client = LLMClient()
        result = client.generate_test("test scenario")

        assert result == "test code"

    @patch("src.llm_client.auto_detect_provider")
    def test_connection_error_handling(self, mock_auto_detect_provider: MagicMock) -> None:
        """Verify RuntimeError is raised for connection failures."""
        # Mock the provider to raise an exception
        mock_provider = MagicMock()
        mock_provider.provider_name = "ollama"
        mock_provider.complete.side_effect = Exception("Connection failed")
        mock_auto_detect_provider.return_value = mock_provider

        client = LLMClient()
        with pytest.raises(Exception) as exc_info:
            client.generate_test("test scenario")
        assert "Connection failed" in str(exc_info.value)


class TestExtractCodeMethod:
    """Tests for the _extract_code method."""

    def test_extracts_code_with_markdown_fences(self) -> None:
        """Verify code is extracted from markdown fences."""
        client = LLMClient()
        input_text = "```python\ntest code\n```"
        result = client._extract_code(input_text)
        assert result == "test code"

    def test_extracts_code_with_language_specifier(self) -> None:
        """Verify code extraction handles language specifier."""
        client = LLMClient()
        input_text = "```python\ntest code\n```"
        result = client._extract_code(input_text)
        assert result == "test code"

    def test_extracts_code_without_language(self) -> None:
        """Verify extraction works without language specifier."""
        client = LLMClient()
        input_text = "```\ntest code\n```"
        result = client._extract_code(input_text)
        assert result == "test code"

    def test_returns_text_without_fences(self) -> None:
        """Verify raw text is returned as-is when no fences."""
        client = LLMClient()
        input_text = "raw code here"
        result = client._extract_code(input_text)
        assert result == "raw code here"

    def test_removes_surrounding_whitespace(self) -> None:
        """Verify surrounding whitespace is stripped."""
        client = LLMClient()
        input_text = "\n```python\ntest code\n```\n"
        result = client._extract_code(input_text)
        assert result == "test code"

    def test_handles_extra_content_around_code(self) -> None:
        """Verify content before/after code block is handled."""
        client = LLMClient()
        input_text = "Some explanation\n\n```python\ntest code\n```\nMore text"
        result = client._extract_code(input_text)
        assert result == "test code"

    def test_handles_empty_code_block(self) -> None:
        """Verify empty code blocks are handled."""
        client = LLMClient()
        input_text = "```\n```"
        result = client._extract_code(input_text)
        assert result == ""

    def test_extracts_code_after_channel_marker(self) -> None:
        """Verify channel marker artifacts are removed when extracting code."""
        client = LLMClient()
        input_text = (
            "I need to generate 5 separate test functions (one per criterion), each decorated with @pytest.mark.evidence, "
            "and each should skip since the necessary locators aren't available in the provided PAGE CONTEXT.<channel|>"
            "from playwright.sync_api import Page, expect\n\n"
            '@pytest.mark.evidence(condition_ref="AC_5", story_ref="user_story_cart_flow")\n'
            "def test_05_complete_checkout(page: Page):\n    pass"
        )
        result = client._extract_code(input_text)
        assert result.startswith("from playwright.sync_api import Page, expect")
        assert "def test_05_complete_checkout" in result

    def test_extracts_code_ignoring_think_block_with_import_mentions(self) -> None:
        """Verify code extraction ignores reasoning blocks that mention imports."""
        client = LLMClient()
        input_text = (
            "<think>\n"
            'I am debating whether to include "import pytest" in generated code.\n'
            "</think>\n\n"
            "from playwright.sync_api import Page, expect\n"
            "import pytest\n\n"
            '@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")\n'
            "def test_example(page: Page, evidence_tracker) -> None:\n"
            "    pass\n"
        )
        result = client._extract_code(input_text)
        assert result.startswith("from playwright.sync_api import Page, expect")
        assert 'I am debating whether to include "import pytest"' not in result


class TestSystemPromptContent:
    """Tests for verifying system prompt content and quality."""

    def test_system_prompt_contains_playwright_import(self) -> None:
        """Verify system prompt instructs correct import."""
        client = LLMClient()
        assert "playwright" in client.system_instruction.lower()

    def test_system_prompt_includes_screenshot_instructions(self) -> None:
        """Verify system prompt includes screenshot instructions."""
        client = LLMClient()
        assert "screenshot" in client.system_instruction.lower()

    def test_system_prompt_uses_sync_api(self) -> None:
        """Verify system prompt specifies sync API usage (pytest-playwright standard)."""
        client = LLMClient()
        assert "sync_api" in client.system_instruction.lower()
        # async_playwright appears only in a "DO NOT use" instruction — not as an instruction to use it
        assert "do not use asyncio, async def, or async_playwright" in client.system_instruction.lower()

    def test_system_prompt_includes_pytest_import_when_needed(self) -> None:
        """Verify system prompt explicitly allows pytest imports for decorators and skips."""
        client = LLMClient()
        assert "pytest" in client.system_instruction.lower()
        assert "include `import pytest`" in client.system_instruction.lower()


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @patch("src.llm_client.auto_detect_provider")
    def test_connection_error_message(self, mock_auto_detect_provider: MagicMock) -> None:
        """Verify helpful error message for connection failures."""
        # Mock the provider to raise an exception
        mock_provider = MagicMock()
        mock_provider.provider_name = "ollama"
        mock_provider.complete.side_effect = Exception("Connection refused")
        mock_auto_detect_provider.return_value = mock_provider

        client = LLMClient()
        with pytest.raises(Exception) as exc_info:
            client.generate_test("test")
        assert "Connection refused" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
