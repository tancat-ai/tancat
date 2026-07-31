"""PEP 750 t-string based prompt assembly for LLM calls.

Separates **trusted static prompt structure** from **untrusted interpolated
values** so rendering can:

* apply per-field safety transforms (truncation, sanitation) keyed by the
  interpolation's source expression (``Interpolation.expression``);
* record exactly what was sent to the LLM — the prompt text *and* a structured
  log entry (which fields, which values, which were truncated);
* render the *same* template differently for different consumers (LLM prompt
  vs. human-readable debug vs. structured audit), the way the structured
  logging example in PEP 750 emits text to stdout and JSON to stderr.

LangChain parallel: ``PromptTemplate`` declares variables + a text template and
``.format(**values)`` substitutes blindly. Here the template is a ``t"..."``
``Template`` with interpolations keyed by their source expression; ``PromptBuilder
.render()`` is the ``.format()`` step but with per-field transforms and structured
metadata instead of blind ``str`` substitution. The template structure lives in
code at compile time (no runtime template parsing), and double-brace
``{{CLICK:...}}`` skeleton placeholders survive as literal single-brace text —
identical to the existing ``.format()`` behaviour.

Requires Python 3.14+ (``string.templatelib``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from string.templatelib import Interpolation, Template
from typing import Any

__all__ = [
    "PromptBuilder",
    "RenderedPrompt",
    "build_skeleton_prompt",
    "build_single_condition_prompt",
    "truncate",
]

# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

#: Per-expression truncation limits (chars). Field names come from the source
#: expression of each interpolation, e.g. ``{user_story}`` → ``"user_story"``.
TRUNCATION_LIMITS: dict[str, int] = {
    "user_story": 8000,
    "conditions": 15000,
    "conditions_block": 15000,
    "known_urls_block": 4000,
}


def truncate(text: str, limit: int) -> str:
    """Truncate *text* to *limit* chars with a visible suffix marker."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncated)"


def _default_transform(value: Any) -> str:
    """Default transform: render any value as a plain string."""
    return str(value)


def _make_transform(expr: str) -> Callable[[Any], str]:
    """Build a per-field transform for expression *expr*."""
    limit = TRUNCATION_LIMITS.get(expr)
    if limit is None:
        return _default_transform

    def _transform(value: Any) -> str:
        return truncate(str(value), limit)

    return _transform


# ---------------------------------------------------------------------------
# Render result
# ---------------------------------------------------------------------------


