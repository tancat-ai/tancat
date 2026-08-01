"""Unit tests for AI-034 Phase 2 shared Test Table wiring (src/ui_pipeline.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.spec_analyzer import TestCondition
from src.test_plan import TestPlan
from src.test_table import TestRow, TestTable
from src.ui_pipeline import (
    build_test_table,
    plan_rows_from_plan,
)
from src.ui_pipeline import (
    test_table_rows as ui_test_table_rows,
)


def _plan() -> TestPlan:
    return TestPlan.from_conditions(
        story_ref="story_test",
        sprint="Backlog",
        conditions=[
            TestCondition(
                id="TC01.03",
                type="happy_path",
                text="filters — A-Z, Z-A, price low-high, price high-low",
                expected="All four filters work",
                source="AC 3",
                src="manual",
            ),
            TestCondition(
                id="TC01.04",
                type="happy_path",
                text="product details visible",
                expected="Details shown",
                source="AC 4",
                src="manual",
            ),
        ],
    )


def _table() -> TestTable:
    return TestTable(
        rows=[
            TestRow(id="T01", condition_ref="TC01.03", intent="Filter A-Z", expected_action="SELECT"),
            TestRow(id="T02", condition_ref="TC01.03", intent="Filter Z-A", expected_action="SELECT"),
            TestRow(id="T03", condition_ref="TC01.04", intent="Product details visible"),
        ],
        confirmed_ids={"T01", "T02", "T03"},
    )


def test_build_test_table_expands_plan_via_expander() -> None:
    table = _table()
    with (
        patch("src.ui_pipeline.LLMClient") as mock_client_cls,
        patch("src.ui_pipeline.TestTableExpander") as mock_expander_cls,
    ):
        mock_expander = MagicMock()
        mock_expander.expand_conditions.return_value = table.rows
        mock_expander_cls.return_value = mock_expander

        result = build_test_table(
            plan=_plan(),
            provider="ollama",
            provider_base_url="http://localhost:11434",
            model_name="qwen3",
        )

    mock_client_cls.assert_called_once_with(
        provider="ollama",
        model="qwen3",
        base_url="http://localhost:11434",
    )
    mock_expander_cls.assert_called_once_with(llm_client=mock_client_cls.return_value)
    assert result.rows == table.rows


def test_build_test_table_empty_plan_yields_empty_table() -> None:
    empty_plan = TestPlan.from_conditions(story_ref="s", sprint="Backlog", conditions=[])
    with (
        patch("src.ui_pipeline.LLMClient"),
        patch("src.ui_pipeline.TestTableExpander") as mock_expander_cls,
    ):
        mock_expander_cls.return_value.expand_conditions.return_value = []
        result = build_test_table(
            plan=empty_plan,
            provider="ollama",
            provider_base_url="http://localhost:11434",
            model_name="m",
        )
    assert result.rows == []


def test_plan_rows_without_table_has_no_tests_column() -> None:
    rows = plan_rows_from_plan(_plan())
    assert "tests" not in rows[0]
    assert len(rows) == 2


def test_plan_rows_with_table_show_test_counts() -> None:
    rows = plan_rows_from_plan(_plan(), _table())
    by_id = {row["id"]: row for row in rows}
    assert by_id["TC01.03"]["tests"] == 2
    assert by_id["TC01.04"]["tests"] == 1


def test_plan_rows_extra_tests_key_ignored_by_plan_editor_round_trip() -> None:
    """The LTP editor feeds rows back through apply_editor_rows — the extra
    ``tests`` key must not break that path."""
    from src.test_plan import apply_editor_rows

    rows = plan_rows_from_plan(_plan(), _table())
    plan = apply_editor_rows(_plan(), rows)
    assert len(plan.conditions) == 2
    assert plan.conditions[0].id == "TC01.03"


def test_test_table_rows_editable_dicts() -> None:
    rows = ui_test_table_rows(_table())
    assert len(rows) == 3
    assert rows[0]["id"] == "T01"
    assert rows[0]["condition_ref"] == "TC01.03"
    assert rows[0]["expected_action"] == "SELECT"
    assert rows[0]["reviewed"] is True
    assert all("row_index" not in row for row in rows)  # presentation-only fields excluded


def test_test_table_rows_reviewed_flag_mirrors_confirmation() -> None:
    partial = TestTable(
        rows=[TestRow(id="T01", condition_ref="TC01.03", intent="Filter A-Z")],
        confirmed_ids=set(),
    )
    rows = ui_test_table_rows(partial)
    assert rows[0]["reviewed"] is False
