"""Quoted text must be checked: text assertions carry the expected string.

t-0471. The landing UAT (t-0470) showed a "verify X contains TEXT" criterion
emitted as ``assert_visible`` (nothing about TEXT was checked), and a criterion
that quoted a heading resolved to a nearby eyebrow/footnote. Two emitter-level
fixes are pinned here:

- ``replace_token_in_line`` keeps ``assert_text`` / ``assert_text_contains``
  and passes the quoted expected string when the description carries it, instead
  of falling back to ``assert_visible``.
- ``ElementMatcher.pass0_exact_text_match`` exact-matches a quoted phrase inside
  a longer ASSERT description before the loose scoring passes.

The skeleton prompt that feeds the description is checked too, because a short
label that drops the quote would leave both fixes with nothing to act on.
"""

from __future__ import annotations

import asyncio

from src.code_postprocessor import replace_token_in_line
from src.element_matcher import ElementMatcher
from src.locator_builder import build_robust_locator
from src.placeholder_resolver import PlaceholderResolver
from src.prompt_builder import PromptBuilder, build_skeleton_prompt


def _emit(description: str, assertion_type: str, resolved_value: str = "'.text-cyan-300'") -> str:
    token = f"{{{{ASSERT:{description}}}}}"
    return replace_token_in_line(
        f"    {token}",
        "ASSERT",
        token,
        resolved_value,
        set(),
        description,
        assertion_type=assertion_type,
    ).strip()


class TestTextAssertionEmission:
    """A text assertion must carry the text, not degrade to assert_visible."""

    def test_contains_criterion_emits_assert_text_contains_with_the_text(self) -> None:
        out = _emit("welcome banner contains 'Welcome back'", "toContainText")
        assert (
            out
            == "evidence_tracker.assert_text_contains('.text-cyan-300', 'Welcome back', label=\"welcome banner contains 'Welcome back'\")"
        )

    def test_to_have_text_emits_assert_text_with_the_text(self) -> None:
        out = _emit("headline text is 'Per deployment, not per seat'", "toHaveText")
        assert "evidence_tracker.assert_text(" in out
        assert "'Per deployment, not per seat'" in out
        assert "assert_visible" not in out

    def test_install_command_contains_is_a_body_text_check(self) -> None:
        """The install command path (page fact) checks the command text on body."""
        out = _emit("install command contains 'git clone https://github.com/tancat-ai/tancat'", "toContainText")
        assert "evidence_tracker.assert_text_contains('body', 'git clone https://github.com/tancat-ai/tancat'" in out
        assert "assert_visible" not in out

    def test_longest_quoted_phrase_is_the_expected_text(self) -> None:
        """With a section name and a heading quoted, the specific heading wins."""
        out = _emit(
            "'How It Works' section with the 'Story -> Generate -> Run -> Evidence -> Export' heading",
            "toHaveText",
        )
        assert "assert_text('.text-cyan-300', 'Story -> Generate -> Run -> Evidence -> Export'" in out

    def test_no_quoted_text_keeps_the_visible_only_fallback(self) -> None:
        out = _emit("install command", "toContainText")
        assert "evidence_tracker.assert_visible('.text-cyan-300'" in out
        assert "assert_text" not in out


class TestQuotedHeadingResolution:
    """pass0 must use a quoted phrase inside a longer description."""

    @staticmethod
    def _matcher() -> ElementMatcher:
        return ElementMatcher(PlaceholderResolver())

    @staticmethod
    def _eyebrow() -> dict[str, str]:
        return {"selector": "span.eyebrow", "text": "How It Works", "tag": "span", "role": "span"}

    def test_quoted_heading_beats_a_shorter_incidental_quote(self) -> None:
        heading = {
            "selector": "h2.pipeline",
            "text": "Story -> Generate -> Run -> Evidence -> Export",
            "tag": "h2",
            "role": "heading",
        }
        pages = {"https://x.test/": [self._eyebrow(), heading]}
        description = "'How It Works' section with the 'Story -> Generate -> Run -> Evidence -> Export' heading"
        matched = self._matcher().pass0_exact_text_match("ASSERT", description, pages)
        assert matched is not None
        assert matched["selector"] == "h2.pipeline"

    def test_quoted_expected_text_is_matched(self) -> None:
        element = {"selector": "p.msg", "text": "Welcome back", "tag": "p", "role": "p"}
        matched = self._matcher().pass0_exact_text_match(
            "ASSERT", "welcome banner contains 'Welcome back'", {"https://x.test/": [element]}
        )
        assert matched is not None
        assert matched["selector"] == "p.msg"

    def test_fully_quoted_description_still_matches(self) -> None:
        element = {"selector": "h1", "text": "Welcome", "tag": "h1", "role": "heading"}
        matched = self._matcher().pass0_exact_text_match("ASSERT", "'Welcome'", {"https://x.test/": [element]})
        assert matched is not None
        assert matched["selector"] == "h1"

    def test_no_quote_matches_nothing_new(self) -> None:
        pages = {"https://x.test/": [self._eyebrow()]}
        assert self._matcher().pass0_exact_text_match("ASSERT", "How It Works section", pages) is None


