"""Streamlit UI for the intelligent scraping pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import streamlit as st

from src.code_validator import validate_python_syntax
from src.coverage_utils import build_coverage_analysis, build_coverage_display_rows
from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.pipeline_report_service import PipelineReportBundle, PipelineReportService
from src.pipeline_run_service import PipelineRunService
from src.pipeline_writer import PipelineArtifactWriter
from src.pytest_output_parser import RunResult
from src.spec_analyzer import SpecAnalyzer
from src.test_generator import TestGenerator
from src.user_story_parser import FeatureParser

st.set_page_config(page_title="AI Playwright Generator", page_icon=":test_tube:", layout="wide")


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "pipeline_results": None,
        "pipeline_skeleton": "",
        "pipeline_saved_path": "",
        "pipeline_manifest_path": "",
        "pipeline_error": "",
        "pipeline_unresolved": [],
        "pipeline_scraped_pages": {},
        "pipeline_urls": [],
        "pipeline_criteria": "",
        "pipeline_conditions": [],
        "pipeline_run_result": None,
        "pipeline_run_output": "",
        "pipeline_run_command": "",
        "pipeline_run_return_code": None,
        "pipeline_local_report": "",
        "pipeline_jira_report": "",
        "pipeline_html_report": "",
        "pipeline_local_report_path": "",
        "pipeline_jira_report_path": "",
        "pipeline_html_report_path": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _build_report_bundle(
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


def _store_report_bundle(report_bundle: PipelineReportBundle) -> None:
    """Persist report content and file paths in Streamlit session state."""
    st.session_state.pipeline_local_report = report_bundle.local_report
    st.session_state.pipeline_jira_report = report_bundle.jira_report
    st.session_state.pipeline_html_report = report_bundle.html_report
    st.session_state.pipeline_local_report_path = report_bundle.local_report_path
    st.session_state.pipeline_jira_report_path = report_bundle.jira_report_path
    st.session_state.pipeline_html_report_path = report_bundle.html_report_path


def _safe_read_text(path: str) -> str:
    """Read a text file if it exists, otherwise return an empty string."""
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def _get_provider_defaults(provider: str) -> tuple[str, str]:
    if provider == "lm-studio":
        return "http://localhost:1234", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
    return "http://localhost:11434", "qwen3.5:35b"


def _parse_target_urls(base_url: str, urls_input: str) -> list[str]:
    urls = [url.strip() for url in urls_input.splitlines() if url.strip()]
    if base_url.strip() and base_url.strip() not in urls:
        urls.insert(0, base_url.strip())
    return urls


def _parse_requirements_text(raw_text: str) -> tuple[str, str]:
    parser = FeatureParser()
    result = parser.parse(raw_text)
    if result.success and result.specification is not None:
        specification = result.specification
        requirement_model = parser.build_requirement_model(specification)
        return specification.user_story.strip(), requirement_model.to_numbered_text().strip()

    cleaned = raw_text.strip()
    return cleaned, cleaned


async def _run_pipeline(
    user_story: str,
    criteria: str,
    provider: str,
    provider_base_url: str,
    model_name: str,
    target_urls: list[str],
    consent_mode: str,
) -> None:
    client = LLMClient(provider=provider, model=model_name, base_url=provider_base_url)

    analyzer = SpecAnalyzer(llm_client=client)
    spec_text = f"User Story:\n{user_story}\n\nAcceptance Criteria:\n{criteria}"
    conditions = analyzer.analyze(spec_text)
    st.session_state.pipeline_conditions = conditions

    if conditions:
        conditions_text = "\n".join(
            f"{i}. [{c.id}] {c.text} -> Expected: {c.expected}" for i, c in enumerate(conditions, 1)
        )
    else:
        conditions_text = criteria

    generator = TestGenerator(client=client, model_name=model_name)
    orchestrator = TestOrchestrator(generator)

    final_code = await orchestrator.run_pipeline(
        user_story=user_story,
        conditions=conditions_text,
        target_urls=target_urls,
        consent_mode=consent_mode,
    )
    last_result = orchestrator.last_result

    st.session_state.pipeline_results = final_code
    st.session_state.pipeline_skeleton = last_result.skeleton_code if last_result else ""
    st.session_state.pipeline_urls = last_result.pages_to_scrape if last_result else target_urls
    st.session_state.pipeline_scraped_pages = last_result.scraped_pages if last_result else {}
    st.session_state.pipeline_unresolved = last_result.unresolved_placeholders if last_result else []
    st.session_state.pipeline_criteria = conditions_text
    st.session_state.pipeline_run_result = None
    st.session_state.pipeline_run_output = ""
    st.session_state.pipeline_run_command = ""
    st.session_state.pipeline_run_return_code = None
    st.session_state.pipeline_local_report = ""
    st.session_state.pipeline_jira_report = ""
    st.session_state.pipeline_html_report = ""
    st.session_state.pipeline_local_report_path = ""
    st.session_state.pipeline_jira_report_path = ""
    st.session_state.pipeline_html_report_path = ""

    syntax_error = validate_python_syntax(final_code)
    if syntax_error:
        st.session_state.pipeline_saved_path = ""
        st.session_state.pipeline_manifest_path = ""
        raise ValueError(f"Generated code failed syntax validation: {syntax_error}")

    primary_url = target_urls[0] if target_urls else ""
    if last_result is not None:
        artifact_writer = PipelineArtifactWriter()
        artifact_set = artifact_writer.write_run_artifacts(
            run_result=last_result,
            story_text=user_story,
            base_url=primary_url,
        )
        st.session_state.pipeline_saved_path = artifact_set.test_file_path
        st.session_state.pipeline_manifest_path = artifact_set.manifest_path


_init_session_state()

st.sidebar.title("Configuration")
provider = st.sidebar.selectbox("LLM Provider", ["ollama", "lm-studio"])
default_provider_url, default_model = _get_provider_defaults(provider)
provider_base_url = st.sidebar.text_input("Provider Base URL", value=default_provider_url)

# Attempt to fetch models from the provider
available_models: list[str] = []
try:
    # We create a temporary client to check available models
    temp_client = LLMClient(provider=provider, base_url=provider_base_url)
    available_models = temp_client.list_models(timeout=2)
except Exception:
    # If fetching fails (e.g. server offline), we just proceed with an empty list
    pass

if available_models:
    model_option = st.sidebar.selectbox("Select Model", ["-- Enter manually --"] + available_models)
    if model_option == "-- Enter manually --":
        model_name = st.sidebar.text_input("Model Name", value=default_model)
    else:
        model_name = model_option
else:
    # Fallback if no models could be fetched or list is empty
    model_name = st.sidebar.text_input("Model", value=default_model)

st.sidebar.divider()
st.sidebar.title("Pages To Scrape")
base_url = st.sidebar.text_input("Starting URL", placeholder="https://your-site.example/")
urls_input = st.sidebar.text_area(
    "Additional URLs",
    placeholder="https://your-site.example/products\nhttps://your-site.example/cart",
    height=120,
)
consent_mode = st.sidebar.selectbox(
    "Consent Handling",
    ["auto-dismiss", "leave-as-is", "test-consent-flow"],
    help="Auto-dismiss is best for normal local app testing. Use the other modes when consent behavior is part of what you want to test.",
)

st.title("AI Playwright Test Generator")
st.markdown("Generate placeholder-first pytest sync Playwright tests, then resolve them against scraped pages.")

col1, col2 = st.columns([2, 1])

with col1:
    input_mode = st.radio("Requirements Input", ["Paste Text", "Upload File"], horizontal=True)
    raw_requirements = ""

    if input_mode == "Upload File":
        uploaded_file = st.file_uploader("Upload user story or markdown", type=["md", "txt"])
        if uploaded_file is not None:
            raw_requirements = uploaded_file.read().decode("utf-8")
            st.text_area("Uploaded Requirements", value=raw_requirements, height=220, disabled=True)
        else:
            st.info("Upload a `.md` or `.txt` file containing your user story and acceptance criteria.")
    else:
        raw_requirements = st.text_area(
            "Requirements",
            placeholder="## User Story\nAs a customer I want to add items to cart\n\n## Acceptance Criteria\n1. Add item to cart\n2. Go to cart\n3. Check out",
            height=260,
        )

    user_story, criteria = _parse_requirements_text(raw_requirements) if raw_requirements.strip() else ("", "")

    if raw_requirements.strip():
        with st.expander("How The App Interpreted Your Input", expanded=False):
            st.text_area("Parsed User Story", value=user_story, height=100, disabled=True)
            st.text_area("Parsed Acceptance Criteria", value=criteria, height=140, disabled=True)

with col2:
    st.info(
        "Primary workflow:\n"
        "1. Generate a placeholder-based skeleton.\n"
        "2. Scrape the required pages.\n"
        "3. Resolve placeholders into real locators.\n"
        "4. Save the final Python test file."
    )
    st.caption("The intelligent pipeline is now the only generation path in this UI.")

if st.button("Run Intelligent Pipeline", type="primary"):
    st.session_state.pipeline_error = ""
    target_urls = _parse_target_urls(base_url, urls_input)

    if not user_story.strip():
        st.session_state.pipeline_error = "Please provide a user story."
    elif not criteria.strip():
        st.session_state.pipeline_error = "Please provide acceptance criteria."
    else:
        try:
            with st.status("Executing intelligent pipeline...", expanded=True) as status:
                st.write("Phase 1: Generating placeholder skeleton")
                st.write("Phase 2: Scraping target pages")
                st.write("Phase 3: Resolving placeholders into real selectors")
                asyncio.run(
                    _run_pipeline(
                        user_story=user_story,
                        criteria=criteria,
                        provider=provider,
                        provider_base_url=provider_base_url,
                        model_name=model_name,
                        target_urls=target_urls,
                        consent_mode=consent_mode,
                    )
                )
                status.update(label="Pipeline complete", state="complete", expanded=False)
        except Exception as exc:
            st.session_state.pipeline_error = str(exc)

if st.session_state.pipeline_error:
    st.error(st.session_state.pipeline_error)

if st.session_state.pipeline_results:
    st.divider()
    results_tab, skeleton_tab, scrape_tab = st.tabs(["Final Code", "Skeleton", "Scrape Summary"])

    with results_tab:
        st.code(st.session_state.pipeline_results, language="python")
        if st.session_state.pipeline_saved_path:
            st.success(f"Saved to: {st.session_state.pipeline_saved_path}")
        if st.session_state.pipeline_manifest_path:
            st.caption(f"Manifest: {st.session_state.pipeline_manifest_path}")
        st.download_button(
            label="Download Final Test Script",
            data=st.session_state.pipeline_results,
            file_name="generated_test.py",
            mime="text/x-python",
        )

    with skeleton_tab:
        st.code(st.session_state.pipeline_skeleton, language="python")

    with scrape_tab:
        st.write("Pages scraped:")
        if st.session_state.pipeline_urls:
            for url in st.session_state.pipeline_urls:
                element_count = len(st.session_state.pipeline_scraped_pages.get(url, []))
                st.write(f"- {url} ({element_count} elements)")
        else:
            st.write("- No URLs were available to scrape.")

        if st.session_state.pipeline_unresolved:
            st.warning("Some placeholders were unresolved and were converted into explicit pytest skips.")
            for unresolved in st.session_state.pipeline_unresolved:
                st.code(unresolved, language="python")

    st.divider()
    st.subheader("Run Generated Package")
    run_col, rerun_col = st.columns(2)

    with run_col:
        if st.button("Run Generated Tests", disabled=not bool(st.session_state.pipeline_saved_path)):
            try:
                with st.spinner("Running generated tests with pytest. This can take a couple of minutes..."):
                    execution_result = PipelineRunService().run_saved_test(st.session_state.pipeline_saved_path)
                    st.session_state.pipeline_run_result = execution_result.run_result
                    st.session_state.pipeline_run_output = execution_result.display_output
                    st.session_state.pipeline_run_command = " ".join(execution_result.command)
                    st.session_state.pipeline_run_return_code = execution_result.return_code
                    _store_report_bundle(
                        _build_report_bundle(
                            criteria_text=st.session_state.pipeline_criteria,
                            generated_code=st.session_state.pipeline_results,
                            run_result=execution_result.run_result,
                            saved_path=st.session_state.pipeline_saved_path,
                        )
                    )
            except Exception as exc:
                st.session_state.pipeline_error = f"Failed to run generated tests: {exc}"

    with rerun_col:
        previous_run_result = st.session_state.pipeline_run_result
        rerun_disabled = not bool(st.session_state.pipeline_saved_path) or previous_run_result is None
        if st.button("Re-run Failed Only", disabled=rerun_disabled):
            try:
                with st.spinner("Re-running failed generated tests with pytest..."):
                    execution_result = PipelineRunService().run_saved_test(
                        st.session_state.pipeline_saved_path,
                        rerun_failed_only=True,
                        previous_run=previous_run_result,
                    )
                    st.session_state.pipeline_run_result = execution_result.run_result
                    st.session_state.pipeline_run_output = execution_result.display_output
                    st.session_state.pipeline_run_command = " ".join(execution_result.command)
                    st.session_state.pipeline_run_return_code = execution_result.return_code
                    _store_report_bundle(
                        _build_report_bundle(
                            criteria_text=st.session_state.pipeline_criteria,
                            generated_code=st.session_state.pipeline_results,
                            run_result=execution_result.run_result,
                            saved_path=st.session_state.pipeline_saved_path,
                        )
                    )
            except Exception as exc:
                st.session_state.pipeline_error = f"Failed to rerun generated tests: {exc}"

    run_result = st.session_state.pipeline_run_result
    if isinstance(run_result, RunResult):
        if st.session_state.pipeline_run_command:
            st.caption(f"Command: {st.session_state.pipeline_run_command}")

        if run_result.errors > 0:
            st.error("Pytest hit a collection or import error before the generated tests could run.")

        metric_cols = st.columns(5)
        metric_cols[0].metric("Total", run_result.total)
        metric_cols[1].metric("Passed", run_result.passed)
        metric_cols[2].metric("Failed", run_result.failed)
        metric_cols[3].metric("Skipped", run_result.skipped)
        metric_cols[4].metric("Errors", run_result.errors)

        criteria_lines = [line.strip() for line in st.session_state.pipeline_criteria.splitlines() if line.strip()]
        coverage_analysis = build_coverage_analysis(criteria_lines, st.session_state.pipeline_results)
        coverage_rows = build_coverage_display_rows(coverage_analysis["requirements"], run_result.results)
        if coverage_rows:
            st.dataframe([row.to_dict() for row in coverage_rows], use_container_width=True)

        if st.session_state.pipeline_run_output:
            with st.expander("Pytest Output", expanded=run_result.errors > 0):
                st.code(st.session_state.pipeline_run_output, language="text")

        download_cols = st.columns(4)
        download_cols[0].download_button(
            label="Download Manifest",
            data=_safe_read_text(st.session_state.pipeline_manifest_path),
            file_name="scrape_manifest.json",
            mime="application/json",
            disabled=not bool(st.session_state.pipeline_manifest_path),
        )
        download_cols[1].download_button(
            label="Download Local Report",
            data=st.session_state.pipeline_local_report,
            file_name="report_local.md",
            mime="text/markdown",
            disabled=not bool(st.session_state.pipeline_local_report),
        )
        download_cols[2].download_button(
            label="Download Jira Report",
            data=st.session_state.pipeline_jira_report,
            file_name="report_jira.md",
            mime="text/markdown",
            disabled=not bool(st.session_state.pipeline_jira_report),
        )
        download_cols[3].download_button(
            label="Download HTML Report",
            data=st.session_state.pipeline_html_report,
            file_name="report.html",
            mime="text/html",
            disabled=not bool(st.session_state.pipeline_html_report),
        )

        if st.session_state.pipeline_local_report_path:
            st.caption(f"Local report: {st.session_state.pipeline_local_report_path}")
        if st.session_state.pipeline_jira_report_path:
            st.caption(f"Jira report: {st.session_state.pipeline_jira_report_path}")
        if st.session_state.pipeline_html_report_path:
            st.caption(f"HTML report: {st.session_state.pipeline_html_report_path}")
