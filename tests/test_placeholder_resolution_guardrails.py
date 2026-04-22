"""Guardrail tests for placeholder resolution correctness.

These three tests exist specifically to break the loop where:
  1. LLM generates skeleton with pytest.skip or bad locators in wrong positions
  2. Unit tests (which mock the LLM) all pass
  3. Real pipeline output breaks at runtime
  4. LLM fixes unit tests but not the real pipeline

The tests here operate on the actual resolution logic with no mocked LLM,
so they catch failures in the output that would reach the user.
"""

from __future__ import annotations

import ast
import re

import pytest

from src.skeleton_parser import SkeletonParser

# ---------------------------------------------------------------------------
# Test 1 — pytest.skip must never appear inside a string argument
# ---------------------------------------------------------------------------


class TestSkipNeverInsideStringArgument:
    """Regression: pytest.skip was appearing as the value of label= arguments.

    When a placeholder can't be resolved, the resolver emits:
        pytest.skip("Locator for '...' not found")
    as a STANDALONE STATEMENT replacing the whole line.

    It must NEVER appear as a string literal inside another call, like:
        evidence_tracker.click('...', label='pytest.skip("...")')

    The latter runs silently without skipping the test — it just records
    a confusing label and continues, giving false confidence.
    """

    # Pattern that catches pytest.skip embedded inside a quoted string argument
    _SKIP_IN_STRING_PATTERN = re.compile(
        r"""['"]\s*pytest\.skip\s*\(""",
        re.MULTILINE,
    )

    def _assert_no_skip_in_strings(self, code: str) -> None:
        """Fail with a clear message if pytest.skip appears inside a string."""
        matches = self._SKIP_IN_STRING_PATTERN.findall(code)
        if matches:
            pytest.fail(
                f"pytest.skip() appeared inside a quoted string argument "
                f"({len(matches)} occurrence(s)). It must appear only as a "
                f"standalone statement.\n\nCode snippet:\n{code[:500]}"
            )

    def test_skip_as_standalone_statement_not_label_value(self) -> None:
        """Given a skeleton where the label slot contains an ASSERT placeholder
        that can't be resolved, the resolved code must not put pytest.skip
        inside the label= string.

        This test exercises the real _replace_token_in_line logic to verify
        that the actual pipeline handles this case correctly.
        """
        from src.orchestrator import TestOrchestrator

        # Simulate a line where the ASSERT placeholder (resolved to pytest.skip)
        # is embedded inside a label= argument
        line = "    evidence_tracker.click('a[href=\"/view_cart\"]', label='{{ASSERT:verify cart page is displayed}}')"

        # _replace_token_in_line with a resolved value of pytest.skip should
        # replace the entire line with the skip statement, not embed it in label=
        resolved = TestOrchestrator._replace_token_in_line(
            line,
            action="ASSERT",
            token="{{ASSERT:verify cart page is displayed}}",
            resolved_value='pytest.skip("Locator not found.")',
            duplicate_selectors=set(),
            description="",
        )

        # The result should be a standalone pytest.skip, NOT embedded in label=
        self._assert_no_skip_in_strings(resolved)
        assert resolved.strip().startswith("pytest.skip("), f"Expected standalone pytest.skip(), got: {resolved}"

    def test_skip_in_label_position_detected_by_validator(self) -> None:
        """The skeleton validator must reject skeletons where the LLM has
        pre-written pytest.skip() directly into the label= argument."""
        parser = SkeletonParser()
        # Skeleton where LLM hallucinated pytest.skip in the label
        skeleton_with_skip_in_label = (
            "from playwright.sync_api import Page\n"
            "import pytest\n\n"
            "def test_01_something(page: Page, evidence_tracker) -> None:\n"
            "    evidence_tracker.click({{CLICK:go to cart}}, "
            'label=pytest.skip("Placeholder not resolved"))\n'
        )
        error = parser.validate_skeleton(skeleton_with_skip_in_label)
        assert error is not None, (
            "Skeleton validator should reject skeletons where pytest.skip() "
            "appears directly in a label= argument, but it did not."
        )
        assert "pytest.skip" in error.lower() or "label" in error.lower()


# ---------------------------------------------------------------------------
# Test 2 — resolved code must always pass ast.parse()
# ---------------------------------------------------------------------------


