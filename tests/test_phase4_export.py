"""Tests for Phase 4: Export UI — Streamlit + CLI export functionality."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.code_postprocessor import strip_evidence_from_test_code
from src.export_service import ExportResult, export_clean_suite
from src.pipeline_models import ExportMode

# =============================================================================
# Unit tests for strip_evidence_from_test_code()
# =============================================================================


class TestStripEvidenceClick:
    """Test click transformation."""

    def test_strip_evidence_from_test_code_click(self) -> None:
        evidence_code = 'evidence_tracker.click("#login-button", label="login button")'
        clean = strip_evidence_from_test_code(evidence_code)
        assert 'page.locator("#login-button").click()' in clean

    def test_strip_evidence_from_test_code_click_various_selectors(self) -> None:
        code = 'evidence_tracker.click("[data-testid=submit]", label="submit")'
        clean = strip_evidence_from_test_code(code)
        assert 'page.locator("[data-testid=submit]").click()' in clean


class TestStripEvidenceFill:
    """Test fill transformation."""

    def test_strip_evidence_from_test_code_fill(self) -> None:
        evidence_code = 'evidence_tracker.fill("#user-name", "standard_user", label="username input")'
        clean = strip_evidence_from_test_code(evidence_code)
        assert 'page.locator("#user-name").fill("standard_user")' in clean

    def test_strip_evidence_from_test_code_fill_single_quotes(self) -> None:
        code = "evidence_tracker.fill('#input', 'value', label='input')"
        clean = strip_evidence_from_test_code(code)
        assert "page.locator" in clean
        assert ".fill(" in clean


class TestStripEvidenceNavigate:
    """Test navigate transformation."""

    def test_strip_evidence_from_test_code_navigate(self) -> None:
        evidence_code = 'evidence_tracker.navigate("https://example.com")'
        clean = strip_evidence_from_test_code(evidence_code)
        assert 'page.goto("https://example.com")' in clean

    def test_strip_evidence_from_test_code_navigate_with_label(self) -> None:
        code = 'evidence_tracker.navigate("https://example.com", label="home page")'
        clean = strip_evidence_from_test_code(code)
        assert 'page.goto("https://example.com")' in clean
        assert "label" not in clean


class TestStripEvidenceAssert:
    """Test assert_visible transformation."""

    def test_strip_evidence_from_test_code_assert(self) -> None:
        evidence_code = 'evidence_tracker.assert_visible(".cart-badge", label="cart badge")'
        clean = strip_evidence_from_test_code(evidence_code)
        assert 'expect(page.locator(".cart-badge")).to_be_visible()' in clean


class TestStripEvidenceSelect:
    """Test select transformation."""

    def test_strip_evidence_from_test_code_select(self) -> None:
        evidence_code = 'evidence_tracker.select("#dropdown", "option1", label="dropdown")'
        clean = strip_evidence_from_test_code(evidence_code)
        assert 'page.locator("#dropdown").select_option("option1")' in clean


class TestStripEvidenceGetText:
    """Test get_text transformation."""

    def test_strip_evidence_from_test_code_get_text(self) -> None:
        evidence_code = 'evidence_tracker.get_text("#heading", label="heading")'
        clean = strip_evidence_from_test_code(evidence_code)
        assert 'page.locator("#heading").text_content()' in clean


class TestStripEvidenceSignature:
    """Test signature and import cleanup."""

    def test_strip_evidence_removes_fixture_param(self) -> None:
        code = "def test_login(page, evidence_tracker):\n    pass"
        clean = strip_evidence_from_test_code(code)
        assert "def test_login(page):" in clean
        assert "evidence_tracker" not in clean

    def test_strip_evidence_removes_fixture_param_type_hinted(self) -> None:
        code = "def test_login(page, evidence_tracker: EvidenceTracker):\n    pass"
        clean = strip_evidence_from_test_code(code)
        assert "def test_login(page):" in clean

    def test_strip_evidence_removes_import(self) -> None:
        code = "from src.evidence_tracker import EvidenceTracker\n\ndef test_x(page):\n    pass"
        clean = strip_evidence_from_test_code(code)
        assert "EvidenceTracker" not in clean

    def test_strip_evidence_ensures_playwright_import(self) -> None:
        code = 'def test_x(page):\n    expect(page.locator("#x")).to_be_visible()'
        clean = strip_evidence_from_test_code(code)
        assert "from playwright.sync_api import Page, expect" in clean

    def test_strip_evidence_removes_dismiss_consent_import(self) -> None:
        code = "from src.browser_utils import dismiss_consent_overlays\n\ndef test_x(page):\n    pass"
        clean = strip_evidence_from_test_code(code)
        assert "dismiss_consent_overlays" not in clean

    def test_strip_evidence_removes_evidence_decorator(self) -> None:
        code = "@pytest.mark.evidence\ndef test_x(page):\n    pass"
        clean = strip_evidence_from_test_code(code)
        assert "@pytest.mark.evidence" not in clean

    def test_strip_evidence_removes_dismiss_consent_calls(self) -> None:
        code = "def test_x(page):\n    dismiss_consent_overlays(page)\n    pass"
        clean = strip_evidence_from_test_code(code)
        assert "dismiss_consent_overlays" not in clean


class TestStripEvidenceCombined:
    """Test combined transformations on full test functions."""

    def test_full_test_function_transformation(self) -> None:
        """Transform a complete evidence-aware test function."""
        code = """from src.evidence_tracker import EvidenceTracker
