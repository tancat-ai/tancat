"""Unit tests for the PEP 750 t-string prompt builder.

Verifies:
* double-brace skeleton placeholders survive as literal single-brace text;
* byte-identical equivalence with the existing ``.format()``-based skeleton prompt;
* per-field transforms (truncation) keyed by interpolation expression;
* structured render metadata (fields, truncated, parts) for audit logging.
"""

from __future__ import annotations

from string.templatelib import Template

import pytest

from src.prompt_builder import (
    PromptBuilder,
    RenderedPrompt,
    build_single_condition_prompt,
    build_skeleton_prompt,
    truncate,
)
from src.prompt_utils import (
    build_single_condition_skeleton_prompt,
    get_skeleton_prompt_template,
)

STORY = "As a customer I want a Honda CR-V insurance quote"
CONDITIONS = "1. Create account\n2. Select Car Insurance\n3. Enter policy details"
URLS = "- http://localhost:8781/generated_tests/mock_insurance_site.html"


def _render(template: Template) -> RenderedPrompt:
    return PromptBuilder(template).render()


# ---------------------------------------------------------------------------
# Double-brace survival
# ---------------------------------------------------------------------------


def test_double_brace_placeholders_render_as_single_braces() -> None:
    """{{CLICK:...}} must render as literal {CLICK:...} — same as .format()."""
    rendered = _render(build_skeleton_prompt(user_story=STORY, conditions=CONDITIONS, known_urls_block=URLS))
    assert "{{CLICK:Login}}" not in rendered.text
    assert "{CLICK:Login}" in rendered.text
    assert "{GOTO:home}" in rendered.text
    assert "{FILL:username:admin}" in rendered.text


def test_skeleton_prompt_returns_template_object() -> None:
    """build_skeleton_prompt must return a Template, not a str."""
    template = build_skeleton_prompt(user_story=STORY, conditions=CONDITIONS, known_urls_block=URLS)
    assert isinstance(template, Template)


# ---------------------------------------------------------------------------
# Equivalence with existing .format() implementation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expected_count", [None, 6])
def test_skeleton_prompt_byte_identical_to_format_version(expected_count: int | None) -> None:
    """The t-string skeleton prompt must render byte-identical to the legacy one."""
    legacy = get_skeleton_prompt_template(expected_count=expected_count).format(
        user_story=STORY,
        conditions=CONDITIONS,
        known_urls_block=URLS,
    )
    new = _render(
        build_skeleton_prompt(
            user_story=STORY,
            conditions=CONDITIONS,
            known_urls_block=URLS,
            expected_count=expected_count,
        )
    ).text
    assert new == legacy


def test_skeleton_prompt_count_header() -> None:
    """EXACTLY N header must be injected when a count is given."""
    rendered = _render(
        build_skeleton_prompt(user_story=STORY, conditions=CONDITIONS, known_urls_block=URLS, expected_count=6)
    ).text
    assert "EXACTLY 6 test functions" in rendered
    assert "Generate the 6 test functions now." in rendered


def test_single_condition_prompt_matches_legacy_modulo_brace_normalisation() -> None:
    """Single-condition prompt must match legacy text except brace normalisation.

    The legacy function used plain string concatenation and sent literal
    ``{{CLICK:...}}`` (double braces) — inconsistent with the skeleton prompt,
    which renders single braces. The t-string version normalises to single
    braces, matching the parser's accepted forms and the primary prompt path.
    """
    ordered = ["1. Create account", "2. Select Car Insurance"]
    legacy = build_single_condition_skeleton_prompt(
        user_story=STORY,
        known_urls_block=URLS,
        ordered_conditions=ordered,
        target_condition_ref="TC-01",
        target_condition_text="Create account",
        target_condition_expected="Account created",
    )
    new = _render(
        build_single_condition_prompt(
            user_story=STORY,
            conditions_block="\n".join(f"- {c}" for c in ordered),
            known_urls_block=URLS,
            target_condition_ref="TC-01",
            target_condition_text="Create account",
            target_condition_expected="Account created",
        )
    ).text
    # The only allowed difference: legacy double-brace → new single-brace.
    assert new == legacy.replace("{{", "{").replace("}}", "}")
    assert "{CLICK:description}" in new


# ---------------------------------------------------------------------------
# Per-field transforms
# ---------------------------------------------------------------------------


def test_truncation_applied_per_field() -> None:
    """Long user_story values must be truncated and recorded."""
    long_story = "x" * 20000
    rendered = _render(build_skeleton_prompt(user_story=long_story, conditions=CONDITIONS, known_urls_block=URLS))
    assert len(rendered.text) < len(STORY) + 20000  # truncated, not full length
    assert "truncated" in rendered.text
    assert "user_story" in rendered.truncated
    # Raw value preserved in fields metadata
    assert rendered.fields["user_story"] == long_story


def test_short_values_not_truncated() -> None:
    """Values within limits pass through unchanged and are not flagged."""
    rendered = _render(build_skeleton_prompt(user_story=STORY, conditions=CONDITIONS, known_urls_block=URLS))
    assert rendered.truncated == []
    assert STORY in rendered.text


def test_unknown_expression_falls_back_to_str() -> None:
    """Interpolations without a registered transform render via str()."""
    rendered = _render(
        build_single_condition_prompt(
            user_story=STORY,
            conditions_block="- 1. Create account",
            known_urls_block=URLS,
            target_condition_ref="TC-01",
            target_condition_text="Create account",
            target_condition_expected="Account created",
        )
    )
    assert rendered.fields["target_condition_ref"] == "TC-01"
    assert "ID: TC-01" in rendered.text


def test_custom_transform_override() -> None:
    """A caller-supplied transform must take precedence over the default."""
    template = build_skeleton_prompt(user_story=STORY, conditions=CONDITIONS, known_urls_block=URLS)
    rendered = PromptBuilder(template, transforms={"user_story": lambda v: "REDACTED"}).render()
    assert "REDACTED" in rendered.text
    assert STORY not in rendered.text


def test_truncate_helper() -> None:
    """truncate() keeps short text and marks long text."""
    assert truncate("short", 100) == "short"
    long = truncate("x" * 100, 10)
    assert len(long) == 10 + len("\n... (truncated)")
    assert long.endswith("(truncated)")


# ---------------------------------------------------------------------------
# Structured metadata (audit logging separation)
# ---------------------------------------------------------------------------


def test_fields_and_parts_split() -> None:
    """Render output must record trusted static parts vs untrusted fields."""
    rendered = _render(build_skeleton_prompt(user_story=STORY, conditions=CONDITIONS, known_urls_block=URLS))
    kinds = {kind for kind, _ in rendered.parts}
    assert kinds == {"static", "field"}
    assert set(rendered.fields) == {"count_label", "user_story", "conditions", "known_urls_block"}
    # Static parts contain instructions; field parts contain data
    static_text = "".join(v for kind, v in rendered.parts if kind == "static")
    assert "You are a Playwright Python test engineer" in static_text
    assert "INSTRUCTIONS" in static_text


def test_to_log_entry_is_json_serialisable() -> None:
    """to_log_entry() must produce a plain dict for structured logging."""
    rendered = _render(build_skeleton_prompt(user_story=STORY, conditions=CONDITIONS, known_urls_block=URLS))
    entry = rendered.to_log_entry()
    assert entry["prompt_len"] == len(rendered.text)
    assert entry["fields"]["user_story"] == STORY
    assert entry["truncated"] == []
    assert "static_parts" in entry
    assert "field_order" in entry
    # JSON round-trip must succeed (all values str/int/list/dict)
    import json

    json.dumps(entry)
