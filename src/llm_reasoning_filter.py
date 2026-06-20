"""Detect and strip LLM reasoning text from generated code.

Uses structural/format-based heuristics only — no hardcoded vocabulary lists.
Catches numbered bullets, range references, parenthetical notes, and long
conversational comment blocks that LLMs leak into code output.

Extracted from code_postprocessor.py to separate reasoning detection
into its own independently testable module.
"""

from __future__ import annotations

import re

__all__ = ["strip_llm_reasoning"]

# Structural patterns — match LLM reasoning by format, not vocabulary.
# Numbered bullet: "# - 1. Anything"
_RE_NUMBERED_BULLET = re.compile(r"^\s*#\s*-\s*\d+\.\s+\S")
# Range reference: "# - 1-2 ..."
_RE_RANGE_REF = re.compile(r"^\s*#\s*-\s*\d+-\d+\s+\S")
# Parenthetical note: "# - (My test has ..."
_RE_PAREN_NOTE = re.compile(r"^\s*#\s*-\s*\(", re.IGNORECASE)
# Requirement-style bullet: "# - ... MAX|MIN|must|should|need|needs"
_RE_REQUIREMENT_BULLET = re.compile(r"^\s*#\s*-\s+.*\b(?:MAX|MIN|must|should|need|needs)\b", re.IGNORECASE)
# Constraint-style bullet: "# - ... inside|within"
_RE_CONSTRAINT_BULLET = re.compile(r"^\s*#\s*-\s+.*\b(?:inside,?|within)\b", re.IGNORECASE)
# Sentence fragment: "CapitalizedWord," (not assignment like "Word, = value")
_RE_SENTENCE_FRAGMENT = re.compile(r"^[A-Z][a-z]+,")
_RE_SENTENCE_FRAGMENT_ASSIGNMENT = re.compile(r"^[A-Z][A-Za-z]*,\s*=")


def _is_structural_reasoning_line(stripped: str) -> bool:
    """Return True if the line matches a structural reasoning pattern."""
    for pattern in (
        _RE_NUMBERED_BULLET,
        _RE_RANGE_REF,
        _RE_PAREN_NOTE,
        _RE_REQUIREMENT_BULLET,
        _RE_CONSTRAINT_BULLET,
    ):
        if pattern.match(stripped):
            return True

    # Sentence fragment: "CapitalizedWord," that's not an assignment
    if _RE_SENTENCE_FRAGMENT.match(stripped):
        if not _RE_SENTENCE_FRAGMENT_ASSIGNMENT.match(stripped):
            return True

    return False


def _is_long_conversational_comment(stripped: str, comment_content: str) -> bool:
    """Return True if a long comment (>100 chars) reads like reasoning prose."""
    if len(comment_content) <= 100:
        return False

    # Check for multiple conversational indicators — requires at least 2
    # to avoid false positives on technical prose.
    conversational_indicators = (
        "we ",
        "i ",
        "you ",
        "let's",
        "let ",
        "should",
        "could",
        "would",
        "assume",
        "assuming",
        "cannot",
        "can't",
    )
    lower = comment_content.lower()
    hits = sum(1 for indicator in conversational_indicators if indicator in lower)
    return hits >= 2


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

    # For comment lines, strip the # prefix and check the content
    is_comment = stripped.startswith("#")
    comment_content = stripped[1:].lstrip() if is_comment else stripped

    if is_comment:
        # Keep valid comments: TODO, FIXME, noqa, pylint, type hints
        if comment_content.upper() in ("TODO", "FIXME", "HACK", "XXX", "NOQA", "TYPE:"):
            return False
        if comment_content.startswith("type:"):
            return False

    # Check structural patterns against the full line
    if _is_structural_reasoning_line(stripped):
        return True

    # Long conversational comments (paragraph reasoning)
    if _is_long_conversational_comment(stripped, comment_content):
        return True

    return False


def strip_llm_reasoning(code: str) -> str:
    """Remove lines that look like LLM reasoning/thinking text.

    LLMs sometimes output their internal chain-of-thought as part of the code
    block. This function detects and removes such lines while preserving valid
    Python code, comments, and blank lines.

    Uses only structural/format heuristics — no hardcoded word lists.
    """
    lines = code.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        if _is_llm_reasoning_line(line):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)
