"""Parse placeholder-based skeleton code produced by the intelligent pipeline."""

from __future__ import annotations

import re

from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep


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

        return code

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
        hallucination_pattern = re.compile(
            r"(?:page\.locator|expect\(.*?page\.locator|evidence_tracker\.(?:click|fill|assert_visible))\(['\"]([^'\"{}]*)['\"]",
            re.S,
        )
        for match in hallucination_pattern.finditer(code):
            content = match.group(1).strip()
            # If it's a hardcoded selector (not starting with {{ and not a URL), it's a hallucination
            if content and not content.startswith("{{") and not content.startswith("http"):
                return (
                    "Skeleton output violated the NEVER GUESS LOCATORS rule. "
                    "You must use placeholders like `{{CLICK:description}}` instead of raw selectors. "
                    f"Guessed selector found: '{content}'"
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
