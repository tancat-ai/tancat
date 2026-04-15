"""Unit tests for the living test plan helpers."""

from src.spec_analyzer import TestCondition
from src.test_plan import TestPlan, apply_editor_rows, build_manual_condition, build_story_ref, next_condition_id


def _condition(
    condition_id: str,
    *,
    text: str = "Condition",
    expected: str = "Expected",
    source: str = "Spec",
) -> TestCondition:
    return TestCondition(
        id=condition_id,
        type="happy_path",
        text=text,
        expected=expected,
        source=source,
        flagged=False,
        src="ai",
    )


def test_build_story_ref_uses_user_story_words() -> None:
    assert build_story_ref("As a customer I want to add items to cart") == "story_customer_add_items_cart"


def test_next_condition_id_ignores_non_manual_ids() -> None:
    condition_id = next_condition_id([_condition("TC01.01"), _condition("MAN02"), _condition("MAN09")])
    assert condition_id == "MAN10"


def test_build_manual_condition_assigns_next_manual_id() -> None:
    condition = build_manual_condition(
        existing_conditions=[_condition("MAN01"), _condition("TC01.01")],
        text="Tester adds a clarification case",
        expected="The plan keeps the new test",
        source="Manual review",
    )

    assert condition.id == "MAN02"
    assert condition.type == "exploratory"
    assert condition.src == "manual"


def test_test_plan_tracks_review_state_and_signoff_readiness() -> None:
    plan = TestPlan.from_conditions(
        story_ref="story_checkout",
        sprint="Sprint 1",
        conditions=[_condition("TC01.01"), _condition("TC01.02")],
    )

    assert plan.is_ready_for_generation is False
    reviewed = plan.confirm("TC01.01").confirm("TC01.02")
    assert reviewed.reviewed_ids == {"TC01.01", "TC01.02"}
    assert reviewed.is_ready_for_generation is False

    signed = reviewed.sign_off(tester_name="Lee", sign_off_notes="Ready to generate", sign_off_date="2026-04-15")
    assert signed.is_ready_for_generation is True
    assert signed.sign_off_date == "2026-04-15"


def test_test_plan_replace_remove_and_add_keep_confirmations_consistent() -> None:
    plan = TestPlan.from_conditions(
        story_ref="story_checkout",
        sprint="Sprint 1",
        conditions=[_condition("TC01.01"), _condition("TC01.02")],
    ).confirm("TC01.01")

    replaced = plan.replace_condition("TC01.01", _condition("TC01.01", text="Updated"))
    assert replaced.conditions[0].text == "Updated"
    assert replaced.reviewed_ids == {"TC01.01"}

    removed = replaced.remove_condition("TC01.01")
    assert [condition.id for condition in removed.conditions] == ["TC01.02"]
    assert removed.reviewed_ids == set()

    added = removed.add_condition(_condition("MAN01", text="Manual check"), confirmed=True)
    assert [condition.id for condition in added.conditions] == ["TC01.02", "MAN01"]
    assert added.reviewed_ids == {"MAN01"}


def test_test_plan_to_dict_serializes_conditions_and_confirmed_ids() -> None:
    plan = (
        TestPlan.from_conditions(
            story_ref="story_checkout",
            sprint="Sprint 1",
            conditions=[_condition("TC01.01")],
        )
        .confirm("TC01.01")
        .sign_off(tester_name="Lee", sign_off_date="2026-04-15")
    )

    payload = plan.to_dict()

    assert payload["story_ref"] == "story_checkout"
    assert payload["confirmed_ids"] == ["TC01.01"]
    conditions = payload["conditions"]
    assert isinstance(conditions, list)
    assert conditions[0]["id"] == "TC01.01"


def test_apply_editor_rows_updates_conditions_assigns_ids_and_review_state() -> None:
    plan = TestPlan.from_conditions(
        story_ref="story_checkout",
        sprint="Sprint 1",
        conditions=[_condition("TC01.01")],
    )

    updated = apply_editor_rows(
        plan,
        [
            {
                "id": "TC01.01",
                "type": "boundary",
                "text": "Updated condition",
                "expected": "Updated expected",
                "source": "Edited",
                "flagged": True,
                "src": "manual",
                "reviewed": True,
            },
            {
                "id": "",
                "type": "exploratory",
                "text": "New manual condition",
                "expected": "Saved",
                "source": "Tester",
                "flagged": False,
                "src": "manual",
                "reviewed": False,
            },
        ],
    )

    assert [condition.id for condition in updated.conditions] == ["TC01.01", "MAN01"]
    assert updated.conditions[0].type == "boundary"
    assert updated.reviewed_ids == {"TC01.01"}
