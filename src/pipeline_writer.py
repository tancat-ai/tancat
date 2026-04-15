"""Write intelligent-pipeline outputs as a structured artifact package."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.code_validator import validate_python_syntax
from src.file_utils import slugify
from src.pipeline_models import ManifestRecord, PipelineArtifactSet

if TYPE_CHECKING:
    from src.orchestrator import PipelineRunResult


class PipelineArtifactWriter:
    """Persist final code, page objects, and a manifest as one package."""

    def __init__(self, output_dir: str = "generated_tests") -> None:
        self.output_dir = Path(output_dir)

    def write_run_artifacts(
        self,
        *,
        run_result: PipelineRunResult,
        story_text: str,
        base_url: str = "",
    ) -> PipelineArtifactSet:
        """Write one structured artifact package for a pipeline run."""
        validation_error = validate_python_syntax(run_result.final_code)
        if validation_error:
            raise ValueError(f"Generated code failed syntax validation: {validation_error}")

        package_dir = self._build_package_dir(story_text)
        pages_dir = package_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / "__init__.py").write_text("", encoding="utf-8")

        page_object_paths: list[str] = []
        for page_object in run_result.generated_page_objects:
            page_object_path = pages_dir / Path(page_object.file_path).name
            page_object_path.write_text(page_object.module_source, encoding="utf-8")
            page_object_paths.append(str(page_object_path.absolute()))

        test_file_path = package_dir / f"test_{slugify(story_text[:50])}.py"
        package_test_code = self._build_packaged_test_code(
            run_result.final_code,
            generated_page_objects=run_result.generated_page_objects,
        )
        test_file_path.write_text(self._build_test_file_content(package_test_code, base_url), encoding="utf-8")

        coverage_summary_path = package_dir / "coverage_summary.json"
        coverage_summary_path.write_text(
            json.dumps(self._build_coverage_summary_dict(run_result), indent=2),
            encoding="utf-8",
        )

        records = self._build_manifest_records(run_result)
        manifest_path = package_dir / "scrape_manifest.json"
        manifest_path.write_text(
            json.dumps(
                self._build_manifest_dict(
                    run_result=run_result,
                    base_url=base_url,
                    page_object_paths=page_object_paths,
                    test_file_path=str(test_file_path.absolute()),
                    coverage_summary_path=str(coverage_summary_path.absolute()),
                    records=records,
                ),
                indent=2,
            ),
            encoding="utf-8",
        )

        return PipelineArtifactSet(
            run_id=package_dir.name,
            test_file_path=str(test_file_path.absolute()),
            page_object_paths=page_object_paths,
            manifest_path=str(manifest_path.absolute()),
            pages=run_result.scraped_page_records,
            records=records,
        )

    def _build_package_dir(self, story_text: str) -> Path:
        """Return the directory path for one generated package."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        story_slug = slugify(story_text[:50]) if story_text else "test"
        return self.output_dir / f"test_{timestamp}_{story_slug}"

    @staticmethod
    def _build_test_file_content(test_code: str, base_url: str) -> str:
        """Return the final saved test file contents with header."""
        return f'''"""
Auto-generated Playwright test package entrypoint
Generated: {datetime.now().isoformat()}
Base URL:  {base_url or "Not specified"}
"""

{test_code}
'''

    def _build_packaged_test_code(
        self,
        test_code: str,
        *,
        generated_page_objects: list[Any],
    ) -> str:
        """Return test code rewritten to import generated page objects from `pages/`."""
        rewritten = test_code
        import_lines: list[str] = []

        for page_object in generated_page_objects:
            class_name = str(page_object.class_name)
            module_name = str(page_object.module_name)
            if f"class {class_name}:" in rewritten:
                rewritten = self._remove_class_definition(rewritten, class_name)
            if class_name in rewritten:
                import_lines.append(f"from pages.{module_name} import {class_name}")

        if not import_lines:
            return rewritten

        unique_imports = "\n".join(dict.fromkeys(import_lines))
        if unique_imports in rewritten:
            return rewritten

        lines = rewritten.splitlines()
        insert_at = 0
        while insert_at < len(lines) and (
            lines[insert_at].startswith("from __future__ import")
            or lines[insert_at].startswith("import ")
            or lines[insert_at].startswith("from ")
            or not lines[insert_at].strip()
        ):
            insert_at += 1
        lines.insert(insert_at, unique_imports)
        return "\n".join(lines)

    @staticmethod
    def _remove_class_definition(code: str, class_name: str) -> str:
        """Remove one top-level class block from generated code."""
        pattern = re.compile(rf"(?ms)^class\s+{re.escape(class_name)}\b.*?(?=^\S|\Z)")
        return re.sub(pattern, "", code).strip() + "\n"

    @staticmethod
    def _build_manifest_records(run_result: PipelineRunResult) -> list[ManifestRecord]:
        """Return manifest records built from unresolved placeholders."""
        records: list[ManifestRecord] = []
        for unresolved in run_result.unresolved_placeholders:
            records.append(
                ManifestRecord(
                    kind="unresolved_placeholder",
                    message=unresolved,
                )
            )
        return records

    def _build_manifest_dict(
        self,
        *,
        run_result: PipelineRunResult,
        base_url: str,
        page_object_paths: list[str],
        test_file_path: str,
        coverage_summary_path: str,
        records: list[ManifestRecord],
    ) -> dict[str, Any]:
        """Return the JSON-serializable manifest structure."""
        return {
            "generated_at": datetime.now().isoformat(),
            "base_url": base_url,
            "test_file_path": test_file_path,
            "coverage_summary_path": coverage_summary_path,
            "run_command": f'pytest "{test_file_path}" -v',
            "pages_scraped": [page.to_dict() for page in run_result.scraped_page_records],
            "page_requirements": [page_requirement.to_dict() for page_requirement in run_result.page_requirements],
            "journeys": [journey.to_dict() for journey in run_result.journeys],
            "page_objects": [
                {
                    "class_name": page_object.class_name,
                    "module_name": page_object.module_name,
                    "file_path": page_path,
                    "url": page_object.url,
                    "methods": page_object.methods,
                }
                for page_object, page_path in zip(run_result.generated_page_objects, page_object_paths, strict=False)
            ],
            "records": [record.to_dict() for record in records],
        }

    @staticmethod
    def _build_coverage_summary_dict(run_result: PipelineRunResult) -> dict[str, Any]:
        """Return a lightweight package coverage summary."""
        return {
            "generated_at": datetime.now().isoformat(),
            "journey_count": len(run_result.journeys),
            "page_count": len(run_result.scraped_page_records),
            "page_object_count": len(run_result.generated_page_objects),
            "unresolved_placeholder_count": len(run_result.unresolved_placeholders),
            "unresolved_placeholders": list(run_result.unresolved_placeholders),
            "tests": [journey.test_name for journey in run_result.journeys],
        }
