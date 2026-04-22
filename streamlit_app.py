"""Streamlit UI for the intelligent scraping pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from src.code_validator import validate_python_syntax
from src.coverage_utils import build_coverage_analysis, build_coverage_display_rows
from src.gantt_utils import (
    build_gantt_chart,
    build_gantt_summary_sentences,
    load_gantt_entries,
    safe_read_sidecar,
)
from src.heatmap_utils import build_confidence_heatmap, build_story_confidence
from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.pipeline_report_service import PipelineReportBundle, PipelineReportService
from src.pipeline_run_service import PipelineRunService
from src.pipeline_writer import PipelineArtifactWriter
from src.pytest_output_parser import RunResult
from src.report_utils import generate_annotated_journey, generate_suite_heatmap
from src.spec_analyzer import SpecAnalyzer, TestCondition
from src.test_generator import TestGenerator
from src.test_plan import TestPlan, apply_editor_rows, build_story_ref
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
        "test_plan": None,
        "plan_confirmed": False,
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


def _build_test_plan(
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


def _plan_rows_from_plan(plan: TestPlan) -> list[dict[str, object]]:
    """Return editable table rows for the current plan."""
    return [
        {
            "reviewed": condition.id in plan.reviewed_ids,
            "id": condition.id,
            "type": condition.type,
            "text": condition.text,
            "expected": condition.expected,
            "source": condition.source,
            "flagged": condition.flagged,
            "src": condition.src,
        }
        for condition in plan.conditions
    ]


async def _run_pipeline(
    user_story: str,
    criteria: str,
    provider: str,
    provider_base_url: str,
    model_name: str,
    target_urls: list[str],
    consent_mode: str,
    reviewed_conditions: list[TestCondition] | None = None,
) -> None:
    client = LLMClient(provider=provider, model=model_name, base_url=provider_base_url)

    conditions = list(reviewed_conditions or [])
    if not conditions:
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

# Quick baseline preset for reproducible debugging runs.
_BASELINE_STARTING_URL = "https://automationexercise.com/"
_BASELINE_ADDITIONAL_URLS = ""
_BASELINE_REQUIREMENTS = """## User Story
As a customer I want to add items to cart

## Acceptance Criteria
1. add items to cart
2. go to cart
3. check the items have been added correctly
4. go to check out
5. check out

