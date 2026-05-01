"""Test Orchestrator for AI Playwright Test Generator.

This module manages the orchestration of test generation workflow including:
- Coordinating between analysis and generation stages
- Managing test case ordering based on dependencies
- Handling parallel execution configuration
- Generating executable Playwright test files

Uses the same pipeline as the Streamlit app (src/orchestrator.TestOrchestrator)
for feature parity between CLI and Streamlit frontends.
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime

from cli.config import AnalysisMode
from cli.input_parser import ParsedInput
from src.analyzer import AnalysisResult, AnalyzedTestCase, KeywordAnalyzer
from src.user_story_parser import FeatureParser

GENERATED_TESTS_DIR: str = "generated_tests"


@dataclass
class TestOrchestrationResult:
    """Container for orchestration results."""

    generated_files: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "generated_files": self.generated_files,
            "summary": self.summary,
            "errors": self.errors,
            "orchestration_timestamp": datetime.now().isoformat(),
        }


class TestCaseOrchestrator:
    """Orchestrate test case flow from analysis to generation."""

    __test__ = False

    def __init__(self, analysis_mode: AnalysisMode | None = None) -> None:
        """Initialize orchestrator."""
        self.analysis_mode: AnalysisMode = analysis_mode or AnalysisMode.FAST
        self.analyzer = KeywordAnalyzer()
        self.generated_files: list[str] = []

    def process(
        self,
        raw_input: str,
        explicit_format: str | None = None,
        url: str | None = None,
        output_dir: str = GENERATED_TESTS_DIR,
    ) -> TestOrchestrationResult:
        """
        Process user input through full orchestration pipeline.

        Args:
            raw_input: Raw user story or test case text
            explicit_format: Optional explicit format specification
            url: Optional URL to capture page context for test generation

        Returns:
            TestOrchestrationResult with generated files and summary
        """
        result = TestOrchestrationResult()

        try:
            # Step 1: Parse input
            from cli.input_parser import InputParser

            parser = InputParser()
            parsed = parser.parse(raw_input, explicit_format)

            # Step 2: Analyze test cases
            analysis_result = self._analyze_input(parsed)

            # Step 3: Order test cases by dependencies
            ordered_cases = self._order_test_cases(analysis_result.analyzed_test_cases)

            # Step 4: Generate test files (with optional page context)
            test_files = self._generate_test_files(ordered_cases, url=url, output_dir=output_dir, raw_requirements=raw_input)
            result.generated_files = test_files

            # Step 5: Create summary
            result.summary = self._create_summary(analysis_result, test_files)

        except Exception as e:
            result.errors.append(f"Orchestration error: {str(e)}")

        return result

    def process_parsed(
        self,
        parsed: ParsedInput,
        url: str | None = None,
        output_dir: str = GENERATED_TESTS_DIR,
    ) -> TestOrchestrationResult:
        """Process an already-parsed input through the full orchestration pipeline."""
        result = TestOrchestrationResult()

        try:
            analysis_result = self._analyze_input(parsed)
            ordered_cases = self._order_test_cases(analysis_result.analyzed_test_cases)
            test_files = self._generate_test_files(
                ordered_cases,
                url=url,
                output_dir=output_dir,
                raw_requirements=parsed.raw_input,
            )
            result.generated_files = test_files
            result.summary = self._create_summary(analysis_result, test_files)
        except Exception as e:
            result.errors.append(f"Orchestration error: {str(e)}")

        return result

    def _analyze_input(self, parsed: object) -> AnalysisResult:
        """Analyze parsed input using the keyword analyzer.

        Args:
            parsed: ParsedInput from cli.input_parser.InputParser

        Returns:
            AnalysisResult with analyzed test cases.
        """
        analyzed_cases: list[AnalyzedTestCase] = []
        detected_patterns: list[str] = []

        if hasattr(parsed, "test_cases") and parsed.test_cases:  # type: ignore[attr-defined]
            for tc in parsed.test_cases:  # type: ignore[attr-defined]
                title = tc.title if hasattr(tc, "title") else tc.name if hasattr(tc, "name") else "Untitled"  # type: ignore[attr-defined]
                desc = tc.description if hasattr(tc, "description") else tc.step if hasattr(tc, "step") else ""  # type: ignore[attr-defined]
                analyzed = KeywordAnalyzer.analyze(title, desc)
                analyzed_cases.append(analyzed)
                detected_patterns.extend(analyzed.identified_actions)
        elif hasattr(parsed, "story"):
            story = parsed.story if hasattr(parsed, "story") else str(parsed)  # type: ignore[attr-defined]
            title = "User Story"
            analyzed = KeywordAnalyzer.analyze(title, str(story))
            analyzed_cases.append(analyzed)
            detected_patterns.extend(analyzed.identified_actions)
        else:
            story = str(parsed)
            title = "Input"
            analyzed = KeywordAnalyzer.analyze(title, story)
            analyzed_cases.append(analyzed)
            detected_patterns.extend(analyzed.identified_actions)

        return AnalysisResult(
            analyzed_test_cases=analyzed_cases,
            analysis_summary={
                "complexity_distribution": {},
                "requires_auth": False,
            },
            detected_patterns=detected_patterns,
        )

    def _order_test_cases(self, cases: list[AnalyzedTestCase]) -> list[AnalyzedTestCase]:
        """
        Order test cases based on dependencies and complexity.

        Topological sort approach:
        1. Cases with no dependencies first
        2. Then cases that depend on completed cases
        3. Within same dependency level, order by complexity (low to high)
        """
        if not cases:
            return []

        ordered: list[AnalyzedTestCase] = []
        remaining = list(cases)
        completed_ids: set[int] = set()

        while remaining:
            # Find cases with all dependencies satisfied
            ready: list[AnalyzedTestCase] = []
            not_ready: list[AnalyzedTestCase] = []

            for case in remaining:
                deps_satisfied = self._check_dependencies_satisfied(case, completed_ids)
                if deps_satisfied:
                    ready.append(case)
                else:
                    not_ready.append(case)

            if not ready:
                # Circular dependency or unsatisfied deps - add remaining
                ordered.extend(remaining)
                break

            # Sort ready cases by complexity (low to high)
            ready.sort(key=lambda c: self._complexity_score(c.estimated_complexity))

            # Add ready cases to ordered list
            for c in ready:
                ordered.append(c)
                completed_ids.add(id(c))

            remaining = not_ready

        return ordered

    def _check_dependencies_satisfied(self, case: AnalyzedTestCase, completed_ids: set[int]) -> bool:
        """Check if all dependencies for a case are satisfied.

        The ``AnalyzedTestCase.dependencies`` field is a list of human-readable
        strings that may contain markers such as ``"Depends on: <title>"``.
        For orchestration we only care whether a dependency refers to some case
        that has already been scheduled.
        """
        if not case.dependencies:
            return True
        if not completed_ids:
            return False
        for dep in case.dependencies:
            text = dep or ""
            if "depends on:" not in text.lower():
                continue
            found = False
            for completed in completed_ids:
                if completed in completed_ids:
                    found = True
                    break
            if not found:
                return False
        return True

    def _complexity_score(self, complexity: str) -> int:
        """Convert complexity to numeric score for sorting."""
        scores: dict[str, int] = {"low": 1, "medium": 2, "high": 3}
        return scores.get(complexity, 2)

    def _generate_test_files(
        self,
        cases: list[AnalyzedTestCase],
        url: str | None = None,
        output_dir: str = GENERATED_TESTS_DIR,
        raw_requirements: str = "",
    ) -> list[str]:
        """Generate Playwright test files from analyzed test cases.

        Uses the same TestOrchestrator pipeline as the Streamlit app for
        feature parity between CLI and Streamlit frontends.
        """
        if not cases:
            return []

        generated: list[str] = []
        os.makedirs(output_dir, exist_ok=True)

        # Determine target URL(s)
        target_urls: list[str] = []
        if url:
            target_urls = [url]

        # Create LLM client and TestGenerator for the orchestrator
        from src.llm_client import LLMClient
        from src.orchestrator import TestOrchestrator
        from src.pipeline_writer import PipelineArtifactWriter
        from src.test_generator import TestGenerator

        client = LLMClient()
        generator = TestGenerator(client=client)
        orchestrator = TestOrchestrator(generator)

        feature_spec_request = self._build_feature_spec_request(raw_requirements)
        if feature_spec_request is not None:
            user_story, conditions_text = feature_spec_request
            try:
                print("  Generating full feature spec from parsed acceptance criteria...")
                asyncio.run(
                    orchestrator.run_pipeline(
                        user_story=user_story,
                        conditions=conditions_text,
                        target_urls=target_urls,
                        consent_mode="auto-dismiss",
                    )
                )

                if orchestrator.last_result is None:
                    raise RuntimeError("No pipeline result for parsed feature specification")

                artifact_writer = PipelineArtifactWriter(output_dir=output_dir)
                artifact_set = artifact_writer.write_run_artifacts(
                    run_result=orchestrator.last_result,
                    story_text="Main Flow",
                    base_url=target_urls[0] if target_urls else "",
                )
                generated.append(artifact_set.test_file_path)
                print(f"    [OK] Saved to {artifact_set.test_file_path}")
                self.generated_files = generated
                return generated
            except Exception as e:
                error_msg = f"Warning: Failed to generate parsed feature spec: {e}"
                print(f"    {error_msg}")
                self.generated_files = generated
                return generated

        # Run the pipeline for each case individually (like the Streamlit app)
        for idx, case in enumerate(cases):
            case_user_story = case.title if hasattr(case, "title") else f"Test case {idx + 1}"
            case_description = case.description if hasattr(case, "description") else ""
            case_expected = case.expected_outcome if hasattr(case, "expected_outcome") else ""
            case_conditions = f"{case_description}\nExpected: {case_expected}"

            try:
                print(f"  Generating test {idx + 1}/{len(cases)}: {case_user_story}...")
                asyncio.run(
                    orchestrator.run_pipeline(
                        user_story=case_user_story,
                        conditions=case_conditions,
                        target_urls=target_urls,
                        consent_mode="auto-dismiss",
                    )
                )

                # Save using PipelineArtifactWriter (same as Streamlit)
                if orchestrator.last_result is None:
                    raise RuntimeError(f"No pipeline result for {case_user_story}")
                artifact_writer = PipelineArtifactWriter(output_dir=output_dir)
                artifact_set = artifact_writer.write_run_artifacts(
                    run_result=orchestrator.last_result,
                    story_text=case_user_story,
                    base_url=target_urls[0] if target_urls else "",
                )
                generated.append(artifact_set.test_file_path)
                print(f"    [OK] Saved to {artifact_set.test_file_path}")

            except Exception as e:
                error_msg = f"Warning: Failed to generate test for {case_user_story}: {e}"
                print(f"    {error_msg}")
                self.generated_files = generated
                return generated

        self.generated_files = generated
        return generated

    @staticmethod
    def _build_feature_spec_request(raw_requirements: str) -> tuple[str, str] | None:
        """Return `(user_story, numbered_conditions)` for markdown-style requirement specs."""
        if not raw_requirements.strip():
            return None

        parser = FeatureParser()
        parse_result = parser.parse(raw_requirements)
        specification = parse_result.specification if parse_result.success else None
        if specification is None or not specification.acceptance_criteria:
            return None

        requirement_model = parser.build_requirement_model(specification)
        if requirement_model.count == 0:
            return None

        return specification.user_story.strip(), requirement_model.to_numbered_text().strip()

    def _generate_test_content(self, test_type: str, cases: list[AnalyzedTestCase]) -> str:
        """Generate Playwright test file content."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Generate imports
        imports: list[str] = [
            "from playwright.sync_api import Page, expect, Playwright, sync_playwright",
            "import pytest",
            "import os",
            "from datetime import datetime",
            "",
        ]

        # Generate test class header
        class_lines: list[str] = [
            f"class Test{test_type.title().replace(' ', '')}:",
            f'    """Auto-generated test class for {test_type} scenarios.',
            f"    Generated from AI Playwright Test Generator on {timestamp}",
            f"    Source analysis: {len(cases)} test cases",
            '    """',
            "",
            "    @pytest.fixture",
            "    def browser(self, playwright: Playwright):",
            '        """Setup browser configuration."""',
            "        browser = playwright.chromium.launch(headless=True)",
            "        context = browser.new_context(",
            "            viewport={'width': 1280, 'height': 720}",
            "        )",
            "        return context.new_page()",
            "",
            "    @pytest.fixture(autouse=True)",
            "    def setup_teardown(self, browser: Page):",
            '        """Auto setup and teardown for each test."""',
            "        # Setup",
            "        yield",
            "        # Teardown",
            "        browser.close()",
            "",
        ]
        class_header = "\n".join(class_lines)

        # Generate test methods
        test_methods: list[str] = []
        for idx, case in enumerate(cases, 1):
            test_method = self._generate_test_method(idx, case, len(cases))
            test_methods.append(test_method)

        # Assemble file content
        content = "\n".join(imports) + "\n" + class_header + "".join(test_methods)

        return content

    def _generate_test_method(self, idx: int, case: AnalyzedTestCase, total: int) -> str:
        """Generate a single test method from an analyzed test case."""
        method_name = f"test_{self._sanitize_name(case.title)}"

        method_lines: list[str] = [
            f'        """Test: {case.title}\n        Description: {case.description}\n        Expected: {case.expected_outcome}."""',
            "",
        ]

        if case.preconditions:
            method_lines.append(f"        # Precondition: {case.preconditions}")

        method_lines.extend(self._generate_steps_from_description(case))

        if case.identified_expectations:
            method_lines.append(f"        # Verify expectations: {', '.join(case.identified_expectations)}")
            for _exp in case.identified_expectations[:2]:
                method_lines.append("        expect(page).to_be_visible()")

        if idx < total:
            method_lines.append("        # Navigate to next step")
            method_lines.append("        pass")

        return f"""
    def {method_name}(self, page: Page):
        {"".join(method_lines)}

"""

    def _generate_steps_from_description(self, case: AnalyzedTestCase) -> list[str]:
        """Generate Playwright steps from test case description."""
        steps: list[str] = []
        description = case.description.lower()

        if "navigate" in description or "go to" in description or "open" in description:
            url = self._extract_url(case.description)
            if url:
                steps.append(f"        page.goto('{url}')")
            else:
                steps.append("        # Navigate to target page")

        if "login" in description or "sign in" in description:
            steps.append("        # Login steps")
            if case.suggested_data.get("email"):
                steps.append(f"        page.fill('[data-testid=email]', '{case.suggested_data['email']}')")
            if case.suggested_data.get("password"):
                steps.append(f"        page.fill('[data-testid=password]', '{case.suggested_data['password']}')")
            steps.append("        page.click('[data-testid=login-button]')")

        if "form" in description or "fill" in description:
            steps.append("        # Fill form fields")
            if case.suggested_data.get("form_data"):
                for field_name, value in case.suggested_data["form_data"].items():
                    steps.append(f"        page.fill('[data-testid={field_name}]', '{value}')")

        if "click" in description or "submit" in description:
            steps.append("        page.click('[data-testid=submit-button]')")

        if "search" in description:
            steps.append("        # Search action")
            steps.append("        page.fill('[data-testid=search]', 'search term')")
            steps.append("        page.click('[data-testid=search-button]')")

        if not steps:
            steps.append("        # Test step placeholder")
            steps.append("        pass")

        return steps

    def _sanitize_name(self, name: str) -> str:
        """Convert name to valid Python identifier."""
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        sanitized = sanitized.strip("_").lower()
        if not sanitized or sanitized[0].isdigit():
            sanitized = f"test_{sanitized}"
        return sanitized

    def _extract_url(self, text: str) -> str | None:
        """Extract URL from text if present."""
        import re

        url_pattern = r"https?://[^\s<>\"']+"
        match = re.search(url_pattern, text)
        return match.group(0) if match else None

    def _create_summary(self, analysis: AnalysisResult, files: list[str]) -> dict:
        """Create orchestration summary."""
        return {
            "total_cases_analyzed": len(analysis.analyzed_test_cases),
            "files_generated": len(files),
            "file_names": [os.path.basename(f) for f in files],
            "analysis_mode": self.analysis_mode.value,
            "complexity_distribution": analysis.analysis_summary.get("complexity_distribution", {}),
            "requires_authentication": analysis.analysis_summary.get("requires_auth", False),
            "orchestration_timestamp": datetime.now().isoformat(),
        }
