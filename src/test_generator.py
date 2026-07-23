"""Test generation helpers for both direct generation and skeleton-first pipeline flows."""

from __future__ import annotations

import os
from pathlib import Path

from src.llm_client import LLMClient
from src.prompt_utils import get_skeleton_prompt_template


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
        expected_count: int | None = None,
    ) -> str:
        """Generate placeholder-based skeleton code for the intelligent pipeline.

        When ``LANGGRAPH_ENABLED=1``, delegates to the multi-agent LangGraph
        workflow (Planner → Generator → Validator).  Otherwise uses the
        original single-call pipeline.
        """
        if os.environ.get("LANGGRAPH_ENABLED", "").strip() == "1":
            return await self._generate_skeleton_langgraph(user_story, conditions, target_urls, expected_count)
        return await self._generate_skeleton_single_call(user_story, conditions, target_urls, expected_count)

    async def _generate_skeleton_single_call(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        expected_count: int | None = None,
    ) -> str:
        """Single-call skeleton generation (original pipeline)."""
        urls = target_urls or []
        known_urls_block = "\n".join(f"- {url}" for url in urls) if urls else "- No URLs were supplied."
        count_note = (
            f"\n\nIMPORTANT: You must generate exactly {expected_count} test functions (one per criterion)."
            if expected_count
            else ""
        )
        count_label_upper = str(expected_count).upper() if expected_count is not None else "N"
        prompt = (
            get_skeleton_prompt_template(expected_count=expected_count).format(
                user_story=user_story,
                conditions=conditions,
                known_urls_block=known_urls_block,
                count_label_upper=count_label_upper,
            )
            + count_note
        )
        return await self.client.generate(prompt)

    async def _generate_skeleton_langgraph(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        expected_count: int | None = None,
    ) -> str:
        """Multi-agent LangGraph skeleton generation (Phase 1c)."""
        try:
            from src.agents.graph import SkeletonGraph  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "langgraph package is not installed. "
                "Install with: uv sync --group langgraph  "
                "or set LANGGRAPH_ENABLED=0 for single-call mode."
            ) from exc

        count = expected_count or 0
        graph = SkeletonGraph(self.client)
        result = await graph.run(
            user_story=user_story,
            conditions=conditions,
            target_urls=target_urls,
            expected_test_count=count,
        )
        if result["validation_errors"] and not result["skeleton_code"]:
            raise RuntimeError(
                f"LangGraph skeleton generation failed after retries: {'; '.join(result['validation_errors'])}"
            )
        return result["skeleton_code"]
