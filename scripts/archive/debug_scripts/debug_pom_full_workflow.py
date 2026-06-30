#!/usr/bin/env python
"""Full POM mode workflow verification script.

Demonstrates the complete real-world workflow:
1. Multi-criteria user story parsing
2. POM mode test generation
3. Page scraping and placeholder resolution
4. Test execution
5. Report generation and saving

Uses AutomationExercise.com for realistic e-commerce testing.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.journey_scraper import CredentialProfile
from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.pipeline_writer import PipelineArtifactWriter
from src.test_generator import TestGenerator
from src.user_story_parser import FeatureParser

# --- Configuration ---
BASE_URL = "https://automationexercise.com"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "generated_tests"
POM_MODE = True

# Multi-point user story with explicit acceptance criteria
USER_STORY = """As a shopper on AutomationExercise.com, I want to:
1. Browse the product catalog by category
2. Add items to my shopping cart
3. View and verify cart contents
4. Complete the checkout process

So that I can purchase products online with confidence."""

CONDITIONS = """1. Navigate to home page and verify product categories are visible
2. Select a product category (e.g., Dress) and verify product listings appear
3. Add a product to cart and verify confirmation popup appears
4. View cart and verify the added item is listed with correct details
5. Proceed to checkout and verify order summary is displayed
6. Verify login status or prompt on checkout page"""


def main() -> None:
    print("=" * 70)
    print("POM Mode Full Workflow Verification")
    print(f"Site: {BASE_URL}")
    print(f"POM Mode: {POM_MODE}")
    print("=" * 70)

    # --- Step 1: Initialize pipeline ---
    print("\n[1/6] Initializing pipeline...")
    client = LLMClient()
    print(f"  Provider: {client.provider_name}")
    print(f"  Endpoint: {client.base_url}")
    print(f"  Model: {client.model}")

    generator = TestGenerator(client=client, model_name=client.model)
    orchestrator = TestOrchestrator(
        generator,
        credential_profile=CredentialProfile(label="e2e", username="", password=""),
        pom_mode=POM_MODE,
    )

    # Parse user story
    parser = FeatureParser()
    parse_result = parser.parse(USER_STORY)
    assert parse_result.specification is not None, "Failed to parse user story"
    spec = parse_result.specification

    print(f"  User story: {spec.user_story[:80]}...")
    print(f"  Acceptance criteria: {len(spec.acceptance_criteria)} explicit criteria")

    # --- Step 2: Generate tests ---
    print("\n[2/6] Generating tests with POM mode...")
    final_code = asyncio.run(
        orchestrator.run_pipeline(
            user_story=spec.user_story,
            conditions=CONDITIONS,
            target_urls=[BASE_URL],
            consent_mode="auto-dismiss",
        )
    )

    last_result = orchestrator.last_result
    if not last_result:
        print("  FAIL: Pipeline returned no results")
        sys.exit(1)

    print(f"  Generated {len(last_result.journeys)} test(s)")
    print(f"  Page objects: {len(last_result.generated_page_objects)}")
    for po in last_result.generated_page_objects:
        print(f"    - {po.class_name} ({po.module_name}) for {po.url}")

    # Resolution diagnostics
    resolution_rate = 1.0 - (len(last_result.unresolved_placeholders) / max(len(last_result.journeys), 1))
    print(f"  Resolution rate: {resolution_rate:.1%}")
    print(f"  Unresolved: {len(last_result.unresolved_placeholders)}")

    if resolution_rate < 0.3:
        print("  WARN: Low resolution rate - check scraper output")

    # --- Step 3: Save artifacts ---
    print("\n[3/6] Saving artifacts...")
    writer = PipelineArtifactWriter(output_dir=str(OUTPUT_DIR))
    artifact_set = writer.write_run_artifacts(
        run_result=last_result,
        story_text=USER_STORY,
        base_url=BASE_URL,
        provider=client.provider_name,
        model=client.model,
    )

    test_pkg = Path(artifact_set.test_file_path).resolve().parent
    print(f"  Test package: {test_pkg.name}")
    print(f"  Test file: {Path(artifact_set.test_file_path).name}")

    # List generated files
    generated_files = list(test_pkg.rglob("*.py"))
    print(f"  Generated files: {len(generated_files)}")
    for f in generated_files[:5]:
        print(f"    - {f.relative_to(test_pkg)}")

    # --- Step 4: Verify POM structure ---
    print("\n[4/6] Verifying POM structure...")

    test_files = list(test_pkg.glob("test_*.py"))
    if not test_files:
        print("  FAIL: No test files found")
        sys.exit(1)

    test_file = test_files[0]
    test_content = test_file.read_text()

    # Check imports
    has_pom_import = "from pages." in test_content
    has_evidence_import = "evidence_tracker" in test_content
    has_pytest_import = "import pytest" in test_content

    print(f"  POM imports: {'[OK]' if has_pom_import else '[FAIL]'}")
    print(f"  Evidence tracker: {'[OK]' if has_evidence_import else '[FAIL]'}")
    print(f"  Pytest import: {'[OK]' if has_pytest_import else '[FAIL]'}")

    # Check POM instantiation
    pom_init_pattern = r"\w+ = \w+\(page,\s*evidence_tracker\)"
    has_pom_init = bool(re.search(pom_init_pattern, test_content))
    print(f"  POM instantiation: {'[OK]' if has_pom_init else '[FAIL]'}")

    # Check POM method calls
    pom_method_calls = re.findall(r"\b\w+\.(click|fill|navigate)_\w+\(", test_content)
    print(f"  POM method calls: {len(pom_method_calls)}")

    # Check assertions remain direct
    direct_asserts = re.findall(r"evidence_tracker\.assert_\w+\(", test_content)
    print(f"  Direct assertions: {len(direct_asserts)}")

    # Check pages directory
    pages_dir = test_pkg / "pages"
    pom_files = []
    if pages_dir.exists():
        pom_files = list(pages_dir.glob("*.py"))
        pom_files = [f for f in pom_files if f.name != "__init__.py"]
        print(f"  POM class files: {len(pom_files)}")
        for pf in pom_files:
            pom_content = pf.read_text()
            has_tracker = "self.tracker" in pom_content
            print(f"    - {pf.name}: {'[OK]' if has_tracker else '[FAIL]'} evidence tracker")
    else:
        print("  WARN: No pages/ directory found")

    # --- Step 5: Run tests ---
    print("\n[5/6] Running generated tests...")
    result = subprocess.run(
        [
            "pytest",
            str(test_file),
            "-v",
            "--tb=short",
            "--screenshot=only-on-failure",
        ],
        capture_output=True,
        text=True,
        cwd=str(test_pkg),
        timeout=300,  # 5 minute timeout
    )

    # Parse test results
    passed = result.stdout.count("PASSED")
    failed = result.stdout.count("FAILED")
    skipped = result.stdout.count("SKIPPED")
    errors = result.stdout.count("ERROR")

    print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped, {errors} errors")

    if result.returncode != 0:
        print("  Test output (last 20 lines):")
        for line in result.stdout.split("\n")[-20:]:
            if line.strip():
                print(f"    {line}")

    # --- Step 6: Generate report ---
    print("\n[6/6] Generating report...")

    report_data = {
        "user_story": USER_STORY,
        "conditions": CONDITIONS,
        "base_url": BASE_URL,
        "pom_mode": POM_MODE,
        "provider": client.provider_name,
        "model": client.model,
        "generation": {
            "tests_generated": len(last_result.journeys),
            "page_objects": len(last_result.generated_page_objects),
            "resolution_rate": f"{resolution_rate:.1%}",
            "unresolved_count": len(last_result.unresolved_placeholders),
        },
        "test_execution": {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
        },
        "pom_structure": {
            "has_imports": has_pom_import,
            "has_instantiation": has_pom_init,
            "method_calls": len(pom_method_calls),
            "direct_asserts": len(direct_asserts),
            "pom_files": len(pom_files) if pages_dir.exists() else 0,
        },
        "files": {
            "test_package": str(test_pkg),
            "test_file": str(test_file),
            "pages_dir": str(pages_dir) if pages_dir.exists() else None,
        },
    }

    report_path = test_pkg / "pom_workflow_report.json"
    report_path.write_text(json.dumps(report_data, indent=2))
    print(f"  Report saved: {report_path.name}")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("Workflow Summary")
    print("=" * 70)
    print(f"[OK] User story parsed: {len(spec.acceptance_criteria)} criteria")
    print(f"[OK] Tests generated: {len(last_result.journeys)}")
    print(f"[OK] Page objects: {len(last_result.generated_page_objects)}")
    print(f"[OK] Resolution rate: {resolution_rate:.1%}")
    print(f"[OK] Tests executed: {passed} passed, {skipped} skipped")
    print(f"[OK] Report saved: {report_path.name}")
    print("=" * 70)

    # Exit with appropriate code
    if failed > 0:
        print("\nFAIL: Some tests failed")
        sys.exit(1)
    elif passed == 0 and skipped == 0:
        print("\nWARN: No tests executed")
        sys.exit(1)
    else:
        print("\nSUCCESS: POM mode workflow completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