@dataclass
class RenderedPrompt:
    """The result of rendering a template: text + structured metadata.

    Attributes:
        text: The final prompt string sent to the LLM.
        fields: Mapping of interpolation expression → raw (pre-transform) value.
        truncated: Expressions whose values were truncated during render.
        parts: Ordered list of ``("static" | "field", value)`` tuples — the
            trusted/untrusted split, useful for audit and debug rendering.
    """

    text: str
    fields: dict[str, Any] = field(default_factory=dict)
    truncated: list[str] = field(default_factory=list)
    parts: list[tuple[str, Any]] = field(default_factory=list)

    def to_log_entry(self) -> dict[str, Any]:
        """Return a JSON-serialisable audit entry for this prompt."""
        return {
            "prompt_len": len(self.text),
            "fields": {k: str(v) for k, v in self.fields.items()},
            "truncated": list(self.truncated),
            "static_parts": [v for kind, v in self.parts if kind == "static"],
            "field_order": [expr for expr, _ in self.fields.items()],
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class PromptBuilder:
    """Render a ``Template`` with per-field transforms and structured output.

    Example::

        template = build_skeleton_prompt(
            user_story=story,
            conditions=conditions,
            known_urls_block=urls,
            expected_count=6,
        )
        rendered = PromptBuilder(template).render()
        await client.generate(rendered.text)          # → LLM
        audit_log.info("llm_call", extra=rendered.to_log_entry())  # → structured store
    """

    def __init__(
        self,
        template: Template,
        *,
        transforms: Mapping[str, Callable[[Any], str]] | None = None,
    ) -> None:
        self._template = template
        # Expression → transform; unknown expressions fall back to str().
        self._transforms: dict[str, Callable[[Any], str]] = dict(transforms) if transforms is not None else {}

    def render(self) -> RenderedPrompt:
        """Render the template, transforming each interpolation by field name."""
        parts: list[tuple[str, Any]] = []
        fields: dict[str, Any] = {}
        truncated: list[str] = []
        rendered_chunks: list[str] = []

        for part in self._template:
            if isinstance(part, Interpolation):
                expr = part.expression
                transform = self._transforms.get(expr, _make_transform(expr))
                rendered = transform(part.value)
                if TRUNCATION_LIMITS.get(expr) is not None and len(rendered) != len(str(part.value)):
                    truncated.append(expr)
                fields[expr] = part.value
                parts.append(("field", rendered))
                rendered_chunks.append(rendered)
            else:
                parts.append(("static", part))
                rendered_chunks.append(part)

        return RenderedPrompt(
            text="".join(rendered_chunks),
            fields=fields,
            truncated=truncated,
            parts=parts,
        )


# ---------------------------------------------------------------------------
# Prompt templates (t-strings — double-brace placeholders stay literal)
# ---------------------------------------------------------------------------


def build_skeleton_prompt(
    *,
    user_story: str,
    conditions: str,
    known_urls_block: str,
    expected_count: int | None = None,
) -> Template:
    """Return the Phase 1 skeleton-generation prompt as a ``Template``.

    Rendered output is byte-identical to
    ``get_skeleton_prompt_template(expected_count=...).format(...)``.
    """
    count_label = str(expected_count) if expected_count is not None else "N"

    return t"""You are a Playwright Python test engineer.

=== INSTRUCTIONS ===
Generate EXACTLY {count_label} test functions. One per criterion.
Use ONLY the double-brace placeholder format for test steps.
NO PROSE. NO EXPLANATIONS. START WITH IMPORTS.

=== ALLOWED STEP FORMATS ===
{{GOTO:page keyword}}
{{CLICK:button or link description}}
{{FILL:input field description:value to type}}
{{ASSERT:what should be visible or true (describe the content/state, not just 'element visible')}}

=== PLACEHOLDER DESCRIPTION RULES ===
1. Keep descriptions SHORT (2-5 words). Use the element's visible text or label.
2. For CLICK: use the button/link text, e.g. {{CLICK:Login}}, {{CLICK:Dress}}, {{CLICK:Add to cart}}
3. For FILL: use the field label, e.g. {{FILL:username:admin}}, {{FILL:password:secret}}
4. For ASSERT: describe what to see, e.g. {{ASSERT:product list}}, {{ASSERT:cart total}}, {{ASSERT:welcome message}}
5. For GOTO: use a keyword, e.g. {{GOTO:home}}, {{GOTO:cart}}, {{GOTO:checkout}}
6. DO NOT write long descriptions like 'the button that says Add to cart next to the Blue Top product'.
   Instead write: {{CLICK:Add to cart}}
7. DO NOT write vague descriptions like 'some element is visible on the page'.
   Instead write: {{ASSERT:product list}} or {{ASSERT:Cart Summary}}

=== PREREQUISITE STEPS ===
Each test must be self-contained. If a test depends on earlier criteria
being completed first (e.g., you must log in before adding items to cart),
include those prerequisite steps at the start of the test function.

=== EXAMPLE OUTPUT ===
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_example(page, evidence_tracker):
    {{GOTO:home}}
    {{FILL:username:admin}}
    {{CLICK:submit button}}
    {{ASSERT:welcome message}}

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_example(page, evidence_tracker):
    {{GOTO:home}}
    {{FILL:username:admin}}
    {{CLICK:submit button}}
    {{CLICK:add to cart button}}
    {{ASSERT:cart badge updated}}

=== USER STORY ===
{user_story}

=== ACCEPTANCE CRITERIA ===
{conditions}

=== KNOWN URLS ===
{known_urls_block}

Generate the {count_label} test functions now."""


def build_single_condition_prompt(
    *,
    user_story: str,
    conditions_block: str,
    known_urls_block: str,
    target_condition_ref: str,
    target_condition_text: str,
    target_condition_expected: str,
) -> Template:
    """Return the per-condition skeleton-fragment prompt as a ``Template``.

    Mirrors ``build_single_condition_skeleton_prompt`` (conditions_block is
    pre-joined by the caller).
    """
    return t"""You are a Playwright Python test engineer.

Generate EXACTLY ONE pytest test function for the target condition below.

=== TARGET CONDITION ===
ID: {target_condition_ref}
Description: {target_condition_text}
Expected: {target_condition_expected}

=== MANDATORY OUTPUT FORMAT ===
1. Output ONLY the test function code. NO PROSE.
2. Use ONLY standalone double-brace placeholders inside the test.
3. Every line in the test body must be a placeholder like {{CLICK:description}}.

=== ALLOWED PLACEHOLDERS ===
{{GOTO:url or description}}
{{CLICK:element description}}
{{FILL:element description:value to type}}
{{ASSERT:what should be visible or true (describe the content/state, not just 'element visible')}}

=== PLACEHOLDER DESCRIPTION RULES ===
1. Keep descriptions SHORT (2-5 words). Use the element's visible text.
2. For CLICK: {{CLICK:Login}}, {{CLICK:Dress}}, {{CLICK:Add to cart}}
3. For FILL: {{FILL:username:admin}}, {{FILL:email:test@example.com}}
4. For ASSERT: {{ASSERT:product list}}, {{ASSERT:Cart Summary}}
5. DO NOT write long verbose descriptions — use short, concrete element labels.

=== USER STORY ===
{user_story}

=== ALL CONDITIONS (FOR CONTEXT) ===
{conditions_block}

=== KNOWN TARGET URLS ===
{known_urls_block}

Generate the test function for {target_condition_ref} now."""
