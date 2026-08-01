"""Unit tests for the Test Table module (AI-034 Phase 1)."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

from src.spec_analyzer import TestCondition
from src.test_table import (
    DEFAULT_MAX_ROWS_PER_CONDITION,
    TestRow,
    TestTable,
    TestTableExpander,
    apply_editor_rows,
    build_table,
    next_row_id,
    normalize_action,
    single_row_for_condition,
    table_to_conditions,
)


def _condition(
    condition_id: str = "TC01.03", text: str = "filters — A-Z, Z-A, price low-high, price high-low"
) -> TestCondition:
    """Build a TestCondition with sensible defaults."""
    return TestCondition(
        id=condition_id,
        type="happy_path",
        text=text,
        expected="Meets acceptance criteria.",
        source="AC 3",
        flagged=False,
        src="manual",
        intent="journey_step",
    )


def _mock_llm(json_response: str) -> MagicMock:
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = json_response
    return mock_llm


# ---------------------------------------------------------------------------
# TestRow serialization + action normalization
# ---------------------------------------------------------------------------


def test_row_to_dict_round_trip() -> None:
    row = TestRow(
        id="T01",
        condition_ref="TC01.03",
        intent="Verify Name A-Z produces ascending name order",
        expected_action="SELECT",
        expected_target="sort dropdown, option Name A-Z",
        row_index=1,
    )
    restored = TestRow.from_dict(row.to_dict())
    assert restored == row


def test_row_from_dict_normalizes_action() -> None:
    data = {
        "id": "T05",
        "condition_ref": "TC01.02",
        "intent": "Login with valid credentials",
        "expected_action": "click",
        "expected_target": "login button",
        "row_index": 5,
    }
    row = TestRow.from_dict(data)
    assert row.expected_action == "CLICK"
    assert row.id == "T05"


def test_normalize_action_aliases() -> None:
    assert normalize_action("select") == "SELECT"
    assert normalize_action("click") == "CLICK"
    assert normalize_action("fill") == "FILL"
    assert normalize_action("verify") == "ASSERT"
    assert normalize_action("open") == "NAVIGATE"
    assert normalize_action("") == "ASSERT"


def test_normalize_action_unknown_defaults_to_assert() -> None:
    assert normalize_action("observe") == "ASSERT"


# ---------------------------------------------------------------------------
# TestTable CRUD + counting
# ---------------------------------------------------------------------------


def _sample_table() -> TestTable:
    rows = [
        TestRow(id="T01", condition_ref="TC01.03", intent="Name A-Z", expected_action="SELECT", row_index=1),
        TestRow(id="T02", condition_ref="TC01.03", intent="Name Z-A", expected_action="SELECT", row_index=2),
        TestRow(id="T03", condition_ref="TC01.04", intent="Product details visible", row_index=3),
    ]
    return TestTable.from_rows(rows, confirmed_ids={"T01"})


def test_rows_for_condition_filters_by_ref() -> None:
    table = _sample_table()
    assert [row.id for row in table.rows_for_condition("TC01.03")] == ["T01", "T02"]
    assert table.rows_for_condition("TC99") == []


def test_tests_count_for_condition() -> None:
    table = _sample_table()
    assert table.tests_count_for("TC01.03") == 2
    assert table.tests_count_for("TC01.04") == 1
    assert table.tests_count_for("TC99") == 0


def test_add_and_remove_row() -> None:
    table = _sample_table()
    table = table.add_row(TestRow(id="T04", condition_ref="TC01.03", intent="Price low-high", row_index=4))
    assert table.tests_count_for("TC01.03") == 3
    table = table.remove_row("T04")
    assert table.tests_count_for("TC01.03") == 2
    # removing a row also clears its confirmation entry
    table = table.add_row(
        TestRow(id="T05", condition_ref="TC01.03", intent="Price high-low", row_index=4),
        confirmed=True,
    )
    assert "T05" in table.confirmed_row_ids
    table = table.remove_row("T05")
    assert "T05" not in table.confirmed_row_ids


def test_update_row_preserves_confirmation() -> None:
    table = _sample_table()  # T01 confirmed, T02 not
    updated = TestRow(id="T01", condition_ref="TC01.03", intent="Name A-Z (edited)", row_index=1)
    table = table.update_row("T01", updated)
    assert table.rows[0].intent == "Name A-Z (edited)"
    assert "T01" in table.confirmed_row_ids


def test_confirm_toggle() -> None:
    table = _sample_table()
    assert table.unreviewed_row_ids == {"T02", "T03"}
    table = table.confirm("T02")
    assert "T02" in table.confirmed_row_ids
    table = table.confirm("T02", confirmed=False)
    assert "T02" not in table.confirmed_row_ids


def test_confirm_condition_confirms_all_rows() -> None:
    table = _sample_table()
    table = table.confirm_condition("TC01.03")
    assert {"T01", "T02"} <= table.confirmed_row_ids
    assert "T03" not in table.confirmed_row_ids
    table = table.confirm_condition("TC01.03", confirmed=False)
    assert "T02" not in table.confirmed_row_ids


def test_is_fully_confirmed() -> None:
    assert _sample_table().is_fully_confirmed is False
    table = TestTable.from_rows([TestRow(id="T01", condition_ref="TC01.03", intent="Name A-Z")])
    assert table.is_fully_confirmed is True


def test_to_dict_round_trip() -> None:
    table = _sample_table()
    payload = table.to_dict()
    restored = TestTable(
        rows=[TestRow.from_dict(row) for row in cast("list[dict[str, object]]", payload["rows"])],
        confirmed_ids=set(cast("list[str]", payload["confirmed_ids"])),
    )
    assert restored == table


# ---------------------------------------------------------------------------
# next_row_id + single_row_for_condition
# ---------------------------------------------------------------------------


def test_next_row_id_sequential() -> None:
    rows = [
        TestRow(id="T01", condition_ref="TC1", intent="a"),
        TestRow(id="T02", condition_ref="TC1", intent="b"),
    ]
    assert next_row_id(rows) == "T03"
    assert next_row_id([]) == "T01"


def test_single_row_for_condition_maps_intent_to_action() -> None:
    behavior = _condition("TC1", "click the login button")
    behavior.intent = "element_behavior"
    row = single_row_for_condition(behavior)
    assert row.intent == behavior.text
    assert row.expected_action == "CLICK"

    outcome = _condition("TC2", "checkout completes")
    outcome.intent = "journey_outcome"
    row = single_row_for_condition(outcome)
    assert row.expected_action == "ASSERT"


# ---------------------------------------------------------------------------
# LLM expansion
# ---------------------------------------------------------------------------


def test_expand_condition_multi_row() -> None:
    mock_llm = _mock_llm(
        """[
        {"intent": "Verify Name A-Z sorts ascending", "expected_action": "SELECT", "expected_target": "sort dropdown, option Name A-Z"},
        {"intent": "Verify Name Z-A sorts descending", "expected_action": "SELECT", "expected_target": "sort dropdown, option Name Z-A"},
        {"intent": "Verify price low-high", "expected_action": "SELECT", "expected_target": "sort dropdown, option Price low-high"},
        {"intent": "Verify price high-low", "expected_action": "SELECT", "expected_target": "sort dropdown, option Price high-low"}
    ]"""
    )
    expander = TestTableExpander(llm_client=mock_llm)
    rows = expander.expand_condition(_condition())
    assert len(rows) == 4
    assert all(row.condition_ref == "TC01.03" for row in rows)
    assert rows[0].expected_action == "SELECT"


def test_expand_condition_atomic_single_row() -> None:
    mock_llm = _mock_llm(
        """[
        {"intent": "Login with valid credentials", "expected_action": "FILL", "expected_target": "username/password fields"}
    ]"""
    )
    expander = TestTableExpander(llm_client=mock_llm)
    rows = expander.expand_condition(_condition("TC01.02", "login with valid credentials"))
    assert len(rows) == 1
    assert rows[0].expected_action == "FILL"


def test_expand_condition_fallback_when_llm_unavailable() -> None:
    mock_llm = MagicMock()
    mock_llm.generate_test.side_effect = RuntimeError("LLM down")
    expander = TestTableExpander(llm_client=mock_llm)
    rows = expander.expand_condition(_condition())
    assert len(rows) == 1  # no regression — 1 condition → 1 row
    assert rows[0].intent == _condition().text


def test_expand_condition_fallback_on_garbage_output() -> None:
    expander = TestTableExpander(llm_client=_mock_llm("This is not JSON at all"))
    rows = expander.expand_condition(_condition())
    assert len(rows) == 1


def test_expand_condition_empty_text_returns_no_rows() -> None:
    expander = TestTableExpander(llm_client=_mock_llm("[]"))
    empty = _condition("TC0", "")
    rows = expander.expand_condition(empty)
    assert rows == []


def test_expand_condition_respects_max_rows_cap() -> None:
    many_rows = "[" + ",".join(f'{{"intent": "row {i}", "expected_action": "ASSERT"}}' for i in range(1, 20)) + "]"
    expander = TestTableExpander(llm_client=_mock_llm(many_rows))
    rows = expander.expand_condition(_condition())
    assert len(rows) == DEFAULT_MAX_ROWS_PER_CONDITION == 10


def test_expand_condition_repairs_markdown_fences_and_trailing_commas() -> None:
    mock_llm = _mock_llm(
        """Here are the rows:
