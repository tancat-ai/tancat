"""Provider-aware LLM client used by both Streamlit and test helpers."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from src.llm_providers import ChatCompletion, ChatMessage, create_provider_from_env, get_provider


class LLMClient:
    """High-level client for generating Playwright code from local or remote LLMs."""

    DEFAULT_SYSTEM_INSTRUCTION = """You are an expert QA engineer and Python developer specializing in Playwright testing.

CRITICAL REQUIREMENTS:
1. Generate pytest sync Playwright tests only.
2. Do not use asyncio, async def, or async_playwright.
3. Use `from playwright.sync_api import Page, expect`.
4. Do not include `import pytest` in generated code.
5. Return valid Python code only, with no markdown fences or commentary.
6. Include screenshot capture logic only when the prompt explicitly asks for it.
7. Do not invent selectors when page context or placeholder rules say not to.
"""

    def __init__(
        self,
        provider: str | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        selected_provider = provider_name or provider
        if selected_provider is not None:
            self._provider = get_provider(selected_provider, base_url=base_url, api_key=api_key)
        else:
            self._provider = create_provider_from_env()

        self._model = model or self._get_default_model()
        self.system_instruction = self.DEFAULT_SYSTEM_INSTRUCTION
        self._conversation_history: list[ChatMessage] = []

    def _get_default_model(self) -> str:
        """Return the default model name for the configured provider."""
        if self._provider.provider_name == "ollama":
            return os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        if self._provider.provider_name == "lm-studio":
            return os.environ.get("LM_STUDIO_MODEL", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
        return os.environ.get("OPENAI_MODEL", "gpt-4o")

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

        cleaned = re.sub(r"<channel\|>+", "", raw_text).strip()
        fence_match = re.search(r"```(?:python)?\n(.+?)```", cleaned, re.S)
        if fence_match:
            return fence_match.group(1).strip()

        if re.match(r"^```(?:python)?\s*```$", cleaned, re.S):
            return ""

        import_match = re.search(r"(?:from\s+playwright\.sync_api\s+import|import\s+pytest)", cleaned)
        if import_match:
            return cleaned[import_match.start() :].strip()

        decorator_match = re.search(r"@pytest\.mark", cleaned)
        if decorator_match:
            return cleaned[decorator_match.start() :].strip()

        function_match = re.search(r"def\s+test_", cleaned)
        if function_match:
            return cleaned[function_match.start() :].strip()

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

    async def generate(self, prompt: str, timeout: int = 300, system_prompt: str | None = None) -> str:
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


def create_llm_client(provider_name: str | None = None, model: str | None = None) -> LLMClient:
    """Create an LLMClient instance."""
    return LLMClient(provider_name=provider_name, model=model)
