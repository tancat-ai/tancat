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

import glob
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.failure_classifier import FailureCategory, FailureDetail, classify_failure
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
    # Locator corrections written back to the RAG store (AI-035 self-healing
    # write-back). Never breaks healing if learning fails.
    learned: int = 0
    # Failures that are locator-type but couldn't be auto-fixed — candidates
    # for interactive repair (opens browser, user clicks correct element).
    interactive_repair_candidates: list[dict[str, Any]] = field(default_factory=list)
    # Per-test attempt history: test_name -> list of {strategy, old_text, new_text,
    # outcome} records. Drives the reflection loop so the LLM knows what was tried.
    attempt_history: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    # Total LLM calls made (for cost monitoring across iterations).
    total_llm_calls: int = 0

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
4. Optionally: PREVIOUS FIX ATTEMPTS — what was already tried and why it failed

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
- If confidence < 0.5, set "fixable": false.

REFLECTION RULES (when PREVIOUS FIX ATTEMPTS are provided):
- Do NOT repeat a strategy that already failed. If replace_locator failed, try
  add_wait or a different selector approach.
- If the same locator keeps timing out, the element may not exist on this page —
  consider add_navigation to ensure the test is on the correct page first.
- If two different locator replacements both failed, the real issue may be page
  load timing — try add_wait (page.wait_for_load_state or wait_for_selector).