```json
[
  { "intent": "Verify sort A-Z", "expected_action": "select", "expected_target": "dropdown", },
]
```
Done."""
    )
    expander = TestTableExpander(llm_client=mock_llm)
    rows = expander.expand_condition(_condition())
    assert len(rows) == 1
    assert rows[0].expected_action == "SELECT"


def test_expand_condition_skips_empty_intent_rows() -> None:
    mock_llm = _mock_llm(
        """[
        {"intent": "", "expected_action": "ASSERT"},
        {"intent": "Verify cart badge count", "expected_action": "ASSERT"}
    ]"""
    )
    expander = TestTableExpander(llm_client=mock_llm)
    rows = expander.expand_condition(_condition("TC1", "cart badge"))
    assert len(rows) == 1
    assert rows[0].intent == "Verify cart badge count"


def test_expand_conditions_assigns_sequential_ids() -> None:
    mock_llm = MagicMock()
    mock_llm.generate_test.side_effect = [
        """[
            {"intent": "Filter A-Z", "expected_action": "SELECT"},
            {"intent": "Filter Z-A", "expected_action": "SELECT"}
        ]""",
        """[
            {"intent": "Product details visible", "expected_action": "ASSERT"}
        ]""",
    ]
    expander = TestTableExpander(llm_client=mock_llm)
    conditions = [_condition("TC01.03"), _condition("TC01.04", "product details visible")]
    rows = expander.expand_conditions(conditions)
    assert [row.id for row in rows] == ["T01", "T02", "T03"]
    assert [row.condition_ref for row in rows] == ["TC01.03", "TC01.03", "TC01.04"]
    assert [row.row_index for row in rows] == [1, 2, 3]


# ---------------------------------------------------------------------------
# build_table + apply_editor_rows
# ---------------------------------------------------------------------------


def test_build_table_expands_and_confirms_all() -> None:
    mock_llm = _mock_llm(
        """[
        {"intent": "Filter A-Z", "expected_action": "SELECT"},
        {"intent": "Filter Z-A", "expected_action": "SELECT"}
    ]"""
    )
    expander = TestTableExpander(llm_client=mock_llm)
    table = build_table([_condition("TC01.03")], expander=expander)
    assert table.tests_count_for("TC01.03") == 2
    assert table.is_fully_confirmed is True


def test_build_table_fallback_single_row_per_condition() -> None:
    expander = TestTableExpander(llm_client=_mock_llm("not json"))
    table = build_table([_condition("TC01.03"), _condition("TC01.04", "product details visible")], expander=expander)
    assert [row.id for row in table.rows] == ["T01", "T02"]
    assert table.tests_count_for("TC01.03") == 1
    assert table.tests_count_for("TC01.04") == 1


def test_apply_editor_rows_round_trip() -> None:
    table = build_table([_condition("TC01.03")], expander=TestTableExpander(llm_client=_mock_llm("[]")))
    assert table.tests_count_for("TC01.03") == 1

    edited_rows = [
        {
            "id": "T01",
            "condition_ref": "TC01.03",
            "intent": "Filter A-Z",
            "expected_action": "SELECT",
            "expected_target": "sort dropdown",
            "reviewed": True,
        },
        {
            "id": "T02",
            "condition_ref": "TC01.03",
            "intent": "Filter Z-A",
            "expected_action": "SELECT",
            "expected_target": "sort dropdown",
            "reviewed": False,
        },
    ]
    updated = apply_editor_rows(table, edited_rows)
    assert updated.tests_count_for("TC01.03") == 2
    assert [row.id for row in updated.rows] == ["T01", "T02"]
    assert updated.confirmed_row_ids == {"T01"}
    assert updated.rows[0].expected_action == "SELECT"


def test_apply_editor_rows_assigns_missing_ids() -> None:
    table = TestTable()
    updated = apply_editor_rows(
        table,
        [
            {"condition_ref": "TC1", "intent": "New row A", "reviewed": True},
            {"condition_ref": "TC1", "intent": "New row B", "reviewed": True},
        ],
    )
    assert [row.id for row in updated.rows] == ["T01", "T02"]


# ---------------------------------------------------------------------------
# table_to_conditions (AI-034 Phase 3) — one skeleton per confirmed row
# ---------------------------------------------------------------------------


def _confirmed_table() -> TestTable:
    return TestTable(
        rows=[
            TestRow(
                id="T01",
                condition_ref="TC01.03",
                intent="Verify Name A-Z sorts ascending",
                expected_action="SELECT",
                expected_target="sort dropdown, option Name A-Z",
            ),
            TestRow(
                id="T02", condition_ref="TC01.03", intent="Verify Name Z-A sorts descending", expected_action="SELECT"
            ),
            TestRow(id="T03", condition_ref="TC01.04", intent="Product details visible", expected_action="ASSERT"),
        ],
        confirmed_ids={"T01", "T03"},
    )


def test_table_to_conditions_confirmed_rows_only() -> None:
    conditions = table_to_conditions(_confirmed_table())
    assert [condition.id for condition in conditions] == ["T01", "T03"]
    assert conditions[0].type == "happy_path"
    assert conditions[0].src == "manual"


def test_table_to_conditions_text_embeds_target() -> None:
    conditions = table_to_conditions(_confirmed_table())
    assert conditions[0].text == "Verify Name A-Z sorts ascending — target: sort dropdown, option Name A-Z"
    # no target on T02-equivalent row → plain intent
    assert "— target" not in conditions[1].text


def test_table_to_conditions_includes_unconfirmed_when_requested() -> None:
    conditions = table_to_conditions(_confirmed_table(), confirmed_only=False)
    assert [condition.id for condition in conditions] == ["T01", "T02", "T03"]


def test_table_to_conditions_empty_confirmed_returns_empty() -> None:
    table = TestTable(
        rows=[TestRow(id="T01", condition_ref="TC1", intent="x")],
        confirmed_ids=set(),
    )
    assert table_to_conditions(table) == []


def test_table_to_conditions_intent_is_valid_literal() -> None:
    from src.spec_analyzer import ConditionIntent

    conditions = table_to_conditions(_confirmed_table())
    for condition in conditions:
        assert condition.intent in ConditionIntent.__args__  # type: ignore[attr-defined]


def test_table_to_conditions_source_tracks_condition_ref() -> None:
    conditions = table_to_conditions(_confirmed_table())
    assert conditions[0].source == "Test Table row for condition TC01.03"
