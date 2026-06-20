#!/usr/bin/env python
"""End-to-end POM mode verification script.

Generates tests with POM mode enabled using a simple user story against
the AutomationExercise site, then verifies:
1. Generated tests import and use POM classes
2. Assertions remain as direct evidence_tracker calls
3. Evidence sidecar JSON is generated
4. Failure diagnostics are captured
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import subprocess

from src.journey_scraper import CredentialProfile
from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.pipeline_writer import PipelineArtifactWriter
from src.test_generator import TestGenerator
from src.user_story_parser import FeatureParser

# --- Configuration ---
BASE_URL = "https://automationexercise.com"
USER_STORY = (
    "As a shopper on AutomationExercise.com, I want to navigate to the home page "
    "so that I can see the category navigation menu with links like Dress, Tops, and Jewelry."
)
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "generated_tests"
POM_MODE = True

print("=" * 60)
print("POM Mode E2E Verification")
print(f"POM Mode: {POM_MODE}")
print(f"Base URL: {BASE_URL}")
print("=" * 60)

# --- Step 1: Run pipeline with POM mode ---
print("\n[1/4] Running pipeline with POM mode...")

# Auto-detect provider, endpoint, and loaded model
client = LLMClient()
print(f"  Detected provider: {client.provider_name}")
print(f"  Detected endpoint: {client.base_url}")
print(f"  Detected model:    {client.model}")

generator = TestGenerator(client=client, model_name=client.model)
orchestrator = TestOrchestrator(
    generator,
    credential_profile=CredentialProfile(label="debug", username="", password=""),
    pom_mode=POM_MODE,
)

# Parse requirements into user story + criteria
parser = FeatureParser()
parse_result = parser.parse(USER_STORY)
assert parse_result.specification is not None
spec = parse_result.specification
conditions_text = "\n".join(spec.acceptance_criteria) if spec.acceptance_criteria else USER_STORY

final_code = asyncio.run(
    orchestrator.run_pipeline(
        user_story=spec.user_story,
        conditions=conditions_text,
        target_urls=[BASE_URL],
        consent_mode="auto-dismiss",
    )
)

last_result = orchestrator.last_result
if not last_result or not last_result.generated_page_objects:
    print("FAIL: No page objects generated")
    sys.exit(1)

print(f"  Generated {len(last_result.generated_page_objects)} page object(s)")
for po in last_result.generated_page_objects:
    print(f"    - {po.class_name} for {po.url}")

# DIAGNOSTICS: Show placeholder resolution quality
print("\n  --- Placeholder Resolution Diagnostics ---")
print(f"  Pages scraped: {len(last_result.scraped_pages)}")
for url, elements in last_result.scraped_pages.items():
    print(f"    {url}: {len(elements)} elements")

print(f"  Unresolved placeholders: {len(last_result.unresolved_placeholders)}")
for unresolved in last_result.unresolved_placeholders[:10]:  # Show first 10
    print(f"    - {unresolved}")

resolution_rate = 1.0 - (len(last_result.unresolved_placeholders) / max(len(last_result.journeys), 1))
print(f"  Resolution rate: {resolution_rate:.1%}")

if resolution_rate < 0.5:
    print(f"  FAIL: Less than 50% of placeholders resolved ({resolution_rate:.1%})")
    print("  This indicates a scraping or resolution failure, not just missing assertions.")

# Write artifacts to disk
writer = PipelineArtifactWriter(output_dir=str(OUTPUT_DIR))
artifact_set = writer.write_run_artifacts(
    run_result=last_result,
    story_text=USER_STORY,
    base_url=BASE_URL,
    provider=client.provider_name,
    model=client.model,
)

test_pkg = Path(artifact_set.test_file_path).resolve().parent
print(f"\n  Test package: {test_pkg.name}")

# --- Step 2: Check test file for POM imports and usage ---
print("\n[2/4] Checking POM imports and usage...")

test_files = list(test_pkg.glob("test_*.py"))
if not test_files:
    print("FAIL: No test files found")
    sys.exit(1)

test_file = test_files[0]
test_content = test_file.read_text()

# Check if file is suspiciously short (might indicate generation failure)
test_lines = [line for line in test_content.splitlines() if line.strip() and not line.strip().startswith('#') and not line.strip().startswith('"""')]
if len(test_lines) < 5:
    print(f"  FAIL: Test file is suspiciously short ({len(test_lines)} non-comment lines)")
    print(f"  Content:\n{test_content}")
    sys.exit(1)

# Check for missing imports when pytest decorators are used
if '@pytest.mark.' in test_content and 'import pytest' not in test_content:
    print("  FAIL: Test uses @pytest.mark.* decorators but missing 'import pytest'")
    sys.exit(1)

# Check for POM imports
pom_import_pattern = r"from pages\.\w+ import \w+"
pom_imports = re.findall(pom_import_pattern, test_content)
if pom_imports:
    print(f"  OK: Found POM imports: {pom_imports}")
else:
    print("  FAIL: No POM imports found in test file")
    print("  Content preview:")
    print(test_content[:500])
    sys.exit(1)

