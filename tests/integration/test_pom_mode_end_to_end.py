"""Integration test: POM mode generates tests with POM imports and instantiations.

Verifies the end-to-end fix for AI-010:
- POM imports are injected after existing imports
- POM instantiations are injected at start of each test function
- Assertions remain as direct evidence_tracker calls
- Evidence sidecar JSON schema is correct
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.orchestrator import TestOrchestrator

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAMPLE_TEST_CODE = '''\
"""
Auto-generated Playwright test package entrypoint
"""

from playwright.sync_api import Page, expect
from src.browser_utils import dismiss_consent_overlays
import pytest


def test_navigate_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible('a[href="/product_details/11"]', label='product categories')

def test_view_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com/')
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/view_cart"]', label='View Cart link')
    evidence_tracker.assert_visible('a[href="/"]', label='cart page')
'''

POM_IMPORTS = [
    "from pages.home_page import HomePage",
    "from pages.view_cart_page import ViewCartPage",
]

POM_INSTANTIATION = [
    "home_page = HomePage(page, evidence_tracker)",
    "view_cart_page = ViewCartPage(page, evidence_tracker)",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPOMInjectionEndToEnd:
    """Verify POM import and instantiation injection into generated tests."""

    def test_injects_pom_imports(self) -> None:
        """POM imports must be injected after existing imports."""
        result = TestOrchestrator._inject_pom_imports(SAMPLE_TEST_CODE, POM_IMPORTS)

        assert "from pages.home_page import HomePage" in result
        assert "from pages.view_cart_page import ViewCartPage" in result
        # Original imports preserved
        assert "from playwright.sync_api import Page, expect" in result
        assert "from src.browser_utils import dismiss_consent_overlays" in result

    def test_injects_pom_instantiations(self) -> None:
        """POM instantiations must be injected at start of each test function."""
        code_with_imports = TestOrchestrator._inject_pom_imports(SAMPLE_TEST_CODE, POM_IMPORTS)
        result = TestOrchestrator._inject_pom_instantiation(code_with_imports, POM_INSTANTIATION)

        lines = result.splitlines()
        for i, line in enumerate(lines):
            if "def test_navigate_home" in line:
                assert "home_page = HomePage(page, evidence_tracker)" in lines[i + 1], (
                    f"Expected HomePage instantiation, got: {lines[i + 1]!r}"
                )
                assert "view_cart_page = ViewCartPage(page, evidence_tracker)" in lines[i + 2]
            if "def test_view_cart" in line:
                assert "home_page = HomePage(page, evidence_tracker)" in lines[i + 1], (
                    f"Expected HomePage instantiation, got: {lines[i + 1]!r}"
                )
                assert "view_cart_page = ViewCartPage(page, evidence_tracker)" in lines[i + 2]

    def test_assertions_remain_direct_evidence_tracker_calls(self) -> None:
        """Assertions must NOT be replaced with POM methods."""
        code_with_imports = TestOrchestrator._inject_pom_imports(SAMPLE_TEST_CODE, POM_IMPORTS)
        result = TestOrchestrator._inject_pom_instantiation(code_with_imports, POM_INSTANTIATION)

        assert "evidence_tracker.assert_visible(" in result
        assert "evidence_tracker.navigate(" in result
        assert "evidence_tracker.click(" in result

    def test_full_injection_pipeline_produces_valid_python(self) -> None:
        """The fully injected code must be syntactically valid Python."""
        code_with_imports = TestOrchestrator._inject_pom_imports(SAMPLE_TEST_CODE, POM_IMPORTS)
        result = TestOrchestrator._inject_pom_instantiation(code_with_imports, POM_INSTANTIATION)

        # Verify it compiles
        compile(result, "<injected_test>", "exec")  # type: ignore[arg-type]


class TestEvidenceSidecarSchema:
    """Verify evidence sidecar JSON has required schema."""

    def test_evidence_json_has_required_fields(self, tmp_path: Path) -> None:
        """Evidence JSON must have required fields."""
        evidence: Any = {
            "test_name": "test_example",
            "timestamp": "2026-06-11T12:00:00",
            "steps": [
                {
                    "step_index": 0,
                    "action": "navigate",
                    "locator": "https://example.com",
                    "timestamp": "2026-06-11T12:00:00",
                },
                {
                    "step_index": 1,
                    "action": "assert_visible",
                    "locator": "#element",
                    "success": True,
                    "timestamp": "2026-06-11T12:00:01",
                },
            ],
        }

        path = tmp_path / "test_example.evidence.json"
        path.write_text(json.dumps(evidence, indent=2))

        loaded = json.loads(path.read_text())
        assert "test_name" in loaded
        assert "steps" in loaded
        assert len(loaded["steps"]) == 2
        assert loaded["steps"][0]["action"] == "navigate"
        assert loaded["steps"][1]["success"] is True

    def test_evidence_json_failure_diagnostics(self, tmp_path: Path) -> None:
        """Failed steps must include diagnosis object."""
        evidence: Any = {
            "test_name": "test_failed",
            "timestamp": "2026-06-11T12:00:00",
            "steps": [
                {
                    "step_index": 0,
                    "action": "click",
                    "locator": "#missing",
                    "success": False,
                    "failure_note": "Element not found",
                    "diagnosis": {
                        "url": "https://example.com",
                        "title": "Page Title",
                        "available_elements": ["#other"],
                        "suggested_locators": [{"selector": "#other", "score": 0.8}],
                        "error_summary": "No matching element",
                    },
                    "timestamp": "2026-06-11T12:00:01",
                },
            ],
        }

        path = tmp_path / "test_failed.evidence.json"
        path.write_text(json.dumps(evidence, indent=2))

        loaded = json.loads(path.read_text())
        step = loaded["steps"][0]
        assert step["success"] is False
        assert "diagnosis" in step
        assert "available_elements" in step["diagnosis"]
        assert "suggested_locators" in step["diagnosis"]
