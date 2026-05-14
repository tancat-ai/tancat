"""Provider-aware LLM client used by both Streamlit and test helpers."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from src.llm_providers import (
    ChatCompletion,
    ChatMessage,
    auto_detect_provider,
    create_provider_from_env,
    get_provider,
)


class LLMClient:
    """High-level client for generating Playwright code from local or remote LLMs."""

    DEFAULT_SYSTEM_INSTRUCTION = """You are an expert QA engineer and Python developer specializing in Playwright testing.

 CRITICAL REQUIREMENTS:
 1. Generate pytest sync Playwright tests only.
 2. Do not use asyncio, async def, or async_playwright.
 3. Use `from playwright.sync_api import Page, expect`.
 4. Include `import pytest` at module top when pytest decorators or pytest.skip are used.
 5. Return valid Python code only, with no markdown fences, chain-of-thought, or commentary.
 6. Include screenshot capture logic only when the prompt explicitly asks for it.
 7. Do not invent selectors when page context or placeholder rules say not to.
 """

    # Session-level provider state set by CLI/Streamlit so all fallback clients
    # use the user-selected provider instead of falling back to .env.
    _session_provider: str | None = None
    _session_base_url: str | None = None
    _session_model: str | None = None

    @classmethod
    def set_session_provider(
        cls,
        provider: str,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        """Set the active provider for all LLMClient instances created without explicit provider.

        Call this from CLI or Streamlit after the user selects a provider so that
        any fallback LLMClient() calls throughout the pipeline use the same provider.
        """
        cls._session_provider = provider
        cls._session_base_url = base_url
        cls._session_model = model

    def __init__(
        self,
        provider: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        selected_provider = provider_name or provider

        # If no explicit provider, use session-level selection (CLI/Streamlit UI choice)
        if selected_provider is None and self._session_provider is not None:
            selected_provider = self._session_provider
            if base_url is None and self._session_base_url is not None:
                base_url = self._session_base_url

        if selected_provider is not None:
            self._provider = get_provider(selected_provider, base_url=base_url, api_key=api_key)
        else:
            try:
                self._provider = auto_detect_provider()
            except ConnectionError:
                # Fallback to env if auto-detect fails
                self._provider = create_provider_from_env()

        selected_model = model
        if selected_model is None and self._session_model is not None:
            selected_model = self._session_model

        self._model = selected_model or self._get_default_model()
        self.system_instruction = self.DEFAULT_SYSTEM_INSTRUCTION
        self._conversation_history: list[ChatMessage] = []

    def _get_default_model(self) -> str:
        """Return the default model name for the configured provider."""
        # 1. Check for provider-specific environment variables first
        if self._provider.provider_name == "ollama":
            env_model = os.environ.get("OLLAMA_MODEL")
            if env_model:
                return env_model
        elif self._provider.provider_name == "lm-studio":
            env_model = os.environ.get("LM_STUDIO_MODEL")
            if env_model:
                return env_model
        elif self._provider.provider_name == "openai":
            env_model = os.environ.get("OPENAI_MODEL")
            if env_model:
                return env_model

        # 2. If no env var, try to list models and pick the first one (for local providers)
        if self._provider.provider_name in ("ollama", "lm-studio"):
            try:
                models = self.list_models(timeout=5)
                if models:
                    self._debug(f"Auto-detected model: {models[0]}")
                    return models[0]
            except Exception as e:
                self._debug(f"Failed to auto-detect model: {e}")

        # 3. Final fallbacks
        if self._provider.provider_name == "ollama":
            return "qwen2.5:7b"
        if self._provider.provider_name == "lm-studio":
            return "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
        return "gpt-4o"

    @property
    def provider_name(self) -> str:
        """Return the configured provider name."""
        return self._provider.provider_name

    @property
    def model(self) -> str:
        """Return the active model name."""
        return self._model

    @property
    def base_url(self) -> str:
        """Return the provider base URL."""
        return self._provider.base_url

    def reset_conversation(
        self,
        system_instruction: str | None = None,
        *,
        system_prompt: str | None = None,
    ) -> None:
        """Reset conversation state with a fresh system message."""
        system_text = system_prompt or system_instruction or self.system_instruction
        self._conversation_history = [ChatMessage(role="system", content=system_text)]

    def get_conversation_summary(self) -> dict[str, Any]:
        """Return lightweight debugging metadata for the current conversation."""
        return {
            "provider": self.provider_name,
            "model": self.model,
            "message_count": len(self._conversation_history),
            "system_instruction_length": len(self.system_instruction),
        }

    def list_models(self, timeout: int = 30) -> list[str]:
        """List models exposed by the current provider."""
        return self._provider.list_models(timeout=timeout)

    def normalise_code_newlines(self, code: str) -> str:
        """Apply minimal whitespace cleanup to model output."""
        if not code or not code.strip():
            return code.strip()

        lines = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        cleaned_lines = [line.rstrip() for line in lines]
        while cleaned_lines and not cleaned_lines[0].strip():
            cleaned_lines.pop(0)
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        return "\n".join(cleaned_lines)

    def _extract_code(self, raw_text: str) -> str:
        """Extract Python code from completions that may include prose or fences."""
        if not raw_text:
            return ""

        cleaned = re.sub(r"<channel\|>+", "\n", raw_text).strip()
        cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
        if "</think>" in cleaned:
            cleaned = cleaned.split("</think>")[-1]
        cleaned = cleaned.strip()

        fence_matches = re.findall(r"```(?:python)?\n(.*?)```", cleaned, re.S)
        if fence_matches:
            return "\n\n".join(m.strip() for m in fence_matches if m.strip())

        if re.match(r"^```(?:python)?\s*```$", cleaned, re.S):
            return ""

        code_start_patterns = [
            re.compile(r"(?m)^(from\s+playwright\.sync_api\s+import[^\n]*)"),
            re.compile(r"(?m)^(import\s+pytest\b[^\n]*)"),
            re.compile(r"(?m)^(@pytest\.mark[^\n]*)"),
            re.compile(r"(?m)^(def\s+test_\w+\s*\()"),
        ]
        for pattern in code_start_patterns:
            match = pattern.search(cleaned)
            if match:
                return cleaned[match.start() :].strip()

        return cleaned

    def _debug(self, message: str) -> None:
        """Print debug message if logging is enabled."""
        if os.getenv("PIPELINE_DEBUG", "").strip() == "1":
            print(f"[llm_client] {message}", flush=True)

    def _complete_sync(self, prompt: str, timeout: int = 300, system_prompt: str | None = None) -> ChatCompletion:
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        self.reset_conversation(system_prompt=system_prompt)
        self._conversation_history.append(ChatMessage(role="user", content=prompt))

        import time

        start_time = time.time()
        try:
            self._debug(f"Calling provider={self.provider_name} model={self._model} timeout={timeout}")
            completion = self._provider.complete(
                messages=self._conversation_history,
                model=self._model,
                timeout=timeout,
            )
            elapsed = time.time() - start_time
            content_len = len(completion.content) if completion.content else 0
            self._debug(f"Received completion in {elapsed:.2f}s, length={content_len} chars")

            if not completion.content or content_len < 10:
                print(f"Warning: LLM returned suspiciously short response: '{completion.content}'")

            self._conversation_history.append(ChatMessage(role="assistant", content=completion.content))
            return completion
        except Exception as e:
            elapsed = time.time() - start_time
            self._debug(f"LLM call failed after {elapsed:.2f}s: {e}")
            self._conversation_history.pop()
            raise

    async def generate(self, prompt: str, timeout: int = 600, system_prompt: str | None = None) -> str:
        """Async wrapper used by the intelligent pipeline."""
        try:
            completion = await asyncio.to_thread(self._complete_sync, prompt, timeout, system_prompt)
        except Exception as exc:
            raise RuntimeError(f"Failed to generate tests: {exc}") from exc

        cleaned = self._extract_code(completion.content)
        return self.normalise_code_newlines(cleaned)

    def generate_test(self, prompt: str, timeout: int = 300, system_prompt: str | None = None) -> str:
        """Sync generation helper retained for existing tests and utility flows."""
        try:
            completion = self._complete_sync(prompt, timeout, system_prompt)
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to generate tests: {exc}") from exc

        cleaned = self._extract_code(completion.content)
        return self.normalise_code_newlines(cleaned)

    def generate_tests(self, acceptance_criteria: list[str], timeout: int = 300) -> dict[str, Any]:
        """Generate code from a list of acceptance criteria."""
        if not acceptance_criteria:
            raise ValueError("acceptance_criteria cannot be empty")

        criteria_text = "\n".join(f"{index + 1}. {criterion}" for index, criterion in enumerate(acceptance_criteria))
        total_count = len(acceptance_criteria)
        prompt = f"""You are an expert QA engineer creating Playwright tests.