class TestPromptKeepsTheQuotedCheck:
    """The skeleton prompt must keep the quoted text, or the emitter gets a bare label."""

    @staticmethod
    def _prompt() -> str:
        return (
            PromptBuilder(
                build_skeleton_prompt(
                    user_story="As a user I verify quoted text.",
                    conditions="1. Verify the install command contains 'git clone https://github.com/tancat-ai/tancat'",
                    known_urls_block="- http://localhost:8079/",
                    expected_count=1,
                )
            )
            .render()
            .text
        )

    def test_prompt_has_the_keep_the_quoted_check_rule(self) -> None:
        prompt = self._prompt()
        assert "KEEP THE QUOTED CHECK" in prompt
        # The rule must survive rendering: the t-string's ``{{`` renders as ``{``.
        assert "{ASSERT:install command contains 'git clone ...'}" in prompt
        assert "{ASSERT:'Per deployment, not per seat' pricing section}" in prompt


class TestQuotedHeadingLocatorPinning:
    """t-0477: a quoted-text match must pin the text when its class is shared.

    On the landing page four headings share one Tailwind class list, so the
    class-based locator matches all of them and ``assert_*`` reads the first -
    the wrong heading. The resolver now carries the quoted target text, and the
    locator builder pins it when the class selector is not unique.
    """

    SHARED_CLASSES = "text-3xl sm:text-4xl font-extrabold text-white mt-2"

    @classmethod
    def _heading(cls, text: str, selector: str) -> dict[str, str]:
        return {"selector": selector, "text": text, "tag": "h2", "role": "heading", "classes": cls.SHARED_CLASSES}

    def _shared_pages(self) -> dict[str, list[dict[str, str]]]:
        return {
            "https://x.test/": [
                self._heading(
                    "See how plain English becomes ground-truth Pytest.", "body > section:nth-of-type(2) > h2"
                ),
                self._heading("Per deployment, not per seat.", "body > section:nth-of-type(3) > h2"),
            ]
        }

    def test_shared_class_heading_is_text_pinned(self) -> None:
        pages = self._shared_pages()
        target = pages["https://x.test/"][1]
        target["exact_text"] = "Per deployment, not per seat"

        locator = build_robust_locator(target, page_elements=pages["https://x.test/"])

        assert locator == 'h2:has-text("Per deployment, not per seat")'
        assert "font-extrabold" not in (locator or "")

    def test_unique_class_heading_keeps_the_class_locator(self) -> None:
        unique = {
            "selector": "body > section:nth-of-type(4) > h2",
            "text": "Clone + uv sync + run",
            "tag": "h2",
            "role": "heading",
            "classes": "text-3xl font-bold text-white mt-1",
            "exact_text": "Clone + uv sync + run",
        }
        locator = build_robust_locator(unique, page_elements=[unique])
        assert locator == "h2.font-bold.mt-1.text-3xl.text-white"

    def test_resolver_carries_the_quoted_text_and_pins_when_shared(self) -> None:
        pages = self._shared_pages()
        matcher = ElementMatcher(PlaceholderResolver())
        matched = asyncio.run(
            matcher.find_best_element_for_current_page(
                "ASSERT", "'Per deployment, not per seat' pricing section", "https://x.test/", pages
            )
        )

        assert matched is not None
        assert matched.get("exact_text") == "Per deployment, not per seat"
        assert build_robust_locator(matched, page_elements=pages["https://x.test/"]) == (
            'h2:has-text("Per deployment, not per seat")'
        )
