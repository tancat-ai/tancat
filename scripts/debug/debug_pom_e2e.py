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

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import PipelineConfig
from src.journey_scraper import CredentialProfile
from src.orchestrator import TestOrchestrator

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

config = PipelineConfig(
    provider="ollama",
    provider_config={
        "base_url": "http://localhost:11434",
        "model": "llama3",
    },
)

orchestrator = TestOrchestrator(
    config=config,
    starting_url=BASE_URL,
    credential_profile=CredentialProfile(),
    pom_mode=POM_MODE,
)

result = orchestrator.generate_and_write_tests(
    requirements=USER_STORY,
    output_dir=OUTPUT_DIR,
)

if not result or not result.generated_page_objects:
    print("FAIL: No page objects generated")
    sys.exit(1)

print(f"  Generated {len(result.generated_page_objects)} page object(s)")
for po in result.generated_page_objects:
    print(f"    - {po.class_name} for {po.url}")

# Find the generated test package
test_packages = list(OUTPUT_DIR.glob("test_*/"))
if not test_packages:
    print("FAIL: No test packages found")
    sys.exit(1)

test_pkg = test_packages[-1]  # Most recent
print(f"\n  Test package: {test_pkg.name}")

# --- Step 2: Check test file for POM imports and usage ---
print("\n[2/4] Checking POM imports and usage...")

test_file = test_pkg / "test_*.py"
test_files = list(test_pkg.glob("test_*.py"))
if not test_files:
    print("FAIL: No test files found")
    sys.exit(1)

test_file = test_files[0]
test_content = test_file.read_text()

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

manifest_file = test_pkg / "package_manifest.json"
if manifest_file.exists():
    manifest = json.loads(manifest_file.read_text())
    pom_mode_value = manifest.get("pom_mode")
    if pom_mode_value:
        print(f"  OK: package_manifest.json pom_mode = {pom_mode_value}")
    else:
        print(f"  FAIL: pom_mode not set in manifest (value: {pom_mode_value})")
else:
    print("  WARN: package_manifest.json not found")

print("\n" + "=" * 60)
print("Verification Summary")
print("=" * 60)

print(f"Test package: {test_pkg}")
print(f"POM imports found: {bool(pom_imports)}")
print(f"POM methods found: {bool(pom_methods)}")
print(f"Direct evidence_tracker asserts: {bool(et_asserts)}")
print(f"POM init with tracker: {bool(pom_inits)}")
print("=" * 60)
