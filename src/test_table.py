"""Test Table — LLM expansion of Living Test Plan conditions into concrete test rows.

AI-034 Phase 1: data model + LLM expansion + CRUD operations.

The Test Table sits between the Living Test Plan and skeleton generation. Each
condition may describe several distinct test scenarios (e.g. "filters — A-Z, Z-A,
price low-high, price high-low" describes four); the LLM expands it into one
``TestRow`` per scenario so the tester sees — and can refine — exactly what will be
generated before skeleton code exists.

Guarantee: when the LLM is unavailable or returns unusable output, expansion falls
back to a single deterministic row per condition (1 condition → 1 row), so the
pipeline never regresses for atomic conditions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal, cast

from src.llm_client import LLMClient
from src.spec_analyzer import TestCondition, infer_condition_intent

TestAction = Literal["SELECT", "CLICK", "FILL", "ASSERT", "NAVIGATE"]

#: Hard ceiling on rows the LLM may produce for a single condition.
DEFAULT_MAX_ROWS_PER_CONDITION = 10

_VALID_ACTIONS: frozenset[str] = frozenset({"SELECT", "CLICK", "FILL", "ASSERT", "NAVIGATE"})
_ACTION_ALIASES: dict[str, str] = {
    "select": "SELECT",
    "choose": "SELECT",
    "click": "CLICK",
    "press": "CLICK",
    "fill": "FILL",
    "type": "FILL",
    "enter": "FILL",
    "assert": "ASSERT",
    "verify": "ASSERT",
    "check": "ASSERT",
    "navigate": "NAVIGATE",
    "goto": "NAVIGATE",
    "go": "NAVIGATE",
    "open": "NAVIGATE",
}


def normalize_action(raw: str) -> TestAction:
    """Normalize a free-text action to a valid TestAction literal."""
    cleaned = str(raw or "").strip().upper()
    if cleaned in _VALID_ACTIONS:
        return cast(TestAction, cleaned)
    return cast(TestAction, _ACTION_ALIASES.get(cleaned.lower(), "ASSERT"))


def _infer_action_from_intent(intent: str) -> TestAction:
    """Return a deterministic default action for a condition intent (fallback path)."""
    if intent == "element_behavior":
        return "CLICK"
    if intent == "journey_step":
        return "NAVIGATE"
    return "ASSERT"


@dataclass(frozen=True)
class TestRow:
    """One concrete test scenario expanded from a Living Test Plan condition."""

    __test__ = False

    id: str  # "T01"
    condition_ref: str  # "TC01.03"
    intent: str  # "Verify Name A-Z produces ascending name order"
    expected_action: TestAction = "ASSERT"
    expected_target: str = ""  # e.g. "sort dropdown, option 'Name A-Z'"
    row_index: int = 0  # display order

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/session-state friendly representation."""
        return {
            "id": self.id,
            "condition_ref": self.condition_ref,
            "intent": self.intent,
            "expected_action": self.expected_action,
            "expected_target": self.expected_target,
            "row_index": self.row_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> TestRow:
        """Reconstruct a TestRow from a dict (editor round-trip)."""
        return cls(
            id=str(data.get("id", "")).strip(),
            condition_ref=str(data.get("condition_ref", "")).strip(),
            intent=str(data.get("intent", "")).strip(),
            expected_action=normalize_action(str(data.get("expected_action", "ASSERT"))),
            expected_target=str(data.get("expected_target", "")).strip(),
            row_index=int(str(data.get("row_index", 0) or 0)) or 0,
        )


@dataclass(frozen=True)
class TestTable:
    """Tester-reviewable collection of expanded test rows."""

    __test__ = False

    rows: list[TestRow] = field(default_factory=list)
    confirmed_ids: set[str] = field(default_factory=set)

    @property
    def row_ids(self) -> set[str]:
        """Return all row ids currently in the table."""
        return {row.id for row in self.rows}

    @property
    def confirmed_row_ids(self) -> set[str]:
        """Return confirmed ids that still exist in the table."""
        return self.confirmed_ids.intersection(self.row_ids)

    @property
    def unreviewed_row_ids(self) -> set[str]:
        """Return row ids that still need explicit confirmation."""
        return self.row_ids.difference(self.confirmed_row_ids)

    @property
    def is_fully_confirmed(self) -> bool:
        """Return True when every row has been reviewed."""
        return bool(self.rows) and not self.unreviewed_row_ids

    def rows_for_condition(self, condition_ref: str) -> list[TestRow]:
        """Return the rows belonging to one condition, in display order."""
        return [row for row in self.rows if row.condition_ref == condition_ref]

    def tests_count_for(self, condition_ref: str) -> int:
        """Return how many test rows a condition produces (Phase 2 "Tests" column)."""
        return len(self.rows_for_condition(condition_ref))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/session-state friendly representation."""
        return {
            "rows": [row.to_dict() for row in self.rows],
            "confirmed_ids": sorted(self.confirmed_row_ids),
        }

    @classmethod
    def from_rows(cls, rows: Sequence[TestRow], *, confirmed_ids: set[str] | None = None) -> TestTable:
        """Create a table from rows, defaulting to all rows confirmed."""
        confirmed = confirmed_ids if confirmed_ids is not None else {row.id for row in rows}
        return cls(rows=list(rows), confirmed_ids=set(confirmed))

    def add_row(self, row: TestRow, *, confirmed: bool = False) -> TestTable:
        """Append a new row to the table."""
        return replace(
            self,
            rows=[*self.rows, row],
            confirmed_ids=set(self.confirmed_row_ids) | ({row.id} if confirmed else set()),
        )

    def remove_row(self, row_id: str) -> TestTable:
        """Remove one row and any stale confirmation entry."""
        updated_rows = [row for row in self.rows if row.id != row_id]
        updated_confirmed = {rid for rid in self.confirmed_row_ids if rid != row_id}
        return replace(self, rows=updated_rows, confirmed_ids=updated_confirmed)

    def update_row(self, row_id: str, updated: TestRow) -> TestTable:
        """Replace one row by id, preserving its confirmation state."""
        updated_rows = [updated if row.id == row_id else row for row in self.rows]
        updated_confirmed = set(self.confirmed_row_ids)
        return replace(self, rows=updated_rows, confirmed_ids=updated_confirmed)

    def confirm(self, row_id: str, *, confirmed: bool = True) -> TestTable:
        """Mark one row reviewed or unreviewed."""
        updated_confirmed = set(self.confirmed_row_ids)
        if confirmed and row_id in self.row_ids:
            updated_confirmed.add(row_id)
        else:
            updated_confirmed.discard(row_id)
        return replace(self, confirmed_ids=updated_confirmed)

    def confirm_condition(self, condition_ref: str, *, confirmed: bool = True) -> TestTable:
        """Mark all rows of one condition reviewed or unreviewed together."""
        condition_row_ids = {row.id for row in self.rows_for_condition(condition_ref)}
        updated_confirmed = set(self.confirmed_row_ids)
        for row_id in condition_row_ids:
            if confirmed:
                updated_confirmed.add(row_id)
            else:
                updated_confirmed.discard(row_id)
        return replace(self, confirmed_ids=updated_confirmed)


def next_row_id(rows: Sequence[TestRow], *, prefix: str = "T") -> str:
    """Return the next sequential test row id for the given rows."""
    max_suffix = 0
    for row in rows:
        if not row.id.startswith(prefix):
            continue
        suffix = row.id.removeprefix(prefix)
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))
    return f"{prefix}{max_suffix + 1:02d}"


def _assign_row_ids(rows: Sequence[TestRow]) -> list[TestRow]:
    """Return rows with stable sequential ids and display order."""
    return [replace(row, id=f"T{index:02d}", row_index=index) for index, row in enumerate(rows, start=1)]


def single_row_for_condition(condition: TestCondition, *, row_id: str = "") -> TestRow:
    """Return the deterministic single test row for a condition (fallback path)."""
    return TestRow(
        id=row_id,
        condition_ref=condition.id,
        intent=condition.text,
        expected_action=_infer_action_from_intent(condition.intent),
        expected_target="",
        row_index=0,
    )


def table_to_conditions(table: TestTable, *, confirmed_only: bool = True) -> list[TestCondition]:
    """Convert test rows into generation conditions — one skeleton per row (AI-034 Phase 3).

    Each (confirmed) row becomes a ``TestCondition`` whose id is the row id and
    whose text is the row's intent (plus expected target when present), so the
    existing per-condition skeleton generator emits exactly one function per row.
    Rows the tester removed are simply absent; unconfirmed rows are skipped
    unless ``confirmed_only`` is False.
    """
    rows = [row for row in table.rows if row.id in table.confirmed_row_ids] if confirmed_only else list(table.rows)
    conditions: list[TestCondition] = []
    for row in rows:
        text = row.intent
        if row.expected_target:
            text = f"{text} — target: {row.expected_target}"
        conditions.append(
            TestCondition(
                id=row.id,
                type="happy_path",
                text=text,
                expected=f"Action: {row.expected_action}. Meets acceptance criteria.",
                source=f"Test Table row for condition {row.condition_ref}",
                flagged=False,
                src="manual",
                intent=infer_condition_intent(row.intent),
            )
        )
    return conditions


class TestTableExpander:
    """Expands conditions into concrete test rows via the LLM.

    Resilient by design: any LLM failure (unavailable, timeout, unparsable output)
    degrades to one deterministic row per condition instead of raising — the
    pipeline must never break because the LLM is down.
    """

    __test__ = False

    SYSTEM_PROMPT = (
        "You are an expert QA Test Analyst expanding test conditions into concrete test scenarios.\n"
        "\n"
        "For each test condition, determine how many DISTINCT test scenarios it describes and "
        "output ONE test row per scenario.\n"
        "\n"
        "Rules:\n"
        '- A condition like "filters — A-Z, Z-A, price low-high, price high-low" describes 4 '
        "distinct scenarios → 4 rows.\n"
        '- An atomic condition like "login with valid credentials" describes 1 scenario → 1 row.\n'
        "- Do NOT invent scenarios the condition does not describe.\n"
        "- Do NOT skip, combine, or merge scenarios.\n"
        f"- Maximum {DEFAULT_MAX_ROWS_PER_CONDITION} rows per condition.\n"
        "\n"
        "Output ONLY valid JSON matching this schema:\n"
        "[\n"
        "  {\n"
        '    "intent": "Plain English: what this test row verifies, using exact labels from the condition",\n'
        '    "expected_action": "SELECT|CLICK|FILL|ASSERT|NAVIGATE",\n'
        '    "expected_target": "The element/option/value the action applies to (e.g. sort dropdown, option Name A-Z)"\n'
        "  }\n"
        "]\n"
        "No markdown fences around the JSON. No conversational text.\n"
        "CRITICAL: Do NOT output trailing commas. The JSON must be strictly valid."
    )

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        max_rows_per_condition: int = DEFAULT_MAX_ROWS_PER_CONDITION,
    ) -> None:
        """Initialize the expander with an LLM client and row cap."""
        self.llm_client = llm_client or LLMClient()
        self.max_rows_per_condition = max(1, int(max_rows_per_condition))

    def expand_condition(self, condition: TestCondition) -> list[TestRow]:
        """Expand one condition into test rows (ids assigned later by the table builder).

        Falls back to a single deterministic row when the LLM path fails.
        """
        if not condition or not condition.text.strip():
            return []
        rows = self._attempt_llm_expansion(condition)
        if not rows:
            return [single_row_for_condition(condition)]
        return rows

    def expand_conditions(self, conditions: Sequence[TestCondition]) -> list[TestRow]:
        """Expand many conditions into a flat row list with stable sequential ids."""
        expanded: list[TestRow] = []
        for condition in conditions:
            expanded.extend(self.expand_condition(condition))
        return _assign_row_ids(expanded)

    def _attempt_llm_expansion(self, condition: TestCondition) -> list[TestRow]:
        """Call the LLM and parse rows. Returns [] on any failure."""
        prompt = (
            f"Condition: [{condition.id}] {condition.text}\n"
            f"Expected: {condition.expected}\n\n"
            "Expand this condition into one test row per distinct scenario."
        )
        try:
            response = self.llm_client.generate_test(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                timeout=300,
            )
        except Exception:
            return []
        return self._parse_response(response, condition_ref=condition.id)

    def _parse_response(self, response: str, *, condition_ref: str) -> list[TestRow]:
        """Parse the LLM JSON array into TestRow objects (best-effort)."""
        json_str = self._extract_json_array_text(response)
        json_str = self._repair_common_json_issues(json_str)
        if not json_str:
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []

        rows: list[TestRow] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            intent = str(item.get("intent", "")).strip()
            if not intent:
                continue  # ignore empty-noise rows from the LLM
            rows.append(
                TestRow(
                    id="",
                    condition_ref=condition_ref,
                    intent=intent,
                    expected_action=normalize_action(str(item.get("expected_action", "ASSERT"))),
                    expected_target=str(item.get("expected_target", "")).strip(),
                    row_index=0,
                )
            )
            if len(rows) >= self.max_rows_per_condition:
                break
        return rows

    @staticmethod
    def _extract_json_array_text(raw: str) -> str:
        """Return the best-effort JSON array substring from the LLM response."""
        if not raw:
            return ""
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        text = match.group(1) if match else raw
        text = text.strip()
        if not text:
            return ""
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()
        return text

    @staticmethod
    def _repair_common_json_issues(text: str) -> str:
        """Repair common JSON mistakes from LLM output (trailing commas, unquoted keys)."""
        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
        cleaned = re.sub(r"([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*):", r'\1"\2"\3:', cleaned)
        cleaned = re.sub(r"(?<!\\)'([^'\\]*)'", r'"\1"', cleaned)
        return cleaned


def build_table(
    conditions: Sequence[TestCondition],
    expander: TestTableExpander | None = None,
) -> TestTable:
    """Expand conditions and build a TestTable with sequential row ids.

    Rows start fully confirmed — the tester can unconfirm or edit before sign-off.
    """
    expander = expander or TestTableExpander()
    rows = expander.expand_conditions(list(conditions))
    return TestTable.from_rows(rows)


def apply_editor_rows(table: TestTable, rows: list[dict[str, object]]) -> TestTable:
    """Return a table updated from editable table rows (mirrors ``apply_editor_rows``)."""
    updated_rows: list[TestRow] = []
    updated_confirmed: set[str] = set()

    for index, row in enumerate(rows, start=1):
        row_id = str(row.get("id", "")).strip()
        if not row_id:
            row_id = next_row_id(updated_rows)
        test_row = TestRow(
            id=row_id,
            condition_ref=str(row.get("condition_ref", "")).strip(),
            intent=str(row.get("intent", "")).strip(),
            expected_action=normalize_action(str(row.get("expected_action", "ASSERT"))),
            expected_target=str(row.get("expected_target", "")).strip(),
            row_index=index,
        )
        updated_rows.append(test_row)
        if bool(row.get("reviewed", True)):
            updated_confirmed.add(row_id)

    return replace(table, rows=updated_rows, confirmed_ids=updated_confirmed)


__all__ = [
    "DEFAULT_MAX_ROWS_PER_CONDITION",
    "TestAction",
    "TestRow",
    "TestTable",
    "TestTableExpander",
    "apply_editor_rows",
    "build_table",
    "next_row_id",
    "normalize_action",
    "single_row_for_condition",
    "table_to_conditions",
]