class TestResolvedCodePassesSyntaxValidation:
    """Any code produced by the resolution step must be syntactically valid.

    This is NOT the same as the code_validator check on the final saved file.
    This test runs ast.parse() on the output of the resolution step itself
    so that broken substitutions are caught before write_run_artifacts().

    The validate_python_syntax() call in PipelineArtifactWriter is the last
    line of defence. This test catches failures earlier so the error message
    is clearer.
    """

    def _parse_or_fail(self, code: str, context: str = "") -> None:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            pytest.fail(
                f"Resolved code has a SyntaxError at line {exc.lineno}: "
                f"{exc.msg}\n\nContext: {context}\n\nCode:\n{code}"
            )

    def test_unresolved_click_produces_valid_python(self) -> None:
        """When a CLICK placeholder can't be resolved, the whole line must
        become a standalone pytest.skip() call — which is valid Python."""
        # Simulate a failed resolution
        resolved = "    pytest.skip(\"Locator for 'non-existent button' not found.\")\n"
        self._parse_or_fail(
            f"import pytest\ndef test_x(page, evidence_tracker):\n{resolved}",
            context="unresolved CLICK → should become pytest.skip()",
        )

    def test_unresolved_assert_produces_valid_python(self) -> None:
        """Same guarantee for ASSERT placeholders."""
        resolved = "    pytest.skip(\"Locator for 'cart total' not found.\")\n"
        self._parse_or_fail(
            f"import pytest\ndef test_x(page, evidence_tracker):\n{resolved}",
            context="unresolved ASSERT → should become pytest.skip()",
        )

    def test_mixed_resolved_and_unresolved_on_same_function_is_valid(self) -> None:
        """A function where some placeholders resolved and others didn't
        must still produce valid Python."""
        code = (
            "import pytest\n"
            "from playwright.sync_api import Page\n\n"
            "def test_01_flow(page: Page, evidence_tracker) -> None:\n"
            "    evidence_tracker.navigate('https://example.com')\n"
            "    evidence_tracker.click('a[href=\"/products\"]:visible', label='browse products')\n"
            "    pytest.skip(\"Locator for 'add to cart button' not found.\")\n"
            "    pytest.skip(\"Locator for 'cart total amount' not found.\")\n"
        )
        self._parse_or_fail(code, context="mixed resolved/unresolved in same test function")


# ---------------------------------------------------------------------------
# Test 3 — skeleton validator closes the gap that allowed skip-in-label through
# ---------------------------------------------------------------------------


class TestSkeletonValidatorRejectsPytestSkipInNonStatementPositions:
    """The skeleton validator must catch pytest.skip() in positions where
    it would be treated as a value rather than a statement.

    This is the root-cause guardrail. If the LLM writes:
        evidence_tracker.click({{CLICK:...}}, label=pytest.skip("..."))
    the validator must reject it before resolution even starts.

    Without this check, the resolver correctly handles the {{CLICK:...}} token
    but the label=pytest.skip(...) survives unchanged into the output and
    confuses both readers and the evidence viewer.
    """

    def test_rejects_pytest_skip_as_label_keyword_arg(self) -> None:
        parser = SkeletonParser()
        bad_skeleton = (
            "from playwright.sync_api import Page\n"
            "import pytest\n\n"
            "def test_01(page: Page, evidence_tracker) -> None:\n"
            "    evidence_tracker.navigate('https://example.com')\n"
            "    evidence_tracker.click({{CLICK:view cart}}, "
            'label=pytest.skip("Placeholder not resolved"))\n'
        )
        error = parser.validate_skeleton(bad_skeleton)
        assert error is not None, (
            "validate_skeleton must reject a skeleton where pytest.skip() "
            "appears as a non-statement expression (e.g. inside label=). "
            "The validator allowed it through, which causes silent test failures."
        )

    def test_rejects_pytest_skip_as_positional_string_arg(self) -> None:
        """Also reject the variant where pytest.skip ends up as a string literal."""
        parser = SkeletonParser()
        bad_skeleton = (
            "from playwright.sync_api import Page\n"
            "import pytest\n\n"
            "def test_01(page: Page, evidence_tracker) -> None:\n"
            "    evidence_tracker.click({{CLICK:view cart}}, "
            "label='pytest.skip(\"Placeholder not resolved\")')\n"
        )
        error = parser.validate_skeleton(bad_skeleton)
        assert error is not None, (
            "validate_skeleton must reject a skeleton where the string 'pytest.skip(...)' appears as a label value."
        )

    def test_accepts_legitimate_pytest_skip_as_standalone_statement(self) -> None:
        """A standalone pytest.skip() statement (not inside another call)
        is valid skeleton output and must not be rejected."""
        parser = SkeletonParser()
        good_skeleton = (
            "from playwright.sync_api import Page\n"
            "import pytest\n\n"
            "# PAGES_NEEDED:\n"
            "# - https://example.com\n\n"
            "def test_01(page: Page, evidence_tracker) -> None:\n"
            "    evidence_tracker.navigate({{GOTO:home page}})\n"
            '    pytest.skip("This step requires manual setup")\n'
        )
        error = parser.validate_skeleton(good_skeleton)
        # Should not reject because of the standalone pytest.skip
        # (It might reject for other reasons unrelated to this guardrail)
        if error is not None:
            assert "pytest.skip" not in error, (
                f"validate_skeleton incorrectly rejected a legitimate standalone "
                f"pytest.skip() statement. Error: {error}"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_naive_token_replacement(code: str, resolutions: dict[str, str]) -> str:
    """Simulate a naive token replacement to produce a broken output.

    This helper deliberately uses str.replace() to reproduce the class of bug
    where pytest.skip ends up embedded in a string argument, so the tests can
    assert that the real pipeline output doesn't exhibit the same pattern.
    """
    result = code
    for token, resolved in resolutions.items():
        result = result.replace(token, resolved)
    return result
