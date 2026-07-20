"""Self-healing reflection loop — automated test repair after failures.

Phase 2 of the ML Engineering roadmap. Runs failed tests, feeds errors
to an LLM reviewer, applies suggested patches, and re-runs until tests
pass or max iterations are exhausted.

Design:
  - Classifier routes failures to repair strategies
  - LLM reviewer suggests concrete code patches
  - Patches are applied surgically (single-line replacement)
  - Loop tracks what was fixed vs. what remains
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.failure_classifier import FailureDetail, classify_failure
from src.llm_client import LLMClient
from src.pytest_output_parser import RunResult, TestResult, parse_pytest_output

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class AppliedPatch:
    """Record of a single code change applied during healing."""

    test_name: str
    line_number: int
    old_text: str
    new_text: str
    diagnosis: str
    strategy: str  # "replace_locator" | "add_navigation" | "add_wait" | "skip_test"


@dataclass
class HealingReport:
    """Result of a self-healing run."""

    total_failures: int = 0
    fixed: int = 0
    remaining: int = 0
    unfixable: int = 0
    iterations: int = 0
    patches: list[AppliedPatch] = field(default_factory=list)
    final_results: list[TestResult] = field(default_factory=list)

    @property
    def all_fixed(self) -> bool:
        return self.remaining == 0 and self.total_failures > 0


# ---------------------------------------------------------------------------
# Reviewer prompt
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM_PROMPT = """You are an expert test automation engineer. Your job is to analyze
a failing Playwright test and suggest a specific code fix.

You will receive:
1. The test function source code
2. The exact error message from pytest
3. Scraped page elements (selectors, text, roles) from the page where it failed

Output ONLY a valid JSON object with these fields:
{
  "fixable": true or false,
  "diagnosis": "brief explanation of what went wrong",
  "strategy": "replace_locator" | "add_navigation" | "add_wait" | "skip_test",
  "old_line": "the exact line to replace (copy-pasted from the source code)",
  "new_line": "the replacement line",
  "confidence": 0.0 to 1.0
}

RULES:
- "replace_locator": the locator string is wrong or ambiguous. Replace it with a
  more specific one from the scraped elements. Use data-test, id, or aria-label
  selectors over generic class/text selectors.
- "add_navigation": the test navigated to the wrong URL or needs a page.goto()
  before this step. Insert a navigation line BEFORE the failing line.
- "add_wait": the test needs a wait for an element or page state. Use
  page.wait_for_selector() or page.wait_for_load_state().
- "skip_test": the failure cannot be fixed automatically (logic error, missing
  prerequisite state, site issue). The test should be skipped.
