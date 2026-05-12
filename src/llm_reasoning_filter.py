"""Detect and strip LLM reasoning text from generated code.

Extracted from code_postprocessor.py to separate reasoning detection
into its own independently testable module.
"""

from __future__ import annotations

import re

__all__ = ["strip_llm_reasoning"]

# Patterns that match common LLM reasoning/thinking text that leaks into code output.
_LLM_REASONING_PREFIXES = (
    "Wait,",
    "Note,",
    "Actually,",
    "Hmm,",
    "Okay,",
    "Sure,",
    "Let's ",
    "That's ",
    "This is ",
    "The prompt ",
    "The example ",
    "I will ",
    "I need ",
    "I should ",
    "All constraints",
    "Matches all",
    "Output matches",
    "Proceeds",
    "Self-Correction",
    "Refinement",
    "One minor",
    "One check",
    "Final check",
    "Self check",
    "Edge case",
    "Corner case",
    "In the example",
    "To be safe",
    "To avoid",
)

_LLM_REASONING_PATTERNS = [
    re.compile(r"^\s*#\s*[A-Z][a-z]+,\s", re.IGNORECASE),
    re.compile(r"^\s*(?:Wait|Note|Actually|Hmm|Okay|Sure|Let's|That's|This is)\b", re.IGNORECASE),
    re.compile(r"^\s*# - \d+\.\s+[A-Z][a-z]+,\s"),
]

_BULLET_REASONING_PATTERNS = [
    re.compile(r"^\s*-?\s*\d+\.\s+[A-Z]"),
    re.compile(r"^\s*-\s+(Actually|Note|Wait|Hmm|Okay|Sure|Let's|That's|This is)\b", re.IGNORECASE),
    re.compile(r"^\s*-\s+(The prompt|The example|I will|I need|I should|All constraints)\b", re.IGNORECASE),
    re.compile(r"^\s*-\s+\d+-\d+\s+\w+", re.IGNORECASE),
    re.compile(r"^\s*-\s+\w+\s+(MAX|MIN|must|should|need)\b", re.IGNORECASE),
    re.compile(r"^\s*-\s+\(My test has", re.IGNORECASE),
    re.compile(r"^\s*-\s+\w+\s+(inside|inside,|within)\b", re.IGNORECASE),
]


def _is_llm_reasoning_line(line: str) -> bool:
    """Return True if the line looks like LLM reasoning text rather than Python code."""
    stripped = line.strip()
    if not stripped:
        return False

    python_keywords = (
        "def ",
        "class ",
        "import ",
        "from ",
        "return ",
        "if ",
        "elif ",
        "else:",
        "for ",
        "while ",
        "try:",
        "except",
        "finally:",
        "with ",
        "assert ",
        "raise ",
        "yield ",
        "lambda ",
        "pass",
        "break",
        "continue",
        "@pytest",
        "@",
        "# PAGES_NEEDED",
        "# - https",
        "# -http",
        '"""',
        "'''",
        "pytest.",
        "evidence_tracker",
        "dismiss_consent",
        "page.",
        "self.",
    )
    if any(stripped.startswith(kw) for kw in python_keywords):
        return False

    for prefix in _LLM_REASONING_PREFIXES:
        if stripped.startswith(prefix):
            return True

    for pattern in _LLM_REASONING_PATTERNS:
        if pattern.match(stripped):
            return True

    for pattern in _BULLET_REASONING_PATTERNS:
        if pattern.match(stripped):
            return True

    if len(stripped) < 80 and any(c in stripped for c in (",", ".")):
        if re.match(r"^[A-Z][a-z]+,", stripped):
            if not re.match(r"^[A-Z][A-Za-z]*\s*[:=]", stripped):
                return True

    return False


def strip_llm_reasoning(code: str) -> str:
    """Remove lines that look like LLM reasoning/thinking text.

    LLMs sometimes output their internal chain-of-thought as part of the code
    block. This function detects and removes such lines while preserving valid
    Python code, comments, and blank lines.
    """
    lines = code.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        if _is_llm_reasoning_line(line):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)