from playwright.sync_api import Page

def test_login(page, evidence_tracker: EvidenceTracker):
    evidence_tracker.navigate("https://saucedemo.com")
    evidence_tracker.fill("#user-name", "standard_user", label="username")
    evidence_tracker.fill("#password", "secret_sauce", label="password")
    evidence_tracker.click("#login-button", label="login button")
    evidence_tracker.assert_visible(".bm-bundle-header", label="inventory header")
"""
        clean = strip_evidence_from_test_code(code)

        # EvidenceTracker import removed
        assert "EvidenceTracker" not in clean
        assert "from src.evidence_tracker" not in clean

        # Test signature cleaned
        assert "def test_login(page):" in clean

        # Transformations applied
        assert 'page.goto("https://saucedemo.com")' in clean
        assert 'page.locator("#user-name").fill("standard_user")' in clean
        assert 'page.locator("#password").fill("secret_sauce")' in clean
        assert 'page.locator("#login-button").click()' in clean
        assert 'expect(page.locator(".bm-bundle-header")).to_be_visible()' in clean

        # Playwright import preserved
        assert "from playwright.sync_api import Page, expect" in clean


# =============================================================================
# ExportMode enum tests
# =============================================================================


class TestExportModeEnum:
    """Test ExportMode enum exists and has correct values."""

    def test_export_mode_pom_exists(self) -> None:
        assert ExportMode.POM == "pom"

    def test_export_mode_flat_exists(self) -> None:
        assert ExportMode.FLAT == "flat"


# =============================================================================
# Export service integration tests
# =============================================================================


class TestExportServicePomMode:
    """Test POM mode export creates clean page objects."""

    def test_export_pom_mode_creates_clean_pages(self) -> None:
        """Export in POM mode creates clean POM classes in pages/."""
        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            source_dir.mkdir()

            # Create source with evidence-aware POM
            pages_dir = source_dir / "pages"
            pages_dir.mkdir()
            (pages_dir / "__init__.py").write_text("")
            (pages_dir / "po_login.py").write_text(
                '"""Auto-generated page object module."""\n'
                "from playwright.sync_api import Page\n"
                "from src.evidence_tracker import EvidenceTracker\n"
                "\n"
                "\n"
                "class LoginPage:\n"
                "    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:\n"
                "        self.page = page\n"
                "        self.tracker = tracker\n"
                "\n"
                "    def click_login_button(self) -> None:\n"
                '        self.tracker.click("#login-button", label="login button")\n'
            )

            # Create a test file
            (source_dir / "test_login.py").write_text(
                'from playwright.sync_api import Page\n\ndef test_login(page):\n    page.goto("https://example.com")\n'
            )

            result = export_clean_suite(
                source_package_dir=source_dir,
                export_mode=ExportMode.POM,
                story_slug="test_login",
            )

            export_dir = Path(result.export_dir)
            exported_pages = export_dir / "pages"
            assert exported_pages.exists()

            po_file = exported_pages / "po_login.py"
            content = po_file.read_text()
            # Evidence stripped from POM
            assert "EvidenceTracker" not in content
            assert "self.tracker" not in content
            assert "self.page.locator" in content
            assert "def __init__(self, page: Page) -> None:" in content


class TestExportServiceFlatMode:
    """Test Flat mode export skips pages directory."""

    def test_export_flat_mode_skips_pages(self) -> None:
        """Flat export does not create pages/ directory."""
        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            source_dir.mkdir()

            # Create a test file with evidence tracker calls
            (source_dir / "test_login.py").write_text(
                "from playwright.sync_api import Page\n"
                "\n"
                "def test_login(page, evidence_tracker):\n"
                '    evidence_tracker.navigate("https://example.com")\n'
                '    evidence_tracker.click("#button", label="button")\n'
            )

            result = export_clean_suite(
                source_package_dir=source_dir,
                export_mode=ExportMode.FLAT,
                output_base_dir=str(Path(tmpdir) / "output"),
                story_slug="test_login",
            )

            export_dir = Path(result.export_dir)
            exported_pages = export_dir / "pages"
            assert not exported_pages.exists()

            # Test file should have evidence stripped
            test_file = export_dir / "test_login.py"
            content = test_file.read_text()
            assert "evidence_tracker" not in content
            assert "page.goto" in content
            assert "page.locator" in content


class TestExportConftest:
    """Test exported conftest is clean."""

    def test_export_conftest_is_clean(self) -> None:
        """Exported conftest has no evidence_tracker fixture."""
        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            source_dir.mkdir()
            (source_dir / "test_login.py").write_text("def test_x(page):\n    pass\n")

            result = export_clean_suite(
                source_package_dir=source_dir,
                export_mode=ExportMode.FLAT,
                story_slug="test",
            )

            conftest = Path(result.conftest)
            content = conftest.read_text()
            assert "evidence_tracker" not in content
            assert "EvidenceTracker" not in content
            assert "pytest-playwright" in content.lower() or "pytest" in content.lower()


class TestExportReadme:
    """Test README.md generation."""

    def test_export_readme_generated(self) -> None:
        """README.md contains export metadata."""
        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir) / "source"
            source_dir.mkdir()
            (source_dir / "test_login.py").write_text("def test_x(page):\n    pass\n")

            # Create package_manifest.json
            import json

            manifest = {
                "source_story": "Login as valid user",
                "starting_url": "https://saucedemo.com",
                "provider": "ollama",
                "model": "gemma3:12b",
                "created_at": "2026-06-06T12:00:00",
            }
            (source_dir / "package_manifest.json").write_text(json.dumps(manifest))

            result = export_clean_suite(
                source_package_dir=source_dir,
                export_mode=ExportMode.FLAT,
                story_slug="test_login",
            )

            readme = Path(result.readme)
            assert readme.exists()
            content = readme.read_text()

            assert "Exported Test Suite" in content
            assert "Flat" in content
            assert "Login as valid user" in content
            assert "https://saucedemo.com" in content
            assert "EvidenceTracker dependency has been stripped" in content


class TestExportResult:
    """Test ExportResult class."""

    def test_export_result_summary(self) -> None:
        result = ExportResult(
            export_dir="/path/to/export",
            test_files=["test_a.py", "test_b.py"],
            page_objects=["po_login.py"],
            conftest="conftest.py",
            readme="README.md",
        )
        summary = result.summary()
        assert "Exported to: /path/to/export" in summary
        assert "Tests: 2" in summary
        assert "Page Objects: 1" in summary


class TestExportServiceErrors:
    """Test error handling in export service."""

    def test_export_raises_for_missing_source(self) -> None:
        """Export raises FileNotFoundError for non-existent source."""
        with pytest.raises(FileNotFoundError, match="does not exist"):
            export_clean_suite(
                source_package_dir="/nonexistent/path",
                export_mode=ExportMode.FLAT,
            )


# =============================================================================
# CLI export tests (stubs — full CLI tests added after CLI wiring)
# =============================================================================


class TestCliExportMenuOption:
    """Test CLI export menu option exists."""

    def test_cli_export_menu_option_exists(self) -> None:
        """CLI should have an export option."""
        # This is a placeholder — the actual CLI wiring will be done
        # when we integrate the export into cli/main.py
        pass

    def test_cli_export_flat_mode(self) -> None:
        """CLI export in flat mode produces correct output."""
        pass

    def test_cli_export_pom_mode(self) -> None:
        """CLI export in POM mode produces correct output."""
        pass
