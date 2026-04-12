"""Test generation helpers for both direct generation and skeleton-first pipeline flows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.code_validator import validate_generated_locator_quality, validate_python_syntax
from src.file_utils import save_generated_test, slugify
from src.llm_client import LLMClient
from src.prompt_utils import build_page_context_prompt_block, get_skeleton_prompt_template


class TestGenerator:
    """Generate test code and persist it when needed."""

    __test__ = False

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        output_dir: str = "generated_tests",
        model_name: str | None = None,
        provider_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.model_name = model_name or os.environ.get("OLLAMA_MODEL", "qwen3.5:35b")
        self.generated_files: list[str] = []
        self.client = client or LLMClient(
            provider_name=provider_name,
            model=self.model_name,
            base_url=base_url,
            api_key=api_key,
        )
        self._ensure_output_dir()

    def _ensure_output_dir(self) -> None:
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    async def generate_skeleton(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
    ) -> str:
        """Generate placeholder-based skeleton code for the intelligent pipeline."""
        urls = target_urls or []
        known_urls_block = "\n".join(f"- {url}" for url in urls) if urls else "- No URLs were supplied."
        prompt = get_skeleton_prompt_template().format(
            user_story=user_story,
            conditions=conditions,
            known_urls_block=known_urls_block,
        )
        return await self.client.generate(prompt)

    async def generate_resolved_test(self, skeleton_code: str, pages_to_scrape: list[str]) -> str:
        """Return the resolved code artifact for the intelligent pipeline.

        The resolver currently performs the replacement work itself, so this method
        acts as a compatibility seam for future polishing.
        """
        _ = pages_to_scrape
        return skeleton_code

    def generate_and_save(self, request_text: str, page_context_or_base_url: Any = "") -> str:
        """Generate code directly and save it to disk."""
        base_url = page_context_or_base_url if isinstance(page_context_or_base_url, str) else ""
        prompt = request_text
        if page_context_or_base_url and not isinstance(page_context_or_base_url, str):
            prompt = f"{request_text}\n\n{build_page_context_prompt_block(page_context_or_base_url)}"

        code = self.client.generate_test(prompt)
        if not code or not code.strip():
            raise ValueError("Generated code was empty")

        syntax_error = validate_python_syntax(code)
        if syntax_error:
            raise ValueError(f"Generated code failed syntax validation: {syntax_error}")

        quality_error = validate_generated_locator_quality(code)
        if quality_error:
            raise ValueError(f"Generated code failed locator quality validation: {quality_error}")

        saved_path = save_generated_test(
            test_code=code,
            story_text=slugify(request_text[:50]),
            base_url=base_url,
            output_dir=self.output_dir,
        )
        self.generated_files.append(saved_path)
        return saved_path