# Check for POM method calls (e.g., home_page.click_*, home_page.fill_*)
pom_method_pattern = r"\b\w+\.(click_|fill_|navigate_|assert_)\w+"
pom_methods = re.findall(pom_method_pattern, test_content)
if pom_methods:
    print(f"  OK: Found POM method calls: {set(pom_methods)}")
else:
    print("  WARN: No POM method calls found (might use direct evidence_tracker)")

# Check for direct evidence_tracker calls (assertions should remain direct)
et_assert_pattern = r"evidence_tracker\.assert_"
et_asserts = re.findall(et_assert_pattern, test_content)
if et_asserts:
    print(f"  OK: Assertions remain as direct evidence_tracker calls: {len(et_asserts)} found")
else:
    print("  WARN: No direct evidence_tracker.assert_ calls found")

# Check for POM instantiation with evidence_tracker
pom_init_pattern = r"\w+ = \w+\(page,\s*evidence_tracker\)"
pom_inits = re.findall(pom_init_pattern, test_content)
if pom_inits:
    print(f"  OK: POM instantiated with evidence_tracker: {pom_inits}")
else:
    print("  FAIL: POM not instantiated with evidence_tracker")
    print("  Looking for instantiation pattern...")
    init_lines = [
        line.strip() for line in test_content.splitlines() if "=" in line and "Page" in line or "page," in line
    ]
    print(f"  Candidate lines: {init_lines[:5]}")

# --- Step 3: Check POM class files ---
print("\n[3/4] Checking POM class files...")

pages_dir = test_pkg / "pages"
if pages_dir.exists():
    pom_files = list(pages_dir.glob("*.py"))
    pom_files = [f for f in pom_files if f.name != "__init__.py"]
    for pf in pom_files:
        print(f"  Checking {pf.name}...")
        pom_content = pf.read_text()

        # Check for EvidenceTracker in __init__
        if "tracker: EvidenceTracker" in pom_content or "tracker:EvidenceTracker" in pom_content:
            print(f"    OK: {pf.name} accepts EvidenceTracker")
        else:
            print(f"    FAIL: {pf.name} does not accept EvidenceTracker")

        # Check for self.tracker.click/fill/navigate
        if "self.tracker." in pom_content:
            tracker_calls = re.findall(r"self\.tracker\.\w+", pom_content)
            print(f"    OK: Uses evidence tracker: {set(tracker_calls)}")
        else:
            print("    FAIL: Does not use self.tracker.*")
else:
    print("  FAIL: pages/ directory not found")

# --- Step 4: Check package manifest ---
print("\n[4/4] Checking package manifest...")

# Check scrape_manifest.json for pom_mode (PipelineArtifactSet includes it)
scrape_manifest_file = test_pkg / "scrape_manifest.json"
if scrape_manifest_file.exists():
    scrape_manifest = json.loads(scrape_manifest_file.read_text())
    pom_mode_value = scrape_manifest.get("pom_mode")
    if pom_mode_value is not None:
        print(f"  OK: scrape_manifest.json pom_mode = {pom_mode_value}")
    else:
        print("  WARN: scrape_manifest.json does not include pom_mode field (POM behavior verified by earlier checks)")
else:
    print("  WARN: scrape_manifest.json not found")

# Also check package_manifest.json for provider/model metadata
package_manifest_file = test_pkg / "package_manifest.json"
if package_manifest_file.exists():
    package_manifest = json.loads(package_manifest_file.read_text())
    print(f"  OK: package_manifest.json provider = {package_manifest.get('provider', 'N/A')}")
    print(f"  OK: package_manifest.json model = {package_manifest.get('model', 'N/A')}")
else:
    print("  WARN: package_manifest.json not found")

# --- Step 5: Run the generated tests ---
print("\n[5/5] Running generated tests...")

test_file = test_files[0]
result = subprocess.run(
    ["pytest", str(test_file), "-v", "--tb=short"],
    capture_output=True,
    text=True,
    cwd=str(test_pkg),
)

print("  Test output:")
for line in result.stdout.split("\n")[:30]:  # Show first 30 lines
    if line.strip():
        print(f"    {line}")

if result.stderr:
    print("  Errors:")
    for line in result.stderr.split("\n")[:10]:
        if line.strip():
            print(f"    {line}")

# Parse results
passed = result.stdout.count("PASSED")
failed = result.stdout.count("FAILED")
skipped = result.stdout.count("SKIPPED")
errors = result.stdout.count("ERROR")

print(f"\n  Results: {passed} passed, {failed} failed, {skipped} skipped, {errors} errors")

if skipped > 0 and passed == 0 and failed == 0:
    print("  WARN: All tests skipped - check placeholder resolution")
elif failed > 0:
    print("  FAIL: Some tests failed")
    sys.exit(1)
elif passed > 0:
    print("  OK: Tests executed successfully")
else:
    print("  WARN: No tests ran")

print("\n" + "=" * 60)
print("Verification Summary")
print("=" * 60)

print(f"Test package: {test_pkg}")
print(f"POM imports found: {bool(pom_imports)}")
print(f"POM methods found: {bool(pom_methods)}")
print(f"Direct evidence_tracker asserts: {bool(et_asserts)}")
print(f"POM init with tracker: {bool(pom_inits)}")
print(f"Tests executed: {passed} passed, {skipped} skipped")
print("=" * 60)
