#!/usr/bin/env python3
"""User story parser module for extracting feature specifications from text."""

import re
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class FeatureSpecification:
    """Parsed feature specification containing user story and acceptance criteria."""

    user_story: str
    acceptance_criteria: list[str]
    raw_input: str

    @property
    def criteria_count(self) -> int:
        """Return the number of acceptance criteria."""
        return len(self.acceptance_criteria)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for external use."""
        return {
            "user_story": self.user_story,
            "acceptance_criteria": self.acceptance_criteria,
            "criteria_count": self.criteria_count,
        }


@dataclass
class ParseResult:
    """Result of parsing a feature specification."""

    success: bool
    specification: FeatureSpecification | None = None
    error_message: str | None = None


@dataclass
class RequirementModel:
    """Normalized requirement list used by prompt, coverage, and reporting."""

    lines: list[str]
    source: Literal["acceptance_criteria", "derived_from_story", "story_fallback"]

    @property
    def count(self) -> int:
        """Return number of normalized requirements."""
        return len(self.lines)

    def to_text(self) -> str:
        """Render requirement lines for prompt injection."""
        return "\n".join(self.lines)

    def to_numbered_text(self) -> str:
        """Render requirement lines as a numbered list."""
        return "\n".join(f"{index}. {line}" for index, line in enumerate(self.lines, start=1))


class FeatureParser:
    """Parser for extracting user story and acceptance criteria from feature specs."""

    STORY_HEADINGS = (
        "user story",
        "user story:",
        "story",
        "story:",
        "## user story",
        "## user story:",
        "## story",
        "## story:",
        "as a",
        "as a:",
        "## as a",
        "## as a:",
        "as a ",
        "as a:",
    )
    CRITERIA_HEADINGS = (
        "acceptance criteria",
        "acceptance criteria:",
        "acceptance",
        "acceptance:",
        "criteria",
        "ac",
        "ac:",
        "requirements",
        "## acceptance criteria",
        "## acceptance criteria:",
        "## acceptance",
        "## acceptance:",
        "## criteria",
        "## criteria:",
        "## ac",
        "## ac:",
        "## requirements",
        "## requirements:",
    )

    def parse(self, text: str) -> ParseResult:
        """
        Parse a feature specification string into user story and acceptance criteria.

        Args:
            text: Raw feature specification text

        Returns:
            ParseResult containing parsed specification or error
        """
        if not text or not text.strip():
            return ParseResult(
                success=False,
                error_message="Input cannot be empty",
            )

        try:
            lines = text.split("\n")
            user_story_lines: list[str] = []
            acceptance_criteria_lines: list[str] = []
            in_story_section = False
            in_criteria_section = False
            heading_found = False

            for line in lines:
                stripped = line.strip()
                stripped_lower = stripped.lower()

                # Detect section headings first (handles markdown headings like ## User Story)
                # Handle variable whitespace between ## and heading text
                is_story_heading = False
                for heading in self.STORY_HEADINGS:
                    # Exact match (handles plain text "user story:" or markdown "## user story:")
                    if stripped_lower == heading:
                        is_story_heading = True
                        break
                    # Markdown heading with ## prefix and variable whitespace (handles ##   User Story)
                    if re.match(r"^#{1,2}\s+" + re.escape(heading) + r"\s*$", stripped_lower):
                        is_story_heading = True
                        break
                    # Markdown heading with text after (handles ## User Story: text or User Story: content)
                    if re.match(r"^#{1,2}\s*" + re.escape(heading) + r"\s+", stripped_lower):
                        is_story_heading = True
                        break

                # Plain text heading "User Story: content" or "Story: content" - case insensitive
                # This must be checked separately after all heading patterns
                # Handle "User Story: content" where content is on same line as heading
                if not is_story_heading and stripped_lower.startswith("user story:"):
                    is_story_heading = True
                    # Capture content after "User Story:" as part of the user story
                    if "user story:" in stripped_lower:
                        idx = stripped_lower.index("user story:")
                        content = stripped[idx + len("user story:") :].strip()
                        if content:
                            user_story_lines.append(content)
                    continue

                if not is_story_heading and stripped_lower.startswith("story:"):
                    is_story_heading = True
                    # Capture content after "Story:" as part of the user story
                    if "story:" in stripped_lower:
                        idx = stripped_lower.index("story:")
                        content = stripped[idx + len("story:") :].strip()
                        if content:
                            user_story_lines.append(content)
                    continue

                is_criteria_heading = False
                for heading in self.CRITERIA_HEADINGS:
                    # Exact match (handles plain text "acceptance criteria:" or markdown "## acceptance criteria:")
                    if stripped_lower == heading:
                        is_criteria_heading = True
                        break
                    # Markdown heading with ## prefix and variable whitespace
                    if re.match(r"^#{1,2}\s+" + re.escape(heading) + r"\s*$", stripped_lower):
                        is_criteria_heading = True
                        break
                    # Plain text or markdown heading with text after (handles User Story: content or ## User Story: text)
                    if re.match(r"^#{0,2}\s*" + re.escape(heading) + r"\s+", stripped_lower):
                        is_criteria_heading = True
                        break

                if is_story_heading:
                    heading_found = True
                    in_story_section = True
                    in_criteria_section = False
                    continue

                if is_criteria_heading:
                    heading_found = True
                    in_criteria_section = True
                    in_story_section = False
                    continue

                # Skip empty lines and markdown dividers
                if not stripped or stripped.startswith("---"):
                    continue

                # Skip standalone hash characters (# or ##) that are not part of known headings
                # Only skip if it's just # or ## without any other text
                if stripped in ("#", "##"):
                    continue

                if in_story_section:
                    user_story_lines.append(stripped)
                elif in_criteria_section:
                    clean = self._clean_criterion(stripped)
                    if clean:
                        acceptance_criteria_lines.append(clean)

            # Fallback: no headings found - collect all meaningful lines as story text
            if not heading_found:
                for line in lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("---"):
                        if not user_story_lines:
                            user_story_lines.append(stripped)
                        elif stripped.lower().startswith("as a") or " want to " in stripped.lower():
                            user_story_lines.append(stripped)
                        elif user_story_lines:
                            user_story_lines.append(stripped)

            user_story_text = "\n".join(user_story_lines).strip()

            if not user_story_text:
                return ParseResult(
                    success=False,
                    error_message="No user story found in input",
                )

            specification = FeatureSpecification(
                user_story=user_story_text,
                acceptance_criteria=acceptance_criteria_lines,
                raw_input=text,
            )

            return ParseResult(success=True, specification=specification)

        except Exception as e:
            return ParseResult(
                success=False,
                error_message=f"Parse error: {str(e)}",
            )

    def build_requirement_model(self, specification: FeatureSpecification) -> RequirementModel:
        """Build a consistent requirement model from parsed specification."""
        explicit_lines = [
            self._clean_criterion(line.strip()) for line in specification.acceptance_criteria if line.strip()
        ]
        explicit_lines = [line for line in explicit_lines if line]
        if explicit_lines:
            return RequirementModel(lines=explicit_lines, source="acceptance_criteria")

        story_lines = [
            self._clean_criterion(line.strip()) for line in specification.user_story.splitlines() if line.strip()
        ]
        story_lines = [line for line in story_lines if line]
        if story_lines and story_lines[0].lower().startswith("as a "):
            remainder = story_lines[1:]
            if remainder:
                story_lines = remainder
        if len(story_lines) > 1:
            return RequirementModel(lines=story_lines, source="derived_from_story")

        fallback_line = specification.user_story.strip()
        return RequirementModel(lines=[fallback_line] if fallback_line else [], source="story_fallback")

    @staticmethod
    def _clean_criterion(stripped: str) -> str:
        """
        Clean a criterion line by removing bullet markers and whitespace.

        Args:
            stripped: Already stripped line text

        Returns:
            Cleaned criterion text
        """
        # Strip leading bullet/number markers.
        clean = stripped
        for marker in ("-", "*", "\u2022"):
            clean = clean.lstrip(marker)
        clean = clean.strip()
        clean = re.sub(r"^\d+[.)]\s*", "", clean)
        if re.fullmatch(r"\(?\s*total\s*:\s*\d+\s+criteria\s*\)?", clean, flags=re.IGNORECASE):
            return ""
        return clean
