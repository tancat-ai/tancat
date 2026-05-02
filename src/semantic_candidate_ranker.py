"""Constrained LLM ranking for shortlisted placeholder candidates."""

from __future__ import annotations

import json
from typing import Any, Protocol


class AsyncGeneratorLike(Protocol):
    """Minimal protocol for async text generation used by the ranker."""

    async def generate(self, prompt: str, timeout: int = 300, system_prompt: str | None = None) -> str:
        """Generate text from a prompt."""
        ...


class SemanticCandidateRanker:
    """Use an LLM to rank a tiny candidate list without inventing selectors."""

    SYSTEM_PROMPT = (
        "You are ranking already-scraped UI candidates for Playwright test generation. "
        "Never invent selectors, URLs, or new candidates. "
        "Choose only from the numbered candidates provided. "
        "Return compact JSON only."
    )

    def __init__(self, generator: AsyncGeneratorLike | None = None) -> None:
        self.generator = generator

    async def choose_best_candidate(
        self,
        *,
        action: str,
        description: str,
        current_url: str | None,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the best candidate from a short list, or None on failure."""
        if self.generator is None or not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        prompt = self._build_prompt(
            action=action,
            description=description,
            current_url=current_url,
            candidates=candidates,
        )
        try:
            raw = await self.generator.generate(prompt, timeout=45, system_prompt=self.SYSTEM_PROMPT)
        except Exception:
            return None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None

        selected_index = payload.get("selected_index")
        if not isinstance(selected_index, int):
            return None
        if 0 <= selected_index < len(candidates):
            return candidates[selected_index]
        return None

    @staticmethod
    def _build_prompt(
        *,
        action: str,
        description: str,
        current_url: str | None,
        candidates: list[dict[str, Any]],
    ) -> str:
        """Return a compact ranking prompt for the candidate shortlist."""
        candidate_lines: list[str] = []
        for index, candidate in enumerate(candidates):
            candidate_lines.append(
                json.dumps(
                    {
                        "index": index,
                        "selector": str(candidate.get("selector", "")).strip(),
                        "text": str(candidate.get("text", "")).strip(),
                        "role": str(candidate.get("role", "")).strip(),
                        "href": str(candidate.get("href", "")).strip(),
                        "classes": str(candidate.get("classes", "")).strip(),
                        "placeholder": str(candidate.get("placeholder", "")).strip(),
                        "accessible_name": str(candidate.get("accessible_name", "")).strip(),
                    }
                )
            )

        return (
            f"Action: {action}\n"
            f"Requirement: {description}\n"
            f"Current page URL: {current_url or ''}\n"
            "Choose the single best candidate for this step.\n"
            "Prefer semantic evidence over navigation chrome.\n"
            "For ASSERT, prefer content that proves the requirement.\n"
            "For CLICK, prefer the control that advances the intended journey.\n"
            "Candidates:\n"
            + "\n".join(candidate_lines)
            + '\nReturn JSON like {"selected_index": 1, "reason": "short reason"}'
        )
