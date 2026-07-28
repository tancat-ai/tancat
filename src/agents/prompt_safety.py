"""Safe prompt construction using Python t-strings (PEP 750).

Wraps dynamic user input in XML tags to:
1. Prevent prompt injection (user input can't override system instructions)
2. Help the LLM distinguish developer-written structure from user-provided data
3. Make prompt construction auditable — static vs dynamic parts are explicit
"""

from __future__ import annotations

from string.templatelib import Interpolation, Template


def safe_prompt(template: Template) -> str:
    """Build a prompt from a t-string template, wrapping interpolations in XML.

    Static text passes through unchanged.  Dynamic expressions (user data,
    criteria, counts) are wrapped in ``<user_input>`` tags so the LLM can
    distinguish developer-written instructions from untrusted input.

    Example::

        user_story = "Drop table users;"
        prompt = safe_prompt(t\"\"\"Generate tests for: {user_story}\"\"\")
        # → "Generate tests for: <user_input>Drop table users;</user_input>"
    """
    parts: list[str] = []
    for part in template:
        if isinstance(part, Interpolation):
            parts.append(f"<user_input>{part.value}</user_input>")
        else:
            parts.append(part)
    return "".join(parts)
