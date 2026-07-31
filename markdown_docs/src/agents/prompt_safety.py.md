# `src/agents/prompt_safety.py` — Safe Prompt Construction

## Purpose
Wraps dynamic user input in XML tags using Python t-strings (PEP 750) to prevent prompt injection and help the LLM distinguish developer-written structure from user-provided data.

## Function: `safe_prompt(template: str) -> str`
Wraps each template variable in `<variable_name>...</variable_name>` XML tags. Uses `string.Template`-style interpolation with `t` prefix.

## Usage
```python
from src.agents.prompt_safety import safe_prompt

prompt = safe_prompt(
    t"""<task>Generate tests for:</task>
<user_input>{user_story}</user_input>"""
)
```

## Related
- `src/agents/planner.py` — consumer
- `src/agents/generator.py` — consumer
- PEP 750 — Template Strings (t-strings)