(Total: 5 criteria)
"""

if st.sidebar.button("Load baseline (automationexercise.com)", type="secondary"):
    st.session_state.starting_url = _BASELINE_STARTING_URL
    st.session_state.additional_urls = _BASELINE_ADDITIONAL_URLS
    st.session_state.requirements_text = _BASELINE_REQUIREMENTS
    # Keep the UI clean and deterministic after loading baseline inputs.
    st.session_state.pipeline_error = ""
    st.session_state.pipeline_results = ""
    st.session_state.pipeline_skeleton = ""
    st.session_state.pipeline_scrape_summary = ""
    st.session_state.pipeline_saved_path = ""
    st.session_state.pipeline_manifest_path = ""
    st.rerun()

# Migrate legacy auto-keys (label-based) into stable keys.
if not st.session_state.get("starting_url") and st.session_state.get("Starting URL"):
    st.session_state.starting_url = st.session_state.get("Starting URL")
if not st.session_state.get("additional_urls") and st.session_state.get("Additional URLs"):
    st.session_state.additional_urls = st.session_state.get("Additional URLs")

base_url = st.sidebar.text_input(
    "Starting URL",
    placeholder="https://your-site.example/",
    key="starting_url",
)
urls_input = st.sidebar.text_area(
    "Additional URLs",
    placeholder="https://your-site.example/products\nhttps://your-site.example/cart",
    height=120,
    key="additional_urls",
)

# Persist the latest non-empty values so a rerun doesn't accidentally
# wipe the run configuration during button-triggered rerenders.
if base_url.strip():
    st.session_state.last_starting_url = base_url
if urls_input.strip():
    st.session_state.last_additional_urls = urls_input
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
            key="requirements_text",
        )

    # Ensure we use the committed widget value on reruns.
    if input_mode == "Paste Text":
        raw_requirements = str(
            st.session_state.get("requirements_text") or st.session_state.get("Requirements") or raw_requirements
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

if raw_requirements.strip():
    st.divider()
    st.subheader("Living Test Plan")
    st.caption("Review, edit, and sign off all derived conditions before generation is unlocked.")

    build_plan_col, plan_state_col = st.columns([1, 2])
    with build_plan_col:
        if st.button("Build Living Test Plan", type="secondary"):
            try:
                st.session_state.test_plan = _build_test_plan(
                    user_story=user_story,
                    criteria=criteria,
                    provider=provider,
                    provider_base_url=provider_base_url,
                    model_name=model_name,
                )
                st.session_state.plan_confirmed = False
                st.session_state.pipeline_error = ""
            except Exception as exc:
                st.session_state.pipeline_error = f"Failed to build living test plan: {exc}"
    with plan_state_col:
        current_plan = st.session_state.test_plan
        if isinstance(current_plan, TestPlan):
            reviewed_count = len(current_plan.reviewed_ids)
            total_count = len(current_plan.conditions)
            status_text = "Ready for generation" if current_plan.is_ready_for_generation else "Review pending"
            st.write(f"Story Ref: `{current_plan.story_ref}`")
            st.write(f"Conditions reviewed: `{reviewed_count}/{total_count}`")
            st.write(f"Status: `{status_text}`")
        else:
            st.write("Build the plan to review AI-derived conditions before generation.")

    current_plan = st.session_state.test_plan
    if isinstance(current_plan, TestPlan):
        edited_rows_raw = st.data_editor(
            _plan_rows_from_plan(current_plan),
            width="stretch",
            num_rows="dynamic",
            key="living_test_plan_editor",
            column_config={
                "reviewed": st.column_config.CheckboxColumn("Reviewed"),
                "id": st.column_config.TextColumn("ID", disabled=True),
                "type": st.column_config.SelectboxColumn(
                    "Type",
                    options=["happy_path", "boundary", "negative", "exploratory", "regression", "ambiguity"],
                ),
                "text": st.column_config.TextColumn("Condition"),
                "expected": st.column_config.TextColumn("Expected"),
                "source": st.column_config.TextColumn("Source"),
                "flagged": st.column_config.CheckboxColumn("Flagged"),
                "src": st.column_config.SelectboxColumn("Source Kind", options=["ai", "manual", "automation"]),
            },
        )
        if hasattr(edited_rows_raw, "to_dict"):
            edited_rows = edited_rows_raw.to_dict("records")
        else:
            edited_rows = list(edited_rows_raw)

        plan_action_col, signoff_col = st.columns([3, 2])
        with plan_action_col:
            st.caption("Optional: save edits without signing off.")
            if st.button("Save Test Plan Edits", type="secondary"):
                st.session_state.test_plan = apply_editor_rows(current_plan, edited_rows)
                st.session_state.plan_confirmed = st.session_state.test_plan.is_ready_for_generation

        with signoff_col:
            tester_name = st.text_input("Tester Name", value=current_plan.tester_name, key="test_plan_tester_name")
            sign_off_notes = st.text_area(
                "Sign-off Notes",
                value=current_plan.sign_off_notes,
                height=90,
                key="test_plan_signoff_notes",
            )
            if st.button("Save And Sign Off Test Plan", type="primary"):
                signed_plan = apply_editor_rows(current_plan, edited_rows).sign_off(
                    tester_name=tester_name,
                    sign_off_notes=sign_off_notes,
                )
                st.session_state.test_plan = signed_plan
                st.session_state.plan_confirmed = signed_plan.is_ready_for_generation

        if current_plan.unreviewed_ids:
            pending_ids = ", ".join(sorted(current_plan.unreviewed_ids))
            st.warning(f"Generation remains locked until every condition is reviewed. Pending: {pending_ids}")
        elif not current_plan.is_ready_for_generation:
            st.info("All conditions are reviewed. Add tester sign-off to unlock generation.")
        else:
            st.success("The living test plan is signed off and generation is unlocked.")

run_disabled = bool(raw_requirements.strip()) and not bool(st.session_state.plan_confirmed)
if st.button("Run Intelligent Pipeline", type="primary", disabled=run_disabled):
    st.session_state.pipeline_error = ""
    # Re-read requirements at click time to avoid cases where the UI shows
    # text but the rerun that handles the click sees an empty widget value.
    raw_requirements_for_run = str(
        st.session_state.get("requirements_text") or st.session_state.get("Requirements") or raw_requirements or ""
    )
    user_story, criteria = (
        _parse_requirements_text(raw_requirements_for_run) if raw_requirements_for_run.strip() else ("", "")
    )

    # Read URL inputs from session_state so the run uses
    # the latest typed values even across Streamlit reruns.
    # (Some Streamlit versions/components may still populate legacy auto-keys
    # based on label text, so we fall back to those too.)
    starting_url_value = (
        st.session_state.get("starting_url")
        or st.session_state.get("Starting URL")
        or st.session_state.get("last_starting_url")
        or base_url
    )
    additional_urls_value = (
        st.session_state.get("additional_urls")
        or st.session_state.get("Additional URLs")
        or st.session_state.get("last_additional_urls")
        or urls_input
    )
    target_urls = _parse_target_urls(
        str(starting_url_value),
        str(additional_urls_value),
    )

    if not user_story.strip():
        st.session_state.pipeline_error = "Please provide a user story."
    elif not criteria.strip():
        st.session_state.pipeline_error = "Please provide acceptance criteria."
    elif not st.session_state.plan_confirmed:
        st.session_state.pipeline_error = "Build, review, and sign off the Living Test Plan before generation."
    else:
        try:
            with st.status("Executing intelligent pipeline...", expanded=True) as status:
                st.write(f"Requirements raw length: {len(raw_requirements_for_run)}")
                st.write(f"Starting URL raw: {starting_url_value!r}")
                st.write(f"Additional URLs raw: {additional_urls_value!r}")
                st.write(f"Target URLs ({len(target_urls)}): {target_urls}")
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
                        reviewed_conditions=(
                            st.session_state.test_plan.conditions
                            if isinstance(st.session_state.test_plan, TestPlan)
                            else None
                        ),
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
            st.dataframe([row.to_dict() for row in coverage_rows], width="stretch")

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

        st.divider()
        st.subheader("Evidence Viewer")
        # Anchor evidence to the repo root so the UI can always find it even if
        # Streamlit was launched from a different working directory.
        evidence_dir = Path(__file__).resolve().parent / "evidence"
        if not evidence_dir.exists():
            st.info("No evidence sidecars found yet. Run generated tests to produce `evidence/*.evidence.json`.")
        else:
            sidecars = sorted(evidence_dir.glob("*.evidence.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not sidecars:
                st.info("No evidence sidecars found yet. Run generated tests to produce `evidence/*.evidence.json`.")
            else:
                evidence_tabs = st.tabs(["Annotated Screenshot", "Gantt Timeline", "Coverage Heat Map"])

                with evidence_tabs[0]:
                    selected = st.selectbox(
                        "Select evidence sidecar",
                        options=sidecars,
                        format_func=lambda p: p.name,
                    )
                    view_mode = st.selectbox(
                        "View mode",
                        options=["annotated", "heatmap", "clean"],
                        index=0,
                        help="annotated = numbered steps; heatmap = density rings; clean = screenshot only.",
                    )
                    html = generate_annotated_journey(
                        sidecar_path=Path(selected),
                        view_mode=view_mode,  # type: ignore[arg-type]
                        title=selected.stem,
                    )
                    components.html(html, height=900, scrolling=True)

                with evidence_tabs[1]:
                    entries = load_gantt_entries(evidence_dir)
                    if not entries:
                        st.info("No Gantt data yet. Run generated tests to produce `.evidence.json` sidecars.")
                    else:
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            group_mode = st.selectbox(
                                "Grouping Mode",
                                options=["condition_type", "sprint", "source"],
                                index=0,
                                key="gantt_group_mode",
                            )
                            fastest, slowest, coverage = build_gantt_summary_sentences(entries)
                            st.write(f"- {fastest}")
                            st.write(f"- {slowest}")
                            st.write(f"- {coverage}")

                        with col2:
                            # Extract condition metadata from test_plan if available
                            condition_meta = {}
                            if st.session_state.test_plan:
                                for c in st.session_state.test_plan.conditions:
                                    condition_meta[c.id] = {
                                        "type": c.type,
                                        "sprint": getattr(st.session_state.test_plan, "sprint", "Backlog"),
                                        "source": c.src,
                                    }

                            fig = build_gantt_chart(
                                entries,
                                grouping_mode=group_mode,  # type: ignore[arg-type]
                                condition_meta=condition_meta,
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        st.divider()
                        st.subheader("Test Execution Details")
                        selected_test = st.selectbox(
                            "Select test for details",
                            options=sorted(entries, key=lambda e: e.condition_ref),
                            format_func=lambda e: f"{e.condition_ref} ({e.status})",
                        )

                        if selected_test:
                            sidecar_path = evidence_dir / f"{selected_test.test_name}.evidence.json"
                            sidecar = safe_read_sidecar(sidecar_path)
                            if sidecar:
                                test_info = sidecar.get("test", {})
                                col_a, colb = st.columns(2)
                                with col_a:
                                    st.write(f"**Condition Ref:** {test_info.get('condition_ref')}")
                                    st.write(f"**Story Ref:** {test_info.get('story_ref')}")
                                    st.write(f"**Status:** {test_info.get('status')}")
                                with colb:
                                    st.write(f"**Duration:** {test_info.get('duration_s')}s")
                                    st.write(f"**Test Name:** {test_info.get('name')}")

                                st.write("**Steps:**")
                                for step in sidecar.get("steps", []):
                                    status_icon = "✅" if step.get("result", {}).get("status") == "passed" else "❌"
                                    st.write(f"- {status_icon} **{step.get('type').upper()}**: {step.get('label')}")
                                    if step.get("result", {}).get("error"):
                                        st.error(step.get("result", {}).get("error"))

                        st.divider()
                        st.subheader("Raw Execution Data")
                        st.dataframe(
                            [
                                {
                                    "condition_ref": e.condition_ref,
                                    "story_ref": e.story_ref,
                                    "status": e.status,
                                    "duration_s": e.duration_s,
                                    "test_name": e.test_name,
                                }
                                for e in sorted(entries, key=lambda e: (-e.duration_s, e.condition_ref))
                            ],
                            width="stretch",
                        )

                with evidence_tabs[2]:
                    # Feed test plan confirmation state into heatmap
                    test_plan_state = None
                    if st.session_state.test_plan:
                        test_plan_state = {"confirmed_ids": list(st.session_state.test_plan.reviewed_ids)}

                    stories = build_story_confidence(evidence_dir, test_plan_state=test_plan_state)
                    if not stories:
                        st.info("No heat map data yet. Run generated tests to produce `.evidence.json` sidecars.")
                    else:
                        # Summary panels
                        total_stories = len(stories)
                        confirmed = len([s for s in stories if s.level == "tester_confirmed"])
                        gaps = len([s for s in stories if s.level == "gap_open_question"])
                        unreviewed = len([s for s in stories if s.level == "ai_covered_unreviewed"])

                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Total Stories", total_stories)
                        m2.metric("Tester Confirmed", confirmed)
                        m3.metric("Gaps/Failures", gaps)
                        m4.metric("Unreviewed", unreviewed)

                        fig = build_confidence_heatmap(stories)
                        st.plotly_chart(fig, use_container_width=True)

                        st.divider()
                        st.subheader("Story Confidence Details")
                        st.dataframe(
                            [
                                {
                                    "story_ref": s.story_ref,
                                    "confidence": s.level,
                                    "color": s.color,
                                    "conditions_with_evidence": s.total_conditions_with_evidence,
                                    "passed": s.passed_conditions,
                                    "failed": s.failed_conditions,
                                    "skipped": s.skipped_conditions,
                                }
                                for s in stories
                            ],
                            width="stretch",
                        )

                st.divider()
                st.subheader("Suite Heatmap (Coverage Overview)")
                # Build URL options from all sidecars by using the `navigate` steps.
                import json

                url_options: set[str] = set()
                for sidecar_path in sidecars:
                    try:
                        sidecar_obj = json.loads(sidecar_path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    steps = sidecar_obj.get("steps", [])
                    if not isinstance(steps, list):
                        continue
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        if str(step.get("type", "")).lower() != "navigate":
                            continue
                        val = str(step.get("value", "") or "")
                        if val.startswith("http"):
                            url_options.add(val)
                url_list = sorted(url_options)

                if not url_list:
                    st.info("No navigated URLs found in sidecars yet.")
                else:
                    selected_url = st.selectbox("Select page URL", options=url_list)
                    suite_html = generate_suite_heatmap(evidence_dir=evidence_dir, page_url=selected_url)
                    components.html(suite_html, height=850, scrolling=True)