ACCEPTANCE CRITERIA ({total_count} total):
{criteria_text}

Total: {total_count} criteria

INSTRUCTIONS:
- Generate EXACTLY ONE test function per criterion
- DO NOT use async def - use pytest sync format only
- DO NOT skip, combine, or omit any criteria
- Each test must be independent and runnable standalone
"""

        completion = self._complete_sync(prompt, timeout)
        return {
            "test_code": self.normalise_code_newlines(self._extract_code(completion.content)),
            "model_used": completion.model,
            "provider_used": self.provider_name,
            "tokens_used": completion.usage or {},
        }

    def create_vision_completion(
        self,
        image_base64: str,
        prompt: str,
    ) -> str:
        """Send a vision-capable LLM an image + text prompt.

        Uses the same provider infrastructure as complete() but
        sends the image as base64 data URI in the message content.

        For ollama/lm-studio: uses chat completions with images field.
        For openai: uses chat.completions.create() with image_url content part.

        Args:
            image_base64: Base64-encoded PNG image string (without data URI prefix).
            prompt: Text prompt for the vision LLM.

        Returns:
            Text response from the vision LLM.

        Raises:
            ValueError: If the provider/model does not support vision.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        self.reset_conversation()

        # Build message content with image + text
        if self.provider_name in ("ollama", "lm-studio"):
            # Ollama format: images as base64 array in message
            ollama_content: list[dict[str, Any]] = [
                {"type": "text", "text": prompt},
            ]
            # Add image as base64 data URI
            image_data_uri = f"data:image/png;base64,{image_base64}"
            ollama_content.append({"type": "image_url", "image_url": image_data_uri})

            self._conversation_history.append(
                ChatMessage(role="user", content=ollama_content)  # type: ignore[arg-type]
            )
        else:
            # OpenAI-compatible format
            openai_content: list[dict[str, Any]] = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                        "detail": "high",
                    },
                },
                {"type": "text", "text": prompt},
            ]

            self._conversation_history.append(
                ChatMessage(role="user", content=openai_content)  # type: ignore[arg-type]
            )

        import time

        start_time = time.time()
        try:
            self._debug(f"Calling vision provider={self.provider_name} model={self._model}")
            completion = self._provider.complete(
                messages=self._conversation_history,
                model=self._model,
                timeout=120,
            )
            elapsed = time.time() - start_time
            content_len = len(completion.content) if completion.content else 0
            self._debug(f"Received vision completion in {elapsed:.2f}s, length={content_len} chars")

            if not completion.content or len(completion.content) < 10:
                print(f"Warning: Vision LLM returned suspiciously short response: '{completion.content}'")

            self._conversation_history.append(ChatMessage(role="assistant", content=completion.content))
            return completion.content or ""
        except Exception as e:
            elapsed = time.time() - start_time
            self._debug(f"Vision LLM call failed after {elapsed:.2f}s: {e}")
            self._conversation_history.pop()
            raise


def create_llm_client(provider_name: str | None = None, model: str | None = None) -> LLMClient:
    """Create an LLMClient instance."""
    return LLMClient(provider_name=provider_name, model=model)
