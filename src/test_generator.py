"""Test generation helpers for both direct generation and skeleton-first pipeline flows."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.llm_client import LLMClient
from src.prompt_builder import PromptBuilder, build_skeleton_prompt

logger = logging.getLogger(__name__)


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
        use_graph: bool = False,
    ) -> str:
        """Generate placeholder-based skeleton code for the intelligent pipeline.

        When ``use_graph=True``, delegates to the multi-agent LangGraph
        workflow (Planner → Generator → Validator).  Otherwise uses the
        original single-call pipeline.

        NOTE (2026-08-01): the LangGraph skeleton workflow is experimental and
        opt-in — the production path is the single-call pipeline. ``langgraph``
        is an optional extra; CI skips graph tests when it is absent.
        B-036 Phase 4: the ``LANGGRAPH_ENABLED`` env gate was removed — pass
        ``use_graph=True`` explicitly to select the graph skeleton path.
        """
        if use_graph:
            return await self._generate_skeleton_langgraph(user_story, conditions, target_urls, expected_count)
        return await self._generate_skeleton_single_call(user_story, conditions, target_urls, expected_count)

    async def _generate_skeleton_single_call(
        self,
        user_story: str,
        conditions: str,
        target_urls: list[str] | None = None,
        expected_count: int | None = None,
    ) -> str:
        """Single-call skeleton generation (original pipeline).

        Prompt assembly uses the PEP 750 t-string PromptBuilder
        (``src/prompt_builder.py``): trusted static structure stays separate
        from untrusted interpolated values, per-field transforms are applied
        at render time, and the structured audit entry (which fields, which
        values, what was truncated) is logged separately from the prompt text.
        """
        urls = target_urls or []
        known_urls_block = "\n".join(f"- {url}" for url in urls) if urls else "- No URLs were supplied."
        count_note = (
            f"\n\nIMPORTANT: You must generate exactly {expected_count} test functions (one per criterion)."
            if expected_count
            else ""
        )
        rendered = PromptBuilder(
            build_skeleton_prompt(
                user_story=user_story,
                conditions=conditions,
                known_urls_block=known_urls_block,
                expected_count=expected_count,
            )
        ).render()
        # Structured audit trail — the LLM gets the text, the store gets the
        # metadata (fields, truncation, static-vs-dynamic split).
        logger.debug("llm_call=generate_skeleton fields=%s", rendered.to_log_entry())
        prompt = rendered.text + count_note
        # Explicit pipeline decision (2026-08-18): skeleton generation is a
        # structured-output task. On thinking models (Qwen3.6/3.8) the
        # thinking phase exhausts the max_tokens budget and returns EMPTY
        # content — the root cause of the `got=0` generation retry loops.
        # With thinking off the same call is deterministic and ~10x faster.
        # Default is off; AITEST_ENABLE_THINKING=1 opts into a thinking-ON leg.
        # The delivered mode is logged per call by LLMClient, never silent.
        from src.llm_client import enable_thinking_default

        return await self.client.generate(prompt, enable_thinking=enable_thinking_default())

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
                "or pass use_graph=False for single-call mode."
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
