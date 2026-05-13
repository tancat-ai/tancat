"""Pipeline execution helpers for the Streamlit UI — business logic only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.code_validator import validate_python_syntax
from src.journey_scraper import CredentialProfile, JourneyStep
from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.pipeline_report_service import PipelineReportBundle, PipelineReportService
from src.pipeline_run_service import PipelineRunService
from src.pipeline_writer import PipelineArtifactWriter
from src.pytest_output_parser import RunResult
from src.spec_analyzer import SpecAnalyzer, TestCondition
from src.test_generator import TestGenerator
from src.test_plan import TestPlan, build_story_ref

# ---------------------------------------------------------------------------
# Provider defaults
# ---------------------------------------------------------------------------


def _get_provider_defaults(provider: str) -> tuple[str, str]:
    """Return (base_url, model) defaults for the given provider."""
    if provider == "lm-studio":
        return "http://localhost:1234", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
    return "http://localhost:11434", "qwen3.5:35b"


# ---------------------------------------------------------------------------
# Requirements parsing
# ---------------------------------------------------------------------------


def parse_requirements_text(raw_text: str) -> tuple[str, str]:
    """Return (user_story, criteria) from raw requirements text.

    If the text cannot be parsed as a structured specification, the
    cleaned text is returned for both fields.
    """
    from src.user_story_parser import FeatureParser

    parser = FeatureParser()
    result = parser.parse(raw_text)
    if result.success and result.specification is not None:
        specification = result.specification
        requirement_model = parser.build_requirement_model(specification)
        return specification.user_story.strip(), requirement_model.to_numbered_text().strip()

    cleaned = raw_text.strip()
    return cleaned, cleaned


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def parse_target_urls(base_url: str, urls_input: str) -> list[str]:
    """Deduplicate and order target URLs from UI inputs."""
    urls = [url.strip() for url in urls_input.splitlines() if url.strip()]
    if base_url.strip() and base_url.strip() not in urls:
        urls.insert(0, base_url.strip())
    return urls


# ---------------------------------------------------------------------------
# Test plan building
# ---------------------------------------------------------------------------


def build_test_plan(
    *,
    user_story: str,
    criteria: str,
    provider: str,
    provider_base_url: str,
    model_name: str,
) -> TestPlan:
    """Analyze requirements and return a living test plan for review."""
    client = LLMClient(provider=provider, model=model_name, base_url=provider_base_url)
    analyzer = SpecAnalyzer(llm_client=client)
    spec_text = f"User Story:\n{user_story}\n\nAcceptance Criteria:\n{criteria}"
    conditions = analyzer.analyze(spec_text)
    return TestPlan.from_conditions(
        story_ref=build_story_ref(user_story),
        sprint="Backlog",
        conditions=conditions,
    )


def plan_rows_from_plan(plan: TestPlan) -> list[dict[str, object]]:
    """Return editable table rows for the current plan."""
    return [
        {
            "reviewed": condition.id in plan.reviewed_ids,
            "id": condition.id,
            "type": condition.type,
            "intent": condition.intent,
            "text": condition.text,
            "expected": condition.expected,
            "source": condition.source,
            "flagged": condition.flagged,
            "src": condition.src,
        }
        for condition in plan.conditions
    ]


# ---------------------------------------------------------------------------
# Pipeline execution (async)
# ---------------------------------------------------------------------------


class PipelineSessionState:
    """Thin wrapper around Streamlit session state for testability."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self._state = state if state is not None else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._state[key] = value


