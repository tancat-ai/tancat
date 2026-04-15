"""Mocked end-to-end checks for packaged pipeline outputs."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from src.orchestrator import PipelineRunResult
from src.pipeline_models import GeneratedPageObject, PageRequirement, ScrapedPage, TestJourney, TestStep
from src.pipeline_run_service import PipelineRunService
from src.pipeline_writer import PipelineArtifactWriter


def test_packaged_pipeline_artifacts_can_be_handed_to_run_service(tmp_path: Path) -> None:
    writer = PipelineArtifactWriter(output_dir=str(tmp_path))
    run_result = PipelineRunResult(
        skeleton_code="""
from playwright.sync_api import Page

class HomePage:
    def __init__(self, page: Page) -> None:
        self.page = page

def test_checkout(page: Page) -> None:
    home_page = HomePage(page)
    home_page.goto()
""".strip(),
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
        page_requirements=[PageRequirement(url="https://example.com/", description="home")],
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
                module_source="""
from playwright.sync_api import Page

class HomePage:
    URL = "https://example.com/"

    def __init__(self, page: Page) -> None:
        self.page = page

    def goto(self) -> None:
        self.page.goto(self.URL)
""".strip(),
            )
        ],
    )

    artifact_set = writer.write_run_artifacts(run_result=run_result, story_text="Checkout flow")
    saved_test = Path(artifact_set.test_file_path).read_text(encoding="utf-8")

    assert "from pages.home_page import HomePage" in saved_test
    assert "class HomePage:" not in saved_test

    stdout = f"""
{artifact_set.test_file_path}::test_checkout PASSED [100%]
============================== 1 passed in 1.20s ==============================
"""
    with patch("src.pipeline_run_service.subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
        execution = PipelineRunService().run_saved_test(artifact_set.test_file_path, cwd=str(tmp_path))

    assert execution.command[:3] == ["python", "-m", "pytest"] or execution.command[1:3] == ["-m", "pytest"]
    assert artifact_set.test_file_path in execution.command
    assert execution.run_result.passed == 1
