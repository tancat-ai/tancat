"""Living test plan models and helpers for tester review/sign-off."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import cast

from src.spec_analyzer import ConditionIntent, TestCondition, infer_condition_intent


@dataclass(frozen=True)
class TestPlan:
    """Tester-reviewed plan of conditions before generation is allowed."""

    __test__ = False

    story_ref: str
    sprint: str
    conditions: list[TestCondition] = field(default_factory=list)
    confirmed_ids: set[str] = field(default_factory=set)
    sign_off_notes: str = ""
    tester_name: str = ""
    sign_off_date: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/session-state friendly representation."""
        return {
            "story_ref": self.story_ref,
            "sprint": self.sprint,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "confirmed_ids": sorted(self.confirmed_ids),
            "sign_off_notes": self.sign_off_notes,
            "tester_name": self.tester_name,
            "sign_off_date": self.sign_off_date,
        }

    @classmethod
    def from_conditions(
        cls,
        *,
        story_ref: str,
        sprint: str,
        conditions: list[TestCondition],
    ) -> TestPlan:
        """Create a plan from analyzed conditions."""
        return cls(
            story_ref=story_ref,
            sprint=sprint,
            conditions=list(conditions),
        )

    @property
    def condition_ids(self) -> set[str]:
        """Return all condition ids currently in the plan."""
        return {condition.id for condition in self.conditions}

    @property
    def reviewed_ids(self) -> set[str]:
        """Return confirmed ids that still exist in the plan."""
        return self.confirmed_ids.intersection(self.condition_ids)

    @property
    def unreviewed_ids(self) -> set[str]:
        """Return condition ids that still need explicit confirmation."""
        return self.condition_ids.difference(self.reviewed_ids)

    @property
    def is_ready_for_generation(self) -> bool:
        """Return True when all conditions are reviewed and sign-off is complete."""
        return (
            bool(self.conditions)
            and not self.unreviewed_ids
            and bool(self.tester_name.strip())
            and bool(self.sign_off_date.strip())
        )

    def replace_condition(self, condition_id: str, updated_condition: TestCondition) -> TestPlan:
        """Replace one condition by id."""
        updated_conditions = [
            updated_condition if condition.id == condition_id else condition for condition in self.conditions
        ]
        return replace(self, conditions=updated_conditions)

    def confirm(self, condition_id: str, *, confirmed: bool = True) -> TestPlan:
        """Mark one condition reviewed or unreviewed."""
        updated_confirmed_ids = set(self.reviewed_ids)
        if confirmed and condition_id in self.condition_ids:
            updated_confirmed_ids.add(condition_id)
        else:
            updated_confirmed_ids.discard(condition_id)
        return replace(self, confirmed_ids=updated_confirmed_ids)

    def remove_condition(self, condition_id: str) -> TestPlan:
        """Remove one condition and any stale confirmation entry."""
        updated_conditions = [condition for condition in self.conditions if condition.id != condition_id]
        updated_confirmed_ids = {cid for cid in self.reviewed_ids if cid != condition_id}
        return replace(self, conditions=updated_conditions, confirmed_ids=updated_confirmed_ids)

    def add_condition(self, condition: TestCondition, *, confirmed: bool = False) -> TestPlan:
        """Append a new condition to the plan."""
        updated_conditions = [*self.conditions, condition]
        updated_confirmed_ids = set(self.reviewed_ids)
        if confirmed:
            updated_confirmed_ids.add(condition.id)
        return replace(self, conditions=updated_conditions, confirmed_ids=updated_confirmed_ids)

    def sign_off(self, *, tester_name: str, sign_off_notes: str = "", sign_off_date: str | None = None) -> TestPlan:
        """Apply tester sign-off metadata."""
        resolved_sign_off_date = sign_off_date or date.today().isoformat()
        return replace(
            self,
            tester_name=tester_name.strip(),
            sign_off_notes=sign_off_notes.strip(),
            sign_off_date=resolved_sign_off_date,
        )


def build_story_ref(user_story: str) -> str:
    """Derive a stable story reference from user-story text."""
    cleaned = " ".join(part for part in user_story.strip().split() if part)
    if not cleaned:
        return "story_unknown"

    words = [part.lower() for part in cleaned.replace(",", " ").replace(".", " ").split() if part]
    filtered_words = [word for word in words if word not in {"as", "a", "an", "the", "i", "want", "to"}]
    slug_parts = filtered_words[:5] or ["story"]
    return "story_" + "_".join(slug_parts)


def next_condition_id(existing_conditions: list[TestCondition], *, prefix: str = "MAN") -> str:
    """Return the next sequential manual condition id."""
    max_suffix = 0
    for condition in existing_conditions:
        if not condition.id.startswith(prefix):
            continue
        suffix = condition.id.removeprefix(prefix)
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))
    return f"{prefix}{max_suffix + 1:02d}"


def build_manual_condition(
    *,
    existing_conditions: list[TestCondition],
    text: str,
    expected: str,
    source: str,
    condition_type: str = "exploratory",
    flagged: bool = False,
    src: str = "manual",
    intent: str | None = None,
) -> TestCondition:
    """Return a new tester-authored condition with a stable id."""
    return TestCondition(
        id=next_condition_id(existing_conditions),
        type=condition_type,  # type: ignore[arg-type]
        text=text.strip(),
        expected=expected.strip(),
        source=source.strip(),
        flagged=flagged,
        src=src,  # type: ignore[arg-type]
        intent=cast(ConditionIntent, intent or infer_condition_intent(text)),
    )


def apply_editor_rows(plan: TestPlan, rows: list[dict[str, object]]) -> TestPlan:
    """Return a plan updated from editable table rows."""
    allowed_types = {"happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"}
    allowed_sources = {"ai", "manual", "automation"}
    allowed_intents = {
        "element_presence",
        "element_behavior",
        "state_assertion",
        "journey_step",
        "journey_outcome",
    }
    updated_conditions: list[TestCondition] = []
    updated_confirmed_ids: set[str] = set()

    for row in rows:
        condition_id = str(row.get("id", "")).strip()
        if not condition_id:
            condition_id = next_condition_id(updated_conditions)

        condition_type = str(row.get("type", "happy_path")).strip() or "happy_path"
        if condition_type not in allowed_types:
            condition_type = "happy_path"

        condition_src = str(row.get("src", "manual")).strip() or "manual"
        if condition_src not in allowed_sources:
            condition_src = "manual"

        condition_intent = str(row.get("intent", "")).strip()
        if condition_intent not in allowed_intents:
            condition_intent = infer_condition_intent(str(row.get("text", "")))

        condition = TestCondition(
            id=condition_id,
            type=condition_type,  # type: ignore[arg-type]
            text=str(row.get("text", "")).strip(),
            expected=str(row.get("expected", "")).strip(),
            source=str(row.get("source", "")).strip(),
            flagged=bool(row.get("flagged", False)),
            src=condition_src,  # type: ignore[arg-type]
            intent=cast(ConditionIntent, condition_intent),
        )
        updated_conditions.append(condition)

        if bool(row.get("reviewed", False)):
            updated_confirmed_ids.add(condition.id)

    return replace(
        plan,
        conditions=updated_conditions,
        confirmed_ids=updated_confirmed_ids,
    )
