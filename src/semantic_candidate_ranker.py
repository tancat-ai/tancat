"""Constrained LLM ranking for shortlisted placeholder candidates.

B-020: Extended to support assertion-type selection for ASSERT actions.
When action is ASSERT, the LLM returns both the best candidate and the
Playwright assertion type (toBeVisible, toHaveText, toContainText, etc.).
"""

from __future__ import annotations

import json
from typing import Any, Protocol


class AsyncGeneratorLike(Protocol):
    """Minimal protocol for async text generation used by the ranker."""

    async def generate(self, prompt: str, timeout: int = 300, system_prompt: str | None = None) -> str:
        """Generate text from a prompt."""
        ...


# B-020: Valid assertion types the LLM can return.
ASSERTION_TYPES = frozenset(
    {
        "toBeVisible",
        "toHaveText",
        "toContainText",
        "toHaveCount",
        "toBeDisabled",
        "toBeEnabled",
        "toBeChecked",
        "toBeEmpty",
        "toHaveValue",
        "toHaveClass",
        "toHaveAttribute",
    }
)


class SemanticCandidateRanker:
    """Use an LLM to rank a tiny candidate list without inventing selectors.

    B-020: For ASSERT actions, the LLM also selects the assertion type
    and optional expected value, enabling the code postprocessor to
    generate the correct Playwright assertion.
    """

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
        previous_steps: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Return the best candidate from a short list, or None on failure.

        B-020: Returns additional keys for ASSERT actions:
            - assertion_type: e.g. "toBeVisible", "toHaveText"
            - expected_value: optional, for toHaveText/toContainText/etc.

        Args:
            previous_steps: Compressed list of prior step descriptions,
                e.g. ["FILL: username -> #user-name", "CLICK: login -> #login-button"].
        """
        if self.generator is None or not candidates:
            return None
        if len(candidates) == 1:
            result = dict(candidates[0])
            if action == "ASSERT":
                result["assertion_type"] = "toBeVisible"
            return result

        prompt = self._build_prompt(
            action=action,
            description=description,
            current_url=current_url,
            candidates=candidates,
            previous_steps=previous_steps,
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
        if not (0 <= selected_index < len(candidates)):
            return None

        result = dict(candidates[selected_index])

        # B-020: Extract assertion metadata for ASSERT actions
        if action == "ASSERT":
            assertion_type = payload.get("assertion_type", "toBeVisible")
            if assertion_type not in ASSERTION_TYPES:
                assertion_type = "toBeVisible"
            result["assertion_type"] = assertion_type
            result["expected_value"] = payload.get("expected_value")

        return result

    @staticmethod
    def _build_prompt(
        *,
        action: str,
        description: str,
        current_url: str | None,
        candidates: list[dict[str, Any]],
        previous_steps: list[str] | None = None,
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
                        "data_test": str(candidate.get("data_test", "")).strip(),
                        "href": str(candidate.get("href", "")).strip(),
                        "classes": str(candidate.get("classes", "")).strip(),
                        "placeholder": str(candidate.get("placeholder", "")).strip(),
                        "accessible_name": str(candidate.get("accessible_name", "")).strip(),
                    }
                )
            )

        # B-020: Build previous steps context block
        steps_block = ""
        if previous_steps:
            steps_lines = "\n".join(f"  - {step}" for step in previous_steps)
            steps_block = f"Previous steps in this test:\n{steps_lines}\n\n"

        # B-020: Assertion type instructions for ASSERT actions
        if action == "ASSERT":
            assertion_instructions = (
                "\nAssertion type: Pick the best Playwright assertion.\n"
                "Options: toBeVisible, toHaveText, toContainText, toHaveCount,\n"
                "  toBeDisabled, toBeEnabled, toBeChecked, toBeEmpty, toHaveValue.\n"
                "- Use toBeVisible for 'X is visible' / 'page loaded' assertions.\n"
                "- Use toHaveText when exact text is expected.\n"
                "- Use toContainText when partial text should be present.\n"
                "- Use toHaveCount for 'N items' assertions.\n"
                "- Use toBeDisabled/toBeEnabled for interactive state.\n"
                "- Use toBeChecked for checkboxes/radio buttons.\n"
                "- Use toBeEmpty for empty containers/lists.\n"
                "- Use toHaveValue for input field values.\n"
                "If toHaveText/toContainText/toHaveValue, set expected_value to the text/value.\n"
                "If toHaveCount, set expected_value to the number (as an integer).\n"
            )
            return_json = (
                '\nReturn JSON like {"selected_index": 1, "assertion_type": "toBeVisible", '
                '"expected_value": null, "reason": "short reason"}'
            )
        else:
            assertion_instructions = ""
            return_json = '\nReturn JSON like {"selected_index": 1, "reason": "short reason"}'

        return (
            f"Action: {action}\n"
            f"Requirement: {description}\n"
            f"Current page URL: {current_url or ''}\n"
            f"{steps_block}"
            "Choose the single best candidate for this step.\n"
            "Prefer semantic evidence over navigation chrome.\n"
            "For ASSERT, prefer content that proves the requirement.\n"
            "For CLICK, prefer the control that advances the intended journey.\n"
            f"{assertion_instructions}"
            "Candidates:\n" + "\n".join(candidate_lines) + return_json
        )
