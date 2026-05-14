"""Validate skeleton output for forbidden patterns (CSS selectors, XPath, etc.).

The SkeletonValidator ensures that LLM-generated test skeletons use ONLY placeholder
syntax ({{CLICK:description}}, {{FILL:description}}, etc.) and contain no real
locators. Real locators are resolved in Phase 2 by the placeholder resolver.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SkeletonValidationResult:
    """Result of validating a skeleton for forbidden patterns."""

    is_valid: bool
    violations: list[str]
    suggestion: str


class SkeletonValidator:
    """Validate skeleton output for forbidden patterns (CSS selectors, XPath, etc.)."""

    def _is_url_context(self, text: str) -> bool:
        """Check if the text contains a URL context (https://, http://)."""
        return "://" in text

    def _extract_string_args(self, line: str) -> list[str]:
        """Extract string arguments from a line of Python code."""
        strings: list[str] = []
        current = ""
        in_quote = None
        i = 0
        while i < len(line):
            ch = line[i]
            if in_quote is None:
                if ch in ('"', "'"):
                    in_quote = ch
                elif ch == " ":
                    if current.strip():
                        strings.append(current.strip())
                    current = ""
            else:
                if ch == in_quote and (i == 0 or line[i - 1] != "\\"):
                    strings.append(current)
                    current = ""
                    in_quote = None
                else:
                    current += ch
            i += 1
        if current.strip():
            strings.append(current.strip())
        return strings

    def validate(self, skeleton_code: str) -> SkeletonValidationResult:
        """Validate skeleton code for forbidden locator patterns.

        Returns a result indicating whether the skeleton is valid, what violations
        were found, and a suggestion for fixing them.
        """
        violations: list[str] = []

        # CSS class selector pattern
        css_class_pattern = re.compile(r"\.btn\.\w+")
        # CSS ID selector pattern
        css_id_pattern = re.compile(r"(?<!['\\])#\w+")
        # CSS attribute selector pattern
        css_attr_pattern = re.compile(r"\[href=")
        # XPath pattern — matches //tag but we'll filter URLs
        xpath_pattern = re.compile(r"(?<!['\\])//[a-zA-Z]")
        # CSS descendant combinator
        css_descendant_pattern = re.compile(r"\w+\s*>\s*\w+")
        # page.locator with real selector
        page_locator_pattern = re.compile(r"page\.locator\(['\"](?!{{)")
        # get_by_role/get_by_text with real selector
        get_by_pattern = re.compile(r"page\.(get_by_role|get_by_text|get_by_label)\(['\"]")

        for line in skeleton_code.splitlines():
            stripped = line.strip()
            # Skip comment lines, import lines, and lines with placeholders
            if stripped.startswith("#") or stripped.startswith("from ") or stripped.startswith("import "):
                continue
            if "{{" in line and "}}" in line:
                continue

            # Skip URL-only lines (e.g. evidence_tracker.navigate("https://..."))
            if self._is_url_context(line):
                # For XPath: URLs like https:// should NOT match
                # Check if the // is part of :// (URL scheme)
                if xpath_pattern.search(line):
                    # Filter out matches that are part of URL schemes
                    for m in xpath_pattern.finditer(line):
                        # Check if preceded by : (making it ://)
                        if m.start() > 0 and line[m.start() - 1] == ":":
                            continue  # This is part of a URL, skip
                        violations.append(f"Found XPath starting with //: {stripped[:120]}")
                        break
            else:
                if xpath_pattern.search(line):
                    violations.append(f"Found XPath starting with //: {stripped[:120]}")

            if css_class_pattern.search(line):
                violations.append(f"Found CSS class selector: {stripped[:120]}")
            if css_id_pattern.search(line):
                violations.append(f"Found CSS ID selector: {stripped[:120]}")
            if css_attr_pattern.search(line):
                violations.append(f"Found CSS attribute selector: {stripped[:120]}")
            if css_descendant_pattern.search(line):
                violations.append(f"Found CSS descendant combinator: {stripped[:120]}")
            if page_locator_pattern.search(line):
                violations.append(f"Found page.locator with real selector: {stripped[:120]}")
            if get_by_pattern.search(line):
                violations.append(f"Found get_by_role/get_by_text with real selector: {stripped[:120]}")

        if violations:
            unique_violations = list(dict.fromkeys(violations))  # Dedupe while preserving order
            suggestion = (
                "The skeleton contains real CSS selectors or XPath expressions. "
                "Replace ALL real locators with placeholders. "
                "Use {{CLICK:description}}, {{ASSERT:description}}, {{FILL:description}}, "
                "{{GOTO:description}}, or {{URL:description}} for ALL element interactions. "
                "The placeholder resolver will substitute real selectors during Phase 2."
            )
            return SkeletonValidationResult(
                is_valid=False,
                violations=unique_violations,
                suggestion=suggestion,
            )

        return SkeletonValidationResult(
            is_valid=True,
            violations=[],
            suggestion="",
        )
