"""Spec Analyzer module to derive TestConditions from a test specification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from src.llm_client import LLMClient

ConditionType = Literal["happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"]
ConditionSrc = Literal["ai", "manual", "automation"]
ConditionIntent = Literal[
    "element_presence",
    "element_behavior",
    "state_assertion",
    "journey_step",
    "journey_outcome",
]


def infer_condition_intent(text: str) -> ConditionIntent:
    """Infer the best-fit generation intent for a test condition."""
    lowered = " ".join(part for part in text.lower().replace("_", " ").split() if part)

    if any(phrase in lowered for phrase in ("go to checkout", "go to cart", "open cart", "open checkout")):
        return "journey_step"
    if any(phrase in lowered for phrase in ("check out", "checkout successfully", "place order", "complete purchase")):
        return "journey_outcome"
    if any(
        phrase in lowered
        for phrase in ("added correctly", "is added", "is in cart", "updated correctly", "contains", "summary")
    ):
        return "state_assertion"
    if any(word in lowered for word in ("visible", "displayed", "shown", "present")):
        return "element_presence"
    if any(word in lowered for word in ("click", "select", "choose", "open", "navigate", "add to cart", "remove")):
        return "element_behavior"
    return "journey_step"


@dataclass
class TestCondition:
    """A single verifiable condition derived from spec analysis."""

    __test__ = False

    id: str  # e.g., BC01.02
    type: ConditionType
    text: str
    expected: str
    source: str
    flagged: bool = False
    src: ConditionSrc = "ai"
    intent: ConditionIntent = "journey_step"

    def to_dict(self) -> dict:
        """Return dict representation."""
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "expected": self.expected,
            "source": self.source,
            "flagged": self.flagged,
            "src": self.src,
            "intent": self.intent,
        }


class SpecAnalyzer:
    """Analyzes specifications to derive explicit test conditions."""

    SYSTEM_PROMPT = """You are an expert QA Test Analyst.
Your task is to analyze the provided feature specification and derive a comprehensive list of test conditions.
You must perform four analysis steps mentally, then output a JSON array of test conditions:
1. Extract business rules (logic statements, thresholds, constraints).
2. Map boundary values (at-limit, below-limit, above-limit).
3. Surface ambiguities (spec gaps where behaviour is undefined).
4. Derive specific test conditions.

The condition types are:
- `happy_path` (valid input, all rules pass)
- `boundary` (value at exactly the rule limit and +/-1 unit either side)
- `negative` (invalid input, error path)
- `exploratory` (tester-added, not spec-derivable, e.g. stress test)
- `regression` (parameterised automation, cross-boundary combinations)
- `ambiguity` (spec gap requiring product owner clarification before sign-off)

