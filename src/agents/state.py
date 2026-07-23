"""Pydantic workflow state for the LangGraph skeleton generation pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowState(BaseModel):
    """Serialisable workflow state passed between agent nodes.

    Each node reads from and writes to this state.  LangGraph persists
    the state across LLM calls so retries restart from the last checkpoint.
    """

    user_story: str = Field(default="", description="User story text (e.g. 'As a user I want to...')")
    conditions: str = Field(default="", description="Numbered acceptance criteria")
    target_urls: list[str] = Field(default_factory=list, description="Known target URLs for the test")
    expected_test_count: int = Field(default=0, description="Number of criteria → expected test functions")

    # Optional: pre-scraped DOM for the planner (future: vision model input)
    raw_dom_snapshot: str = Field(default="", description="Pre-scraped DOM snapshot (optional)")

    # Planner output
    test_plan: str = Field(
        default="",
        description="Planned test structure as Markdown: one section per criterion with steps",
    )

    # Generator output
    skeleton_code: str = Field(default="", description="Generated pytest skeleton with placeholders")

    # Validator feedback
    validation_errors: list[str] = Field(
        default_factory=list,
        description="Errors found by the validator (empty list = valid)",
    )

    # Retry control
    retry_count: int = Field(default=0, description="Number of retries attempted so far")
    max_retries: int = Field(default=2, description="Maximum generator→validator retry cycles")
