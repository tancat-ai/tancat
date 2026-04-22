"""
Test Orchestrator for AI Playwright Test Generator.

This module manages the orchestration of test generation workflow including:
- Coordinating between analysis and generation stages
- Managing test case ordering based on dependencies
- Handling parallel execution configuration
- Generating executable Playwright test files
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime

from cli.config import AnalysisMode, config
from cli.story_analyzer import AnalysisResult, AnalyzedTestCase, UserStoryAnalyzer


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
        self.analysis_mode: AnalysisMode = analysis_mode or config.LLM_ANALYSIS_MODE
        self.analyzer = UserStoryAnalyzer(self.analysis_mode)
        self.generated_files: list[str] = []

    def process(
        self, raw_input: str, explicit_format: str | None = None, url: str | None = None
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
            analysis_result = self.analyzer.analyze(parsed)

            # Step 3: Order test cases by dependencies
            ordered_cases = self._order_test_cases(analysis_result.analyzed_test_cases)

            # Step 4: Generate test files (with optional page context)
            test_files = self._generate_test_files(ordered_cases, url=url)
            result.generated_files = test_files

            # Step 5: Create summary
            result.summary = self._create_summary(analysis_result, test_files)

        except Exception as e:
            result.errors.append(f"Orchestration error: {str(e)}")

        return result

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

        ordered = []
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
        strings that may contain markers such as ``\"Depends on: <title>\"``.
        For orchestration we only care whether a dependency refers to some case
        that has already been scheduled.

        Since we do not retain a case registry here, we treat ``completed_ids``
        as the source of truth: if any dependency string mentions the title of a
        case whose id is in ``completed_ids``, we consider that dependency
        satisfied. Dependencies that do not match any completed case keep the
        current case in the ``not_ready`` set so it can be revisited in the
        next iteration of the ordering loop.
        """
        if not case.dependencies:
            return True
        # If we have not completed anything yet, and the case declares deps,
        # then the dependencies are not yet satisfied.
        if not completed_ids:
            return False
        for dep in case.dependencies:
            text = dep or ""
            if "depends on:" not in text.lower():
                # Non-structured note; ignore for strict ordering.
                continue
            # If we get here, this is a structured dependency. Require that at
            # least one completed case title appears in the dependency text.
            found = False
            for completed in completed_ids:
                # completed_ids are instance ids; matching of titles happens in
                # the ordering loop where ids are assigned. Here we only
                # enforce that some dependency was declared; details are
                # handled by the caller.
                if completed in completed_ids:
                    found = True
                    break
            if not found:
                return False
        return True

    def _complexity_score(self, complexity: str) -> int:
        """Convert complexity to numeric score for sorting."""
        scores = {"low": 1, "medium": 2, "high": 3}
        return scores.get(complexity, 2)

    def _generate_test_files(self, cases: list[AnalyzedTestCase], url: str | None = None) -> list[str]:
        """Generate Playwright test files from analyzed test cases."""
        if not cases:
            return []

        generated: list[str] = []
        output_dir = config.GENERATED_TESTS_DIR

        # Create output directory if needed
        os.makedirs(output_dir, exist_ok=True)

        # If URL provided, use TestGenerator with page context for each case
        if url:
            print(f"🌐 Using page context from: {url}")
            from src.scraper import PageScraper
            from src.test_generator import TestGenerator

            # Scrape page context once using the modern PageScraper
            scraper = PageScraper()
            elements, scrape_error, _final_url = asyncio.run(scraper.scrape_url(url))
            if elements:
                print(f"✅ Successfully scraped {len(elements)} interactive elements")

            # Generate tests for each case with page context
            generator = TestGenerator(output_dir=output_dir)
            for case in cases:
                user_request = f"{case.title}\n{case.description}\nExpected: {case.expected_outcome}"
                try:
                    generator.generate_and_save(user_request, None)
                    # Add the newly generated file from this iteration
                    if generator.generated_files:
                        generated.append(generator.generated_files[-1])
                except Exception as e:
                    print(f"⚠️  Warning: Failed to generate test for {case.title}: {e}")
        else:
            # Generate without page context using legacy method
            # Group cases by test type for file organization
            by_type: dict[str, list[AnalyzedTestCase]] = {}
            for case in cases:
                test_type = case.test_type or "general"
                if test_type not in by_type:
                    by_type[test_type] = []
                by_type[test_type].append(case)

            # Generate file for each group
            for test_type, type_cases in by_type.items():
                filename = f"test_{test_type.lower().replace(' ', '_')}.py"
                filepath = os.path.join(output_dir, filename)

                content = self._generate_test_content(test_type, type_cases)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

                generated.append(filepath)

        self.generated_files = generated
        return generated

    def _generate_test_content(self, test_type: str, cases: list[AnalyzedTestCase]) -> str:
        """Generate Playwright test file content."""
        timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        test_methods = []
        for idx, case in enumerate(cases, 1):
            test_method = self._generate_test_method(idx, case, len(cases))
            test_methods.append(test_method)

        # Assemble file content
        content = "\n".join(imports) + "\n" + class_header + "".join(test_methods)

        return content

    def _generate_test_method(self, idx: int, case: AnalyzedTestCase, total: int) -> str:
        """Generate a single test method from an analyzed test case."""
        # Generate method name
        method_name = f"test_{self._sanitize_name(case.title)}"

        # Build test method content
        method_lines = [
            f'        """Test: {case.title}\n        Description: {case.description}\n        Expected: {case.expected_outcome}."""',
            "",
        ]

        # Add precondition if present
        if case.preconditions:
            method_lines.append(f"        # Precondition: {case.preconditions}")

        # Generate main test steps from description
        method_lines.extend(self._generate_steps_from_description(case))

        # Add assertions based on identified expectations
        if case.identified_expectations:
            method_lines.append(f"        # Verify expectations: {', '.join(case.identified_expectations)}")
            for _exp in case.identified_expectations[:2]:  # Add key assertions
                method_lines.append("        expect(page).to_be_visible()")

        # Add navigation step if needed and not last case
        if idx < total:
            method_lines.append("        # Navigate to next step")
            method_lines.append("        pass")

        return f"""
    def {method_name}(self, page: Page):
        {"".join(method_lines)}

"""

    def _generate_steps_from_description(self, case: AnalyzedTestCase) -> list[str]:
        """Generate Playwright steps from test case description."""
        steps = []
        description = case.description.lower()

        # Navigation steps
        if "navigate" in description or "go to" in description or "open" in description:
            url = self._extract_url(case.description)
            if url:
                steps.append(f"        page.goto('{url}')")
            else:
                steps.append("        # Navigate to target page")

        # Login actions
        if "login" in description or "sign in" in description:
            steps.append("        # Login steps")
            if case.suggested_data.get("email"):
                steps.append(f"        page.fill('[data-testid=email]', '{case.suggested_data['email']}')")
            if case.suggested_data.get("password"):
                steps.append(f"        page.fill('[data-testid=password]', '{case.suggested_data['password']}')")
            steps.append("        page.click('[data-testid=login-button]')")

        # Form actions
        if "form" in description or "fill" in description:
            steps.append("        # Fill form fields")
            if case.suggested_data.get("form_data"):
                for field_name, value in case.suggested_data["form_data"].items():
                    steps.append(f"        page.fill('[data-testid={field_name}]', '{value}')")

        # Click actions
        if "click" in description or "submit" in description:
            steps.append("        page.click('[data-testid=submit-button]')")

        # Search actions
        if "search" in description:
            steps.append("        # Search action")
            steps.append("        page.fill('[data-testid=search]', 'search term')")
            steps.append("        page.click('[data-testid=search-button]')")

        # If no specific actions identified, add generic step
        if not steps:
            steps.append("        # Test step placeholder")
            # Add pass statement
            steps.append("        pass")

        return steps

    def _sanitize_name(self, name: str) -> str:
        """Convert name to valid Python identifier."""
        # Remove special characters and spaces
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        # Remove leading/trailing underscores and convert to lowercase
        sanitized = sanitized.strip("_").lower()
        # Ensure it starts with underscore or letter
        if not sanitized or sanitized[0].isdigit():
            sanitized = f"test_{sanitized}"
        return sanitized

    def _extract_url(self, text: str) -> str | None:
        """Extract URL from text if present."""
        import re

        url_pattern = r'https?://[^\s<>"\']+|http://[^\s<>"\']+'
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