Output ONLY valid JSON matching this schema:
[
  {
    "id": "A unique ID string like 'TC01.01'",
    "type": "happy_path|boundary|negative|exploratory|regression|ambiguity",
    "text": "Plain English description of the test condition",
    "expected": "Plain English expected result",
    "source": "The specific spec clause that drove this condition",
    "flagged": boolean (true if type is ambiguity, false otherwise),
    "src": "ai",
    "intent": "element_presence|element_behavior|state_assertion|journey_step|journey_outcome"
  }
]
No markdown fences around the JSON. No conversational text.
CRITICAL: Do NOT output trailing commas. The JSON must be strictly valid."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Initialize with an LLM client."""
        self.llm_client = llm_client or LLMClient()

    def analyze(self, spec_text: str) -> list[TestCondition]:
        """Analyze spec text and return list of test conditions."""
        if not spec_text or not spec_text.strip():
            return []

        # If the user already provided explicit, numbered acceptance criteria, prefer
        # a deterministic mapping (one condition per criterion) over speculative LLM
        # expansion. This keeps the generator aligned with user intent/baselines.
        explicit_criteria = self._extract_numbered_criteria(spec_text)
        if explicit_criteria:
            conditions: list[TestCondition] = []
            for idx, text in enumerate(explicit_criteria, start=1):
                conditions.append(
                    TestCondition(
                        id=f"TC01.{idx:02d}",
                        type="happy_path",
                        text=text,
                        expected="Meets acceptance criteria.",
                        source=f"Acceptance Criteria {idx}",
                        flagged=False,
                        src="manual",
                        intent=infer_condition_intent(text),
                    )
                )
            return conditions

        prompt = f"Analyze the following specification:\n\n{spec_text}"

        try:
            # We use generate_test (or direct generation) to get the response string.
            response = self.llm_client.generate_test(prompt=prompt, system_prompt=self.SYSTEM_PROMPT, timeout=300)
            return self._parse_response(response)
        except Exception as e:
            raise RuntimeError(f"Spec analysis failed: {str(e)}") from e

    @staticmethod
    def _extract_numbered_criteria(spec_text: str) -> list[str]:
        """Extract numbered acceptance criteria lines from spec_text.

        Returns a list like ["Add items to cart", "Go to cart", ...] or [] if not found.
        """
        text = (spec_text or "").strip()
        if not text:
            return []

        # Try to isolate the acceptance criteria section if present.
        # Handles common headings:
        # - "## Acceptance Criteria"
        # - "Acceptance Criteria:"
        ac_match = re.search(r"(?im)^\s*(?:##\s*)?acceptance criteria\s*:?\s*$", text)
        if ac_match:
            section = text[ac_match.end() :]
        else:
            section = text

        criteria: list[str] = []
        for line in section.splitlines():
            m = re.match(r"^\s*(\d+)\.\s+(.*\S)\s*$", line)
            if not m:
                # Stop once we leave a numbered list after having started one.
                if criteria and line.strip() and not line.lstrip().startswith("-"):
                    break
                continue
            criteria.append(m.group(2).strip())

        return criteria

    def _parse_response(self, response: str) -> list[TestCondition]:
        """Parse LLM JSON response into TestCondition objects."""
        json_str = self._extract_json_array_text(response)
        json_str = self._repair_common_json_issues(json_str)

        if not json_str:
            raise RuntimeError("LLM returned empty or whitespace response")

        try:
            data = json.loads(json_str)
            if not isinstance(data, list):
                raise ValueError("Expected a JSON array of conditions")

            conditions = []
            for i, item in enumerate(data):
                item_dict: dict[str, Any] = item if isinstance(item, dict) else {}
                ctype = item_dict.get("type", "happy_path")
                # Ensure type is valid
                if ctype not in ["happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"]:
                    ctype = "happy_path"

                conditions.append(
                    TestCondition(
                        id=str(item_dict.get("id", f"COND.{i + 1:02d}")),
                        type=ctype,  # type: ignore
                        text=str(item_dict.get("text", "Unknown condition")),
                        expected=str(item_dict.get("expected", "Pass")),
                        source=str(item_dict.get("source", "Implicit")),
                        flagged=bool(item_dict.get("flagged", ctype == "ambiguity")),
                        src=str(item_dict.get("src", "ai")),  # type: ignore[arg-type]
                        intent=self._normalise_intent(item_dict.get("intent"), str(item_dict.get("text", ""))),
                    )
                )
            return conditions
        except json.JSONDecodeError as e:
            # Fallback: try to salvage individual objects even if the array is malformed.
            salvaged = self._try_parse_objects_from_array(json_str)
            if salvaged:
                return salvaged

            preview = json_str[:600].replace("\n", "\\n")
            raise RuntimeError(f"Failed to parse LLM response as JSON: {e}\nResponse was: {preview}...") from e

    @staticmethod
    def _extract_json_array_text(raw: str) -> str:
        """Return the best-effort JSON array substring from the LLM response."""
        if not raw:
            return ""

        # Prefer fenced JSON blocks if present.
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        text = match.group(1) if match else raw
        text = text.strip()
        if not text:
            return ""

        # If the model added preamble/epilogue, extract the first [...] region.
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
        return text

    @staticmethod
    def _repair_common_json_issues(text: str) -> str:
        """Attempt to repair common JSON mistakes from LLM output.

        Repairs:
        - Trailing commas before } or ]
        - Unquoted object keys: { id: "TC01" } -> { "id": "TC01" }
        - Single quotes in simple cases
        - Raw newlines inside quoted strings
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return ""

        # Remove trailing commas (most common).
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

        # Quote unquoted keys in objects.
        cleaned = re.sub(r"([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*):", r'\1"\2"\3:', cleaned)

        # Replace single-quoted keys/strings when it looks safe (no embedded quotes).
        cleaned = re.sub(r"(?<!\\)'([^'\\]*)'", r'"\1"', cleaned)

        # Escape raw newlines within JSON strings (invalid in strict JSON).
        cleaned = SpecAnalyzer._escape_newlines_inside_strings(cleaned)

        return cleaned

    @staticmethod
    def _escape_newlines_inside_strings(text: str) -> str:
        out: list[str] = []
        in_string = False
        escape = False
        for ch in text:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                out.append(ch)
                continue
            if in_string and ch in {"\n", "\r"}:
                out.append("\\n")
                continue
            out.append(ch)
        return "".join(out)

    @staticmethod
    def _normalise_intent(raw_intent: Any, text: str) -> ConditionIntent:
        """Return a validated condition intent, falling back to heuristic inference."""
        valid_intents: set[str] = {
            "element_presence",
            "element_behavior",
            "state_assertion",
            "journey_step",
            "journey_outcome",
        }
        intent = str(raw_intent or "").strip()
        if intent in valid_intents:
            return intent  # type: ignore[return-value]
        return infer_condition_intent(text)

    def _try_parse_objects_from_array(self, array_text: str) -> list[TestCondition]:
        """Best-effort parse when the overall JSON array is malformed.

        Extract `{...}` blocks and parse them individually.
        """
        blob = (array_text or "").strip()
        if not blob:
            return []

        # Find candidate object blocks. This is heuristic, but works well for common LLM output.
        object_blocks = re.findall(r"\{[\s\S]*?\}", blob)
        if not object_blocks:
            return []

        parsed_items: list[dict[str, Any]] = []
        for block in object_blocks:
            repaired = self._repair_common_json_issues(block)
            try:
                obj = json.loads(repaired)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                parsed_items.append(obj)

        if not parsed_items:
            return []

        # Reuse the normal item->TestCondition conversion path by encoding as a JSON array.
        repaired_array = json.dumps(parsed_items)
        data = json.loads(repaired_array)
        if not isinstance(data, list):
            return []

        conditions: list[TestCondition] = []
        for i, item in enumerate(data):
            item_dict: dict[str, Any] = item if isinstance(item, dict) else {}
            ctype = item_dict.get("type", "happy_path")
            if ctype not in ["happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"]:
                ctype = "happy_path"
            conditions.append(
                TestCondition(
                    id=str(item_dict.get("id", f"COND.{i + 1:02d}")),
                    type=ctype,  # type: ignore
                    text=str(item_dict.get("text", "Unknown condition")),
                    expected=str(item_dict.get("expected", "Pass")),
                    source=str(item_dict.get("source", "Implicit")),
                    flagged=bool(item_dict.get("flagged", ctype == "ambiguity")),
                    src=str(item_dict.get("src", "ai")),  # type: ignore[arg-type]
                )
            )
        return conditions
