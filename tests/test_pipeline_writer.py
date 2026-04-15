"""Tests for structured intelligent-pipeline artifact writing."""

from __future__ import annotations

import json
from pathlib import Path

from src.orchestrator import PipelineRunResult
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney, TestStep
from src.pipeline_writer import PipelineArtifactWriter


def test_write_run_artifacts_creates_package_with_manifest_and_pages(tmp_path: Path) -> None:
    writer = PipelineArtifactWriter(output_dir=str(tmp_path))
    run_result = PipelineRunResult(
        skeleton_code="def test_checkout(page):\n    pass",
        final_code="from playwright.sync_api import Page\n\ndef test_checkout(page: Page):\n    pass",
        pages_to_scrape=["https://example.com/", "https://example.com/cart"],
        scraped_pages={"https://example.com/": [], "https://example.com/cart": []},
        page_requirements=[
            PageRequirement(url="https://example.com/", description="home"),
            PageRequirement(url="https://example.com/cart", description="cart"),
        ],
        journeys=[
            TestJourney(
                test_name="test_checkout",
                start_line=1,
                end_line=2,
                page_object_names=["HomePage", "CartPage"],
                steps=[TestStep(line_number=2, raw_line="pass")],
            )
        ],
        scraped_page_records=[
            ScrapedPage(url="https://example.com/", element_count=2, elements=[]),
            ScrapedPage(url="https://example.com/cart", element_count=1, elements=[]),
        ],
        generated_page_objects=[
            GeneratedPageObject(
                class_name="HomePage",
                module_name="home_page",
                file_path="generated_tests/pages/home_page.py",
                url="https://example.com/",
                methods=["goto"],
                module_source='from playwright.sync_api import Page\n\nclass HomePage:\n    URL = "https://example.com/"\n',
            ),
            GeneratedPageObject(
                class_name="CartPage",
                module_name="cart_page",
                file_path="generated_tests/pages/cart_page.py",
                url="https://example.com/cart",
                methods=["goto", "proceed_to_checkout"],
                module_source='from playwright.sync_api import Page\n\nclass CartPage:\n    URL = "https://example.com/cart"\n',
            ),
        ],
        unresolved_placeholders=["pytest.skip(\"Locator for 'checkout button' not found on scraped pages.\")"],
    )

    artifact_set = writer.write_run_artifacts(
        run_result=run_result,
        story_text="Checkout flow",
        base_url="https://example.com/",
    )

    package_dir = Path(artifact_set.test_file_path).parent
    assert package_dir.exists()
    assert Path(artifact_set.test_file_path).exists()
    assert Path(artifact_set.manifest_path).exists()
    assert (package_dir / "coverage_summary.json").exists()
    assert (package_dir / "pages" / "__init__.py").exists()
    assert len(artifact_set.page_object_paths) == 2
    assert all(Path(path).exists() for path in artifact_set.page_object_paths)

    saved_test = Path(artifact_set.test_file_path).read_text(encoding="utf-8")
    assert "from pages.home_page import HomePage" not in saved_test

    manifest = json.loads(Path(artifact_set.manifest_path).read_text(encoding="utf-8"))
    assert manifest["base_url"] == "https://example.com/"
    assert manifest["run_command"].endswith('" -v')
    assert manifest["coverage_summary_path"].endswith("coverage_summary.json")
    assert manifest["page_requirements"][0]["description"] == "home"
    assert manifest["journeys"][0]["test_name"] == "test_checkout"
    assert manifest["page_objects"][1]["class_name"] == "CartPage"
    assert manifest["records"][0]["kind"] == "unresolved_placeholder"

    coverage_summary = json.loads((package_dir / "coverage_summary.json").read_text(encoding="utf-8"))
    assert coverage_summary["journey_count"] == 1
    assert coverage_summary["page_object_count"] == 2
    assert coverage_summary["unresolved_placeholder_count"] == 1


def test_write_run_artifacts_rejects_invalid_python(tmp_path: Path) -> None:
    writer = PipelineArtifactWriter(output_dir=str(tmp_path))
    run_result = PipelineRunResult(
        skeleton_code="",
        final_code="def broken(",
        pages_to_scrape=[],
        scraped_pages={},
    )

    try:
        writer.write_run_artifacts(run_result=run_result, story_text="Broken flow")
        raise AssertionError("Expected invalid code to raise ValueError")
    except ValueError as exc:
        assert "syntax validation" in str(exc)


def test_write_run_artifacts_rewrites_inline_page_objects_to_package_imports(tmp_path: Path) -> None:
    writer = PipelineArtifactWriter(output_dir=str(tmp_path))
    run_result = PipelineRunResult(
        skeleton_code="",
        final_code="""
from playwright.sync_api import Page

class HomePage:
    def __init__(self, page: Page) -> None:
        self.page = page

def test_checkout(page: Page) -> None:
    home_page = HomePage(page)
    home_page.goto()
""".strip(),
        pages_to_scrape=["https://example.com/"],
        scraped_pages={"https://example.com/": []},
        journeys=[
            TestJourney(
                test_name="test_checkout",
                start_line=1,
                end_line=8,
                page_object_names=["HomePage"],
                steps=[TestStep(line_number=7, raw_line="home_page.goto()")],
            )
        ],
        scraped_page_records=[ScrapedPage(url="https://example.com/", element_count=1, elements=[])],
        generated_page_objects=[
            GeneratedPageObject(
                class_name="HomePage",
                module_name="home_page",
                file_path="generated_tests/pages/home_page.py",
                url="https://example.com/",
                methods=["goto"],
                module_source='from playwright.sync_api import Page\n\nclass HomePage:\n    URL = "https://example.com/"\n',
            )
        ],
    )

    artifact_set = writer.write_run_artifacts(run_result=run_result, story_text="Checkout flow")
    saved_test = Path(artifact_set.test_file_path).read_text(encoding="utf-8")

    assert "from pages.home_page import HomePage" in saved_test
    assert "class HomePage:" not in saved_test