- Mention in your diagnosis WHY the previous attempt failed and how your new
  approach differs."""


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
        rag_store: Any | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self.max_iterations = max_iterations
        self._scraped_data = scraped_data or {}
        # AI-035: injectable RAG store for the self-healing write-back (tests
        # pass an in-memory store; production defaults to the real store).
        self._rag_store = rag_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heal(
        self,
        test_file: str | Path,
        *,
        test_names: list[str] | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> HealingReport:
        """Run the self-healing loop on a test file.

        Args:
            test_file: Path to the generated test file.
            test_names: Optional list of specific test names to heal.
            on_progress: Optional callback for progress messages (e.g., Streamlit status).

        Returns:
            HealingReport with fix counts, patches applied, and final results.
        """

        def _progress(msg: str) -> None:
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        test_path = Path(test_file)
        if not test_path.exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")

        report = HealingReport()
        current_test_names = test_names  # None means "all tests"
        # Track per-test attempt history across iterations for reflection
        per_test_attempts: dict[str, list[dict[str, str]]] = {}

        for iteration in range(1, self.max_iterations + 1):
            _progress(f"Healing iteration {iteration}/{self.max_iterations} — running tests...")

            # 1. Run tests
            run_result = self._run_pytest(test_path, current_test_names)
            failed = [r for r in run_result.results if r.status == "failed"]

            if not failed:
                _progress("All tests pass — healing complete!")
                report.total_failures = report.total_failures or 0
                report.iterations = iteration
                report.final_results = run_result.results
                report.attempt_history = dict(per_test_attempts)
                return report

            # Track initial failure count on first iteration
            if iteration == 1:
                report.total_failures = len(failed)
                _progress(f"Found {len(failed)} failed test(s). Analyzing with LLM reviewer...")

            # 2. Read test source once
            test_source = test_path.read_text(encoding="utf-8")

            # 3. Process each failure
            fixed_this_iteration = 0
            for result in failed:
                _progress(f"Reviewing: {result.name}...")
                detail = classify_failure(result.error_message)

                # Pre-screen: skip LLM for clearly unfixable failures
                if not self._pre_screen_failure(detail):
                    _progress(f"  ⏭ Pre-screened as unfixable ({detail.category})")
                    report.unfixable += 1
                    self._maybe_add_interactive_candidate(report, result, detail)
                    continue

                # Get prior attempts for this test (reflection context)
                prior = per_test_attempts.get(result.name, [])
                patch = self._review_and_suggest(result, detail, test_source, prior_attempts=prior)
                report.total_llm_calls += 1  # Count each LLM reviewer call

                if patch is None:
                    report.unfixable += 1
                    self._maybe_add_interactive_candidate(report, result, detail)
                    continue

                # Apply the patch
                if self._apply_patch(test_path, test_source, patch):
                    report.patches.append(patch)
                    fixed_this_iteration += 1
                    # AI-035: a verified locator replacement writes back to the
                    # RAG store (guarded — learning never breaks healing).
                    if patch.strategy == "replace_locator" and self._learn_from_patch(test_path, result, patch):
                        report.learned += 1
                    # Record the attempt for reflection if it fails again
                    per_test_attempts.setdefault(result.name, []).append(
                        {
                            "strategy": patch.strategy,
                            "old_text": patch.old_text[:120],
                            "new_text": patch.new_text[:120],
                            "diagnosis": patch.diagnosis,
                        }
                    )
                    # Refresh source after patch
                    test_source = test_path.read_text(encoding="utf-8")
                else:
                    report.unfixable += 1
                    per_test_attempts.setdefault(result.name, []).append(
                        {
                            "strategy": patch.strategy,
                            "old_text": patch.old_text[:120],
                            "new_text": patch.new_text[:120],
                            "diagnosis": f"PATCH FAILED: {patch.diagnosis}",
                        }
                    )

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
        report.attempt_history = dict(per_test_attempts)
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
            str(test_path.absolute()),
            "-v",
            "--tb=short",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",  # Override pytest.ini addopts (disables xdist parallel mode outside uv)
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
    # Internal: pre-screening
    # ------------------------------------------------------------------

    @staticmethod
    def _pre_screen_failure(detail: FailureDetail) -> bool:
        """Pre-screen: return True if failure is worth sending to the LLM.

        Skips the LLM call for failures that cannot be fixed by code changes:
        - ASSERTION_FAILURE: logic/test error, not a locator issue
        - NAVIGATION_ERROR: site down, connection refused — nothing to fix
        - OTHER: unknown error with no actionable locator signal

        LOCATOR_TIMEOUT and STRICT_VIOLATION are worth LLM review — the LLM
        can suggest better selectors or disambiguation strategies.
        """
        if detail.category in (
            FailureCategory.ASSERTION_FAILURE,
            FailureCategory.NAVIGATION_ERROR,
        ):
            return False
        if detail.category == FailureCategory.OTHER:
            return False
        # LOCATOR_TIMEOUT and STRICT_VIOLATION are worth LLM review
        return True

    @staticmethod
    def _maybe_add_interactive_candidate(
        report: HealingReport,
        result: TestResult,
        detail: FailureDetail,
    ) -> None:
        """Add failure to interactive repair candidates if it's a locator-type failure.

        Only LOCATOR_TIMEOUT and STRICT_VIOLATION failures can benefit from
        interactive repair (open browser → user clicks correct element → capture locator).
        """
        if detail.category in (
            FailureCategory.LOCATOR_TIMEOUT,
            FailureCategory.STRICT_VIOLATION,
        ):
            report.interactive_repair_candidates.append(
                {
                    "test_name": result.name,
                    "raw_locator": detail.raw_locator,
                    "error_message": detail.error_message,
                    "failure_url": detail.failure_url,
                }
            )

    # ------------------------------------------------------------------
    # Internal: LLM reviewer
    # ------------------------------------------------------------------

    def _review_and_suggest(
        self,
        result: TestResult,
        detail: FailureDetail,
        test_source: str,
        prior_attempts: list[dict[str, str]] | None = None,
    ) -> AppliedPatch | None:
        """Send failure context to the LLM reviewer and parse the suggested patch.

        Args:
            result: The failed test result.
            detail: Classified failure details.
            test_source: Full test file source code.
            prior_attempts: Previous fix attempts for this test (for reflection).
                Each entry: {strategy, old_text, new_text, diagnosis}.
        """
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

        # Build prior attempts section for reflection
        prior_section = ""
        if prior_attempts:
            lines = ["PREVIOUS FIX ATTEMPTS (all failed):"]
            for i, attempt in enumerate(prior_attempts, 1):
                lines.append(
                    f"  {i}. {attempt['strategy']}: '{attempt['old_text'][:80]}' -> '{attempt['new_text'][:80]}'"
                )
                if attempt.get("diagnosis"):
                    lines.append(f"     Diagnosis: {attempt['diagnosis'][:120]}")
            lines.append("")
            lines.append("Do NOT repeat any strategy that already failed. Try a different approach.")
            prior_section = "\n".join(lines) + "\n\n"

        prompt = f"""FAILING TEST:
```python
{test_func}
```

ERROR MESSAGE:
{result.error_message or detail.error_message}

