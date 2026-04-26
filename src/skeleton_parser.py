"""Parse placeholder-based skeleton code produced by the intelligent pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep


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


class SkeletonParser:
    """Extract placeholders and required URLs from generated skeletons."""

    def __init__(self) -> None:
        self.placeholder_pattern = re.compile(r"\{\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}\}")
        self.any_double_brace_placeholder_pattern = re.compile(r"\{\{([A-Z_]+):([^}]+)\}\}")
        self.pages_pattern = re.compile(r"#\s*[-*]?\s*`?(https?://[^`\s]+)`?(?:\s+\((.*?)\))?")
        self.single_brace_placeholder_pattern = re.compile(r"(?<!\{)\{(CLICK|FILL|GOTO|URL|ASSERT):([^}]+)\}(?!\})")
        self.test_definition_pattern = re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.M)
        self.page_object_reference_pattern = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\s*\(")

    @staticmethod
    def normalise_placeholder_actions(code: str) -> str:
        """Rewrite common placeholder action synonyms into the allowed action set.

        The LLM sometimes emits verbs like ADD/REMOVE/SELECT/SUBMIT. The pipeline only
        supports CLICK/FILL/GOTO/URL/ASSERT, so we conservatively map synonyms.
        """
        # Step 1: Convert single-brace placeholders to double-brace first.
        # LLMs trained on Python f-strings interpret {{ as an escaped literal brace,
        # so they frequently emit {ACTION:desc} when the prompt shows {{ACTION:desc}}.
        code = SkeletonParser._single_to_double_brace(code)

        # Step 2: Rewrite action synonyms (ADD->CLICK, VERIFY->ASSERT, etc.)
        aliases: dict[str, str] = {
            # navigation synonyms
            "NAVIGATE": "GOTO",
            "GO": "GOTO",
            "OPEN": "GOTO",
            "VISIT": "GOTO",
            # click-like verbs
            "ADD": "CLICK",
            "REMOVE": "CLICK",
            "DELETE": "CLICK",
            "SUBMIT": "CLICK",
            "PRESS": "CLICK",
            "TAP": "CLICK",
            "SELECT": "CLICK",
            "CHOOSE": "CLICK",
            # assertion-like verbs
            "VERIFY": "ASSERT",
            "CHECK": "ASSERT",
            "CONFIRM": "ASSERT",
            "ENSURE": "ASSERT",
            # fill-like verbs
            "TYPE": "FILL",
            "ENTER": "FILL",
        }

        def _rewrite(match: re.Match[str]) -> str:
            action = match.group(1)
            # Normalise whitespace inside placeholders so token matching works even if
            # the model emits `{{CLICK:thing }}` with trailing spaces.
            description = match.group(2).strip()
            mapped = aliases.get(action, action)
            return f"{{{{{mapped}:{description}}}}}"

        # Replace any double-brace placeholder actions we recognize.
        code = re.sub(r"\{\{([A-Z_]+):([^}]+)\}\}", _rewrite, code)

        # CRITICAL: Also handle single-brace placeholders that were NOT caught
        # by _single_to_double_brace. This catches cases where the LLM writes
        # {CLICK:x} or {FILL:x} with single braces.
        code = re.sub(r"(?<!\{)\{([A-Z_]+):([^}]+)\}(?!\})", _rewrite, code)

        return SkeletonParser._replace_unsupported_placeholder_actions(code)

    @staticmethod
    def _replace_unsupported_placeholder_actions(code: str) -> str:
        """Replace unsupported placeholder-action lines with standalone pytest skips.

        This keeps the pipeline runnable when the model echoes teaching examples like
        ``{{ACTION:description}}`` or invents unsupported actions such as WAIT/CLOSE.
        """
        allowed_actions = {"CLICK", "FILL", "GOTO", "URL", "ASSERT"}
        placeholder_pattern = re.compile(r"\{\{([A-Z_]+):(.+?)\}\}", re.DOTALL)

        def _is_inside_quotes(text_before: str) -> bool:
            in_single = False
            in_double = False
            for ch in text_before:
                if ch == "'" and not in_double:
                    in_single = not in_single
                elif ch == '"' and not in_single:
                    in_double = not in_double
            return in_single or in_double

        output_lines: list[str] = []
        for line in code.splitlines():
            if "{{" not in line:
                output_lines.append(line)
                continue

            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                output_lines.append(line)
                continue

            matches = list(placeholder_pattern.finditer(stripped))
            unsupported = [
                match
                for match in matches
                if match.group(1) not in allowed_actions and not _is_inside_quotes(stripped[: match.start()])
            ]
            if not unsupported:
                output_lines.append(line)
                continue

            indent = line[: len(line) - len(line.lstrip())]
            preview = ", ".join(match.group(1) for match in unsupported[:3])
            reason = f"Unsupported placeholder action emitted by model: {preview}."
            output_lines.append(f"{indent}pytest.skip({reason!r})")

        return "\n".join(output_lines)

    @staticmethod
    def _single_to_double_brace(code: str) -> str:
        """Convert single-brace placeholders {ACTION:desc} to double-brace {{ACTION:desc}}.

        LLMs trained on Python f-strings interpret {{ as an escaped literal brace,
        so they frequently emit {ACTION:desc} when the prompt shows {{ACTION:desc}}.
        This method repairs that common mistake.

        IMPORTANT: Uses a WILD CARD pattern ([A-Z_]+) to match ANY uppercase action,
        not just the five allowed actions. This catches synonyms like VERIFY, CHECK,
        NAVIGATE, etc. that the LLM may emit. The action synonym mapping in
        normalise_placeholder_actions handles the actual conversion afterwards.
        """
        single_pattern = re.compile(r"(?<!\{)\{([A-Z_]+):([^}]+)\}(?!\})")

        def _convert(match: re.Match) -> str:
            action = match.group(1)
            description = match.group(2).strip()
            return f"{{{{{action}:{description}}}}}"

        return single_pattern.sub(_convert, code)

    def parse_placeholders(self, code: str) -> list[tuple[str, str]]:
        """Return all placeholder action-description pairs."""
        return [(action, description.strip()) for action, description in self.placeholder_pattern.findall(code)]

    def parse_placeholder_uses(self, code: str) -> list[PlaceholderUse]:
        """Return all placeholder uses found in the code, including Page Objects."""
        lines = code.splitlines()
        uses: list[PlaceholderUse] = []
        for index, line in enumerate(lines, start=1):
            for action, description in self.placeholder_pattern.findall(line):
                clean_description = description.strip()
                uses.append(
                    PlaceholderUse(
                        action=action,
                        description=clean_description,
                        token=f"{{{{{action}:{clean_description}}}}}",
                        line_number=index,
                        raw_line=line,
                    )
                )
        return uses

    def parse_pages_needed(self, code: str) -> list[tuple[str, str]]:
        """Return the pages listed in the `# PAGES_NEEDED:` block."""
        return [(url.strip(), desc.strip() if desc else "") for url, desc in self.pages_pattern.findall(code)]

    def parse_page_requirements(self, code: str) -> list[PageRequirement]:
        """Return typed page requirements from the `# PAGES_NEEDED:` block."""
        return [PageRequirement(url=url, description=description) for url, description in self.parse_pages_needed(code)]

    def parse_test_journeys(self, code: str) -> list[TestJourney]:
        """Return structured journey data for each generated test function."""
        lines = code.splitlines()
        matches = list(self.test_definition_pattern.finditer(code))
        if not matches:
            return []

        line_offsets = self._build_line_offsets(lines)
        journeys: list[TestJourney] = []

        for index, match in enumerate(matches):
            test_name = match.group(1)
            start_line = self._offset_to_line(line_offsets, match.start())
            next_match_start = matches[index + 1].start() if index + 1 < len(matches) else len(code)
            end_line = self._offset_to_line(line_offsets, next_match_start) - (0 if index + 1 == len(matches) else 1)
            block_lines = lines[start_line - 1 : end_line]
            steps = self._build_steps(block_lines, start_line)
            page_object_names = self._extract_page_object_names(block_lines)

            journeys.append(
                TestJourney(
                    test_name=test_name,
                    start_line=start_line,
                    end_line=end_line,
                    page_object_names=page_object_names,
                    steps=steps,
                )
            )

        return journeys

    @staticmethod
    def _build_line_offsets(lines: list[str]) -> list[int]:
        """Return the starting character offset for each line."""
        offsets: list[int] = []
        running_offset = 0
        for line in lines:
            offsets.append(running_offset)
            running_offset += len(line) + 1
        return offsets

    @staticmethod
    def _offset_to_line(line_offsets: list[int], offset: int) -> int:
        """Convert a character offset into a 1-based line number."""
        line_number = 1
        for index, line_offset in enumerate(line_offsets, start=1):
            if line_offset > offset:
                break
            line_number = index
        return line_number

    def _build_steps(self, block_lines: list[str], start_line: int) -> list[TestStep]:
        """Build ordered steps for one test function block."""
        steps: list[TestStep] = []

        for index, line in enumerate(block_lines, start=0):
            raw_line = line.rstrip()
            if not raw_line.strip() or raw_line.lstrip().startswith("#") or raw_line.lstrip().startswith("def "):
                continue

            placeholders: list[PlaceholderUse] = []
            for action, description in self.placeholder_pattern.findall(raw_line):
                clean_description = description.strip()
                placeholders.append(
                    PlaceholderUse(
                        action=action,
                        description=clean_description,
                        token=f"{{{{{action}:{clean_description}}}}}",
                        line_number=start_line + index,
                        raw_line=raw_line,
                    )
                )

            steps.append(
                TestStep(
                    line_number=start_line + index,
                    raw_line=raw_line,
                    placeholders=placeholders,
                )
            )

        return steps

    def _extract_page_object_names(self, block_lines: list[str]) -> list[str]:
        """Return page object classes referenced within a test block."""
        page_object_names: list[str] = []
        seen: set[str] = set()

        for line in block_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            for name in self.page_object_reference_pattern.findall(line):
                if not name.endswith("Page"):
                    continue
                if name not in seen:
                    seen.add(name)
                    page_object_names.append(name)

        return page_object_names

    def get_test_class_names(self, code: str) -> list[str]:
        """Return class names declared in the skeleton."""
        return re.findall(r"class\s+(\w+):", code)

    def find_malformed_placeholders(self, code: str) -> list[str]:
        """Return placeholders that incorrectly use single braces."""
        return [
            f"{{{action}:{description.strip()}}}"
            for action, description in self.single_brace_placeholder_pattern.findall(code)
        ]

    def validate_skeleton(self, code: str) -> str | None:
        """Return a user-facing validation error for malformed skeleton output."""
        malformed_placeholders = self.find_malformed_placeholders(code)
        if malformed_placeholders:
            preview = ", ".join(malformed_placeholders[:3])
            return (
                f"Skeleton output used invalid single-brace placeholders instead of `{{{{...}}}}`. Examples: {preview}"
            )

        allowed_actions = {"CLICK", "FILL", "GOTO", "URL", "ASSERT"}
        unknown_actions = []
        for action, description in self.any_double_brace_placeholder_pattern.findall(code):
            if action not in allowed_actions:
                unknown_actions.append(f"{{{{{action}:{description.strip()}}}}}")
        if unknown_actions:
            preview = ", ".join(unknown_actions[:3])
            return (
                "Skeleton output used unsupported placeholder actions. "
                "Only CLICK, FILL, GOTO, URL, ASSERT are allowed. "
                f"Examples: {preview}"
            )

        # Reject placeholders whose descriptions contain Python format-string
        # variable references like {item_name}.  Those curly braces break the
        # resolver's [^}]+ regex so the placeholder is never substituted and
        # the raw text causes a SyntaxError at validation time.
        python_var_in_placeholder = re.compile(r"\{\{[A-Z_]+:[^}]*\{[^}]+\}[^}]*\}\}")
        bad_placeholders = python_var_in_placeholder.findall(code)
        if bad_placeholders:
            preview = ", ".join(bad_placeholders[:3])
            return (
                "Skeleton output used Python variable syntax inside placeholder descriptions "
                "(e.g. {{ASSERT:item {item_name} is in cart}}). "
                "Use a literal description instead, e.g. {{ASSERT:Blue Top is in cart}}. "
                f"Examples: {preview}"
            )

        pages_needed_block = re.search(r"#\s*PAGES_NEEDED:\s*(.*)", code, re.S)
        if pages_needed_block:
            page_lines = re.findall(r"^\s*#\s*-\s*(.+)$", pages_needed_block.group(1), re.M)
            invalid_pages = [
                line.strip() for line in page_lines if line.strip() and not re.match(r"https?://", line.strip())
            ]
            if invalid_pages:
                preview = ", ".join(invalid_pages[:3])
                return (
                    "Skeleton output listed invalid page entries in `# PAGES_NEEDED:`. "
                    "Each entry must be a real absolute URL. "
                    f"Examples: {preview}"
                )

        # Hallucination check: Reject raw strings that look like CSS selectors or IDs
        # in evidence_tracker calls, or raw Playwright calls.
        # We allow URLs starting with http.
        #
        # Strategy: find evidence_tracker.click/fill/assert_visible(page.locator|expect) calls,
        # extract the FIRST string argument, and reject it if it looks like a real CSS/XPath
        # selector (contains .class, #id, [attr], //, > combinators) but is NOT a placeholder
        # (doesn't start with {{).
        #
        # We use a two-step approach to handle nested quotes:
        # 1. Find the call site
        # 2. Extract the first quoted string argument (handling both ' and " quotes)
        evidence_tracker_call_pattern = re.compile(r"evidence_tracker\.(click|fill|assert_visible)\s*\(")

        for match in evidence_tracker_call_pattern.finditer(code):
            # Find the first string argument after the opening paren
            paren_pos = match.end() - 1
            if paren_pos >= len(code):
                continue
            # Find the opening quote of the first argument
            arg_start = paren_pos + 1
            # Skip whitespace
            while arg_start < len(code) and code[arg_start] in (" ", "\t", "\n", "\r"):
                arg_start += 1
            if arg_start >= len(code):
                continue
            quote_char = code[arg_start]
            if quote_char not in ("'", '"'):
                continue
            # Find the closing quote, handling escaped quotes and nested quotes
            # For selectors like 'a[href="/path"]', we look for the outer quote
            arg_end = arg_start + 1
            while arg_end < len(code):
                ch = code[arg_end]
                if ch == "\\":
                    arg_end += 2  # Skip escaped character
                    continue
                if ch == quote_char:
                    break
                arg_end += 1
            content = code[arg_start + 1 : arg_end].strip()
            # If it's a hardcoded selector (not starting with {{ and not a URL), it's a hallucination
            if content and not content.startswith("{{") and not content.startswith("http"):
                # Check if it looks like a real selector (has CSS/XPath patterns)
                looks_like_selector = any(
                    pattern.search(content)
                    for pattern in [
                        re.compile(r"\.[a-zA-Z]"),  # CSS class
                        re.compile(r"#\w+"),  # CSS ID
                        re.compile(r"\[.+="),  # Attribute selector
                        re.compile(r"//[a-zA-Z]"),  # XPath
                        re.compile(r"\w+\s*>\s*\w+"),  # Descendant combinator
                    ]
                )
                if looks_like_selector:
                    return (
                        "Skeleton output violated the NEVER GUESS LOCATORS rule. "
                        "You must use placeholders like `{{CLICK:description}}` instead of raw selectors. "
                        f"Guessed selector found: '{content[:80]}'"
                    )
        # Reject skeletons where the LLM has written pytest.skip() directly into a
        # non-statement position (e.g. as a label= value or as a string literal in
        # any argument slot).  When this happens the test runs silently instead of
        # skipping, and the label shows confusing text in the evidence viewer.
        #
        # Two forms to catch:
        #   label=pytest.skip("...")          ← unquoted call as keyword value
        #   label='pytest.skip("...")'        ← quoted string containing the call text
        #
        # A legitimate standalone statement like:
        #   pytest.skip("reason")
        # is on its own line with no surrounding call context and is NOT rejected.

        _PYTEST_SKIP_NON_STATEMENT_PATTERN = re.compile(
            r"""
            (?:                         # Either:
                \w+\s*=\s*              #   keyword=   (label=pytest.skip(...))
                |                       # or
                ,\s*                    #   , prefix   (arg, pytest.skip(...))
                |                       # or
                ['"]\s*                 #   open quote ('pytest.skip(...)')
            )
            pytest\.skip\s*\(           # followed by pytest.skip(
            """,
            re.VERBOSE | re.MULTILINE,
        )

        pytest_skip_non_statement_matches = _PYTEST_SKIP_NON_STATEMENT_PATTERN.findall(code)
        if pytest_skip_non_statement_matches:
            return (
                "Skeleton output contained pytest.skip() in a non-statement position "
                "(e.g. as a label= value or inside a string argument). "
                "pytest.skip() must only appear as a standalone statement. "
                "Use a placeholder like {{CLICK:description}} instead of pre-writing skip calls."
            )
        return None