- Set "fixable": false only for truly unfixable failures (logic errors, site down).
- For locator replacements, prefer selectors with data-test, id, or aria-label.
- Do NOT change the test logic — only fix the technical issue.
- old_line must match the source code exactly (character-for-character).
- If confidence < 0.5, set "fixable": false."""


# ---------------------------------------------------------------------------
# Self-Healing Runner
# ---------------------------------------------------------------------------


class SelfHealingRunner:
    """Automated test repair loop.

    Runs failed tests, feeds errors to an LLM reviewer, applies suggested
    patches, and re-runs until tests pass or max iterations are exhausted.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        max_iterations: int = 3,
        scraped_data: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self.max_iterations = max_iterations
        self._scraped_data = scraped_data or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heal(
        self,
        test_file: str | Path,
        *,
        test_names: list[str] | None = None,
    ) -> HealingReport:
        """Run the self-healing loop on a test file.

        Args:
            test_file: Path to the generated test file.
            test_names: Optional list of specific test names to heal.
                        If None, runs all tests and heals any failures.

        Returns:
            HealingReport with fix counts, patches applied, and final results.
        """
        test_path = Path(test_file)
        if not test_path.exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")

        report = HealingReport()
        current_test_names = test_names  # None means "all tests"

        for iteration in range(1, self.max_iterations + 1):
            logger.info("Healing iteration %d/%d", iteration, self.max_iterations)

            # 1. Run tests
            run_result = self._run_pytest(test_path, current_test_names)
            failed = [r for r in run_result.results if r.status == "failed"]

            if not failed:
                logger.info("All tests pass — healing complete")
                report.total_failures = report.total_failures or 0
                report.iterations = iteration
                report.final_results = run_result.results
                return report

            # Track initial failure count on first iteration
            if iteration == 1:
                report.total_failures = len(failed)

            # 2. Read test source once
            test_source = test_path.read_text(encoding="utf-8")

            # 3. Process each failure
            fixed_this_iteration = 0
            for result in failed:
                detail = classify_failure(result.error_message)
                patch = self._review_and_suggest(result, detail, test_source)

                if patch is None:
                    report.unfixable += 1
                    continue

                # Apply the patch
                if self._apply_patch(test_path, test_source, patch):
                    report.patches.append(patch)
                    fixed_this_iteration += 1
                    # Refresh source after patch
                    test_source = test_path.read_text(encoding="utf-8")

            report.fixed += fixed_this_iteration

            if fixed_this_iteration == 0:
                logger.info("No fixable failures — stopping")
                break

            # 4. Re-run only previously-failed tests
            current_test_names = [r.name for r in failed]

        # Final state
        final_run = self._run_pytest(test_path, current_test_names)
        report.remaining = len([r for r in final_run.results if r.status == "failed"])
        report.iterations = iteration
        report.final_results = final_run.results
        return report

    # ------------------------------------------------------------------
    # Internal: test execution
    # ------------------------------------------------------------------

    @staticmethod
    def _run_pytest(
        test_path: Path,
        test_names: list[str] | None = None,
    ) -> RunResult:
        """Run pytest on a test file (optionally specific tests) and return parsed results."""
        import subprocess
        import sys

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_path),
            "-v",
            "--tb=short",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ]
        if test_names:
            for name in test_names:
                cmd.extend(["-k", name])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(test_path.parent.parent),  # repo root
            )
            output = proc.stdout + "\n" + proc.stderr
        except subprocess.TimeoutExpired:
            return RunResult(results=[], raw_output="pytest timed out after 300s")

        return parse_pytest_output(output)

    # ------------------------------------------------------------------
    # Internal: LLM reviewer
    # ------------------------------------------------------------------

    def _review_and_suggest(
        self,
        result: TestResult,
        detail: FailureDetail,
        test_source: str,
    ) -> AppliedPatch | None:
        """Send failure context to the LLM reviewer and parse the suggested patch."""
        # Extract the failing test function from source
        test_func = self._extract_test_function(test_source, result.name)
        if not test_func:
            logger.warning("Could not extract test function '%s' from source", result.name)
            return None

        # Get scraped elements for the failure URL if available
        elements_context = ""
        if detail.failure_url and detail.failure_url in self._scraped_data:
            elements = self._scraped_data[detail.failure_url][:30]
            elements_context = self._format_elements_for_prompt(elements)

        prompt = f"""FAILING TEST:
```python
{test_func}
```

ERROR MESSAGE:
{result.error_message or detail.error_message}

SCRAPED PAGE ELEMENTS (selectors, text, roles):
{elements_context or "(no scraped data available for this page)"}

Analyze this failure and suggest a fix."""

        try:
            response = self._llm.generate_test(
                prompt=prompt,
                timeout=60,
                system_prompt=REVIEWER_SYSTEM_PROMPT,
            )
            return self._parse_reviewer_response(response, result.name, test_func)
        except Exception as e:
            logger.warning("LLM reviewer failed: %s", e)
            return None

    @staticmethod
    def _extract_test_function(source: str, test_name: str) -> str | None:
        """Extract a single test function from the test file source."""
        escaped = re.escape(test_name)
        pattern = re.compile(rf"(def {escaped}\(.*?\).*?)(?=\ndef \w|\Z)", re.DOTALL)
        match = pattern.search(source)
        if not match:
            return None
        return match.group(1).strip()

    @staticmethod
    def _format_elements_for_prompt(elements: list[dict[str, Any]]) -> str:
        """Format scraped elements into a compact, LLM-friendly representation."""
        lines: list[str] = []
        for elem in elements[:30]:
            selector = elem.get("selector", "")
            text = elem.get("text", "")
            role = elem.get("role", "")
            tag = elem.get("tag", "")
            element_id = elem.get("id", "")
            data_test = elem.get("data_test", "")
            aria_label = elem.get("aria_label", "")

            parts = [f"selector={selector}"]
            if text:
                parts.append(f"text='{text[:60]}'")
            if role:
                parts.append(f"role={role}")
            if tag:
                parts.append(f"tag={tag}")
            if element_id:
                parts.append(f"id={element_id}")
            if data_test:
                parts.append(f"data-test={data_test}")
            if aria_label:
                parts.append(f"aria-label='{aria_label[:60]}'")
            lines.append(", ".join(parts))

        return "\n".join(lines)

    @staticmethod
    def _parse_reviewer_response(
        response: str,
        test_name: str,
        test_func: str,
    ) -> AppliedPatch | None:
        """Parse the LLM reviewer's JSON response into an AppliedPatch."""
        # Extract JSON from response
        json_str = response.strip()
        # Remove markdown fences if present
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", json_str)
        if json_match:
            json_str = json_match.group(1)
        # Find first { ... } block
        brace_match = re.search(r"\{[\s\S]*\}", json_str)
        if brace_match:
            json_str = brace_match.group(0)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse reviewer response as JSON: %s", e)
            return None

        if not data.get("fixable", False):
            return None

        old_line = data.get("old_line", "")
        new_line = data.get("new_line", "")
        strategy = data.get("strategy", "replace_locator")
        diagnosis = data.get("diagnosis", "No diagnosis provided")
        confidence = data.get("confidence", 0.0)

        if confidence < 0.5:
            logger.info("Reviewer confidence %.2f below threshold for '%s'", confidence, test_name)
            return None

        if not old_line or not new_line:
            return None

        # Verify old_line exists in the test function
        if old_line.strip() not in test_func:
            logger.warning("old_line not found in test function '%s'", test_name)
            return None

        # Find line number in full source
        line_number = old_line.strip().count("\n") + 1  # approximate

        return AppliedPatch(
            test_name=test_name,
            line_number=line_number,
            old_text=old_line.strip(),
            new_text=new_line.strip(),
            diagnosis=diagnosis,
            strategy=strategy,
        )

    # ------------------------------------------------------------------
    # Internal: patch application
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_patch(
        test_path: Path,
        test_source: str,
        patch: AppliedPatch,
    ) -> bool:
        """Apply a single patch to the test file. Returns True on success."""
        try:
            if patch.old_text not in test_source:
                logger.warning(
                    "Patch old_text not found in source for '%s': %s",
                    patch.test_name,
                    patch.old_text[:80],
                )
                return False

            new_source = test_source.replace(patch.old_text, patch.new_text, 1)
            test_path.write_text(new_source, encoding="utf-8")
            logger.info(
                "Applied patch for '%s' (%s): %s",
                patch.test_name,
                patch.strategy,
                patch.diagnosis[:80],
            )
            return True
        except Exception as e:
            logger.warning("Failed to apply patch: %s", e)
            return False


__all__ = ["AppliedPatch", "HealingReport", "SelfHealingRunner"]