{prior_section}SCRAPED PAGE ELEMENTS (selectors, text, roles):
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

        # Verify old_line exists in the test function.
        # Normalise quotes: LLMs often return single-quoted strings while
        # Python source uses double quotes (or vice versa).
        old_normalised = old_line.strip().replace('"', "'").replace("'", "'")
        func_normalised = test_func.replace('"', "'").replace("'", "'")
        if old_normalised not in func_normalised:
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
    # Internal: AI-035 self-healing → RAG write-back
    # ------------------------------------------------------------------

    @staticmethod
    def _evidence_context(
        test_path: Path,
        test_name: str,
    ) -> tuple[list[dict[str, Any]], str]:
        """Recover (evidence_steps, base_url) for a failing test, best-effort.

        The evidence sidecar (``<package>/evidence/<test>.evidence.json``)
        records the resolved steps — labels carry the placeholder descriptions
        the resolver looks up by, and ``page.url`` scopes the learned pattern
        to the site domain. Falls back to the package manifest's
        ``starting_url`` when no sidecar exists. Never raises.
        """
        package_dir = test_path.parent
        evidence_dir = package_dir / "evidence"

        def _try_read(sidecar: Path) -> tuple[list[dict[str, Any]], str] | None:
            try:
                if not sidecar.exists():
                    return None
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                steps = data.get("steps") if isinstance(data, dict) else None
                page = data.get("page") if isinstance(data, dict) else None
                url = str((page or {}).get("url", "") or "") if isinstance(page, dict) else ""
                return (steps if isinstance(steps, list) else []), url
            except Exception:
                return None

        # Exact name first (non-parametrized tests), then the [param] suffix
        # variant — the sidecar keeps the FULL pytest node name while
        # ``result.name`` has the suffix stripped by the output parser.
        stripped = test_name.split("[", 1)[0]
        for name in (f"{test_name}.evidence.json", f"{stripped}.evidence.json"):
            for sidecar in (evidence_dir / name, package_dir / name):
                found = _try_read(sidecar)
                if found is not None:
                    return found

        # Glob fallback: test_04_click -> test_04_click[chromium].evidence.json
        # (escape the prefix — "[chromium]" in a node name would otherwise be
        # interpreted as a glob character class).
        for sidecar in sorted(evidence_dir.glob(glob.escape(stripped) + "*.evidence.json")):
            found = _try_read(sidecar)
            if found is not None:
                return found

        # Fallback: package scrape/package manifest carries starting_url.
        for manifest_name in ("scrape_manifest.json", "package_manifest.json"):
            try:
                manifest_path = package_dir / manifest_name
                if not manifest_path.exists():
                    continue
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                url = str(data.get("starting_url", "") or data.get("base_url", "") or "")
                if url:
                    return [], url
            except Exception:
                continue
        return [], ""

    def _learn_from_patch(
        self,
        test_path: Path,
        result: TestResult,
        patch: AppliedPatch,
    ) -> bool:
        """Write a self-healing-corrected locator to the RAG store.

        Returns True when the pattern was upserted (new or dedup'd hit).
        Best-effort and guarded: a learning failure never breaks healing.
        Only ``replace_locator`` patches carry a usable corrected selector.
        """
        if patch.strategy != "replace_locator":
            return False
        try:
            from src.rag_learn import learn_from_patch as _learn

            evidence_steps, base_url = self._evidence_context(test_path, result.name)
            outcome = _learn(
                old_text=patch.old_text,
                new_text=patch.new_text,
                base_url=base_url,
                evidence_steps=evidence_steps,
                store=self._rag_store,
            )
            learned = outcome.get("inserted", 0) + outcome.get("exists", 0) > 0
            if learned:
                logger.info("Self-healing wrote pattern for '%s' to RAG store", result.name)
            return learned
        except Exception as exc:
            logger.warning("Self-healing learn-back failed (non-fatal): %s", exc)
            return False

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
            # Normalise quotes for matching (LLM returns single quotes, source may use double)
            old_norm = patch.old_text.replace('"', "'")
            src_norm = test_source.replace('"', "'")
            if old_norm not in src_norm:
                logger.warning(
                    "Patch old_text not found in source for '%s': %s",
                    patch.test_name,
                    patch.old_text[:80],
                )
                return False

            # Find the actual line in source to replace (preserving original quotes)
            old_lines = patch.old_text.split("\n")
            src_lines = test_source.split("\n")
            actual_old = patch.old_text  # fallback
            for i, line in enumerate(src_lines):
                if line.strip().replace('"', "'") == old_norm.split("\n")[0].strip():
                    actual_old = "\n".join(src_lines[i : i + len(old_lines)])
                    break

            new_source = test_source.replace(actual_old, patch.new_text, 1)
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