async def run_pipeline(
    *,
    user_story: str,
    criteria: str,
    provider: str,
    provider_base_url: str,
    model_name: str,
    target_urls: list[str],
    consent_mode: str,
    reviewed_conditions: list[TestCondition] | None = None,
    session: PipelineSessionState | None = None,
    credential_profile: CredentialProfile | None = None,
    journey_steps: list[JourneyStep] | None = None,
) -> None:
    """Execute the full skeleton-first pipeline.

    Side-effects:
    - Updates session state with pipeline artifacts
    - Writes test file and manifest to disk
    """
    if session is None:
        session = PipelineSessionState()

    client = LLMClient(provider=provider, model=model_name, base_url=provider_base_url)

    conditions = list(reviewed_conditions or [])
    if not conditions:
        analyzer = SpecAnalyzer(llm_client=client)
        spec_text = f"User Story:\n{user_story}\n\nAcceptance Criteria:\n{criteria}"
        conditions = analyzer.analyze(spec_text)
    session.set("pipeline_conditions", conditions)

    if conditions:
        conditions_text = "\n".join(
            f"{i}. [{c.id}] {c.text} -> Expected: {c.expected}" for i, c in enumerate(conditions, 1)
        )
    else:
        conditions_text = criteria

    generator = TestGenerator(client=client, model_name=model_name)
    orchestrator = TestOrchestrator(
        generator,
        credential_profile=credential_profile,
        journey_steps=journey_steps,
    )

    final_code = await orchestrator.run_pipeline(
        user_story=user_story,
        conditions=conditions_text,
        target_urls=target_urls,
        consent_mode=consent_mode,
        reviewed_conditions=conditions,
    )
    last_result = orchestrator.last_result

    # Store results in session state
    session.set("pipeline_results", final_code)
    session.set("pipeline_skeleton", last_result.skeleton_code if last_result else "")
    session.set("pipeline_urls", last_result.pages_to_scrape if last_result else target_urls)
    session.set("pipeline_scraped_pages", last_result.scraped_pages if last_result else {})
    session.set("pipeline_unresolved", last_result.unresolved_placeholders if last_result else [])
    session.set("pipeline_criteria", conditions_text)

    # Clear previous run results
    for key in (
        "pipeline_run_result",
        "pipeline_run_output",
        "pipeline_run_command",
        "pipeline_run_return_code",
        "pipeline_local_report",
        "pipeline_jira_report",
        "pipeline_html_report",
        "pipeline_local_report_path",
        "pipeline_jira_report_path",
        "pipeline_html_report_path",
    ):
        session.set(key, "" if key.endswith(("_output", "_report")) else None)

    # Validate generated code
    syntax_error = validate_python_syntax(final_code)
    if syntax_error:
        session.set("pipeline_saved_path", "")
        session.set("pipeline_manifest_path", "")
        raise ValueError(f"Generated code failed syntax validation: {syntax_error}")

    # Write artifacts
    primary_url = target_urls[0] if target_urls else ""
    if last_result is not None:
        artifact_writer = PipelineArtifactWriter()
        artifact_set = artifact_writer.write_run_artifacts(
            run_result=last_result,
            story_text=user_story,
            base_url=primary_url,
        )
        session.set("pipeline_saved_path", artifact_set.test_file_path)
        session.set("pipeline_manifest_path", artifact_set.manifest_path)


# ---------------------------------------------------------------------------
# Test execution
# ---------------------------------------------------------------------------


def execute_saved_test(saved_path: str) -> Any:
    """Run a saved test file and return the execution result."""
    return PipelineRunService().run_saved_test(saved_path)


def execute_failed_only(
    saved_path: str,
    previous_run: RunResult,
) -> Any:
    """Re-run only the failed tests from a previous run."""
    return PipelineRunService().run_saved_test(
        saved_path,
        rerun_failed_only=True,
        previous_run=previous_run,
    )


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def build_report_bundle(
    *,
    criteria_text: str,
    generated_code: str,
    run_result: RunResult,
    saved_path: str,
) -> PipelineReportBundle:
    """Build report artifacts for the current pipeline run."""
    package_dir = str(Path(saved_path).resolve().parent)
    return PipelineReportService().build_reports(
        criteria_text=criteria_text,
        generated_code=generated_code,
        run_result=run_result,
        package_dir=package_dir,
    )


def store_report_bundle(report_bundle: PipelineReportBundle, session: PipelineSessionState) -> None:
    """Persist report content and file paths in session state."""
    session.set("pipeline_local_report", report_bundle.local_report)
    session.set("pipeline_jira_report", report_bundle.jira_report)
    session.set("pipeline_html_report", report_bundle.html_report)
    session.set("pipeline_local_report_path", report_bundle.local_report_path)
    session.set("pipeline_jira_report_path", report_bundle.jira_report_path)
    session.set("pipeline_html_report_path", report_bundle.html_report_path)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def safe_read_text(path: str) -> str:
    """Read a text file if it exists, otherwise return an empty string."""
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Evidence sidecar discovery
# ---------------------------------------------------------------------------


def find_evidence_sidecars(base_dir: Path) -> list[Path]:
    """Find all evidence sidecars under the generated_tests directory."""
    sidecars: list[Path] = []
    if not base_dir.exists():
        return sidecars
    for test_pkg in sorted(base_dir.iterdir()):
        if test_pkg.is_dir():
            pkg_evidence = test_pkg / "evidence"
            sidecars.extend(pkg_evidence.glob("*.evidence.json"))
    sidecars.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return sidecars


def find_all_evidence_dirs(base_dir: Path) -> list[Path]:
    """Return all evidence directories under generated_tests/."""
    dirs: list[Path] = []
    if not base_dir.exists():
        return dirs
    for test_pkg in sorted(base_dir.iterdir()):
        if test_pkg.is_dir():
            pkg_evidence = test_pkg / "evidence"
            if pkg_evidence.exists():
                dirs.append(pkg_evidence)
    return dirs


def find_sidecar_for_test(base_dir: Path, test_name: str) -> Path | None:
    """Find a sidecar by test name across all test package evidence directories."""
    if not base_dir.exists():
        return None
    for test_pkg in sorted(base_dir.iterdir()):
        if test_pkg.is_dir():
            candidate = test_pkg / "evidence" / f"{test_name}.evidence.json"
            if candidate.exists():
                return candidate
    return None
