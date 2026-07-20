"""Streamlit UI for the intelligent scraping pipeline."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src.llm_client import LLMClient
from src.provider_config import (
    get_provider_defaults,
    provider_requires_openai_api_key,
    resolve_openai_api_key,
    sync_openai_api_key_to_env,
)
from src.pytest_output_parser import RunResult
from src.storage import get_storage, init_storage
from src.test_plan import TestPlan, apply_editor_rows
from src.ui.ui_evidence import EvidenceViewer
from src.ui.ui_journey import render_credential_profiles, render_journey_builder
from src.ui.ui_requirements import RequirementsInput
from src.ui.ui_results import ResultsPanel
from src.ui.ui_run_results import RunResultsDisplay
from src.ui.ui_saved_packages import SavedPackagePanel
from src.ui.ui_sidebar import SidebarConfig
from src.ui_pipeline import (
    PipelineSessionState,
    build_test_plan,
    parse_requirements_text,
    parse_target_urls,
    plan_rows_from_plan,
    run_pipeline,
)

st.set_page_config(page_title="AI Playwright Generator", page_icon="assets/logo.png", layout="wide")


def _init_session_state() -> None:
    # Workspace isolation — set via WORKSPACE env var (default: "default")
    init_storage(workspace=os.environ.get("WORKSPACE", "default"))

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
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


_init_session_state()

if st.session_state.pop("_load_baseline_requested", False):
    st.session_state.starting_url = RequirementsInput.BASELINE_STARTING_URL
    st.session_state.additional_urls = RequirementsInput.BASELINE_ADDITIONAL_URLS
    st.session_state.requirements_text = RequirementsInput.BASELINE_REQUIREMENTS
    st.session_state.pipeline_error = ""
    st.session_state.pipeline_results = ""
    st.session_state.pipeline_skeleton = ""
    st.session_state.pipeline_scrape_summary = ""
    st.session_state.pipeline_saved_path = ""
    st.session_state.pipeline_manifest_path = ""

# ---------------------------------------------------------------------------
# Sidebar configuration
# ---------------------------------------------------------------------------
config = SidebarConfig.render()
provider = config["provider"]
pom_mode = config.get("pom_mode", False)

default_provider_url, default_model = get_provider_defaults(provider)

user_openai_api_key: str | None = None
if provider_requires_openai_api_key(provider):
    user_openai_api_key = st.sidebar.text_input(
        "OpenAI API Key",
        type="password",
        key="openai_api_key",
        help=(
            "Required for OpenAI (cloud). Stored in memory for this session only — "
            "never written to disk. Azure/AWS deployments can inject OPENAI_API_KEY "
            "instead."
        ),
    )
    if not (user_openai_api_key or "").strip() and not os.environ.get("OPENAI_API_KEY", "").strip():
        st.sidebar.warning("Enter your OpenAI API key to use cloud generation.")

resolved_openai_api_key = resolve_openai_api_key(provider=provider, user_api_key=user_openai_api_key)
sync_openai_api_key_to_env(provider, resolved_openai_api_key)

provider_base_url = st.sidebar.text_input("Provider Base URL", value=default_provider_url)

# Propagate user-selected provider to ALL fallback LLMClient() instances
# throughout the pipeline so they don't fall back to .env.
LLMClient.set_session_provider(provider, provider_base_url)

# Attempt to fetch models from the provider
available_models: list[str] = []
try:
    temp_client = LLMClient(provider=provider, base_url=provider_base_url)
    available_models = temp_client.list_models(timeout=2)
except Exception:
    pass

if available_models:
    model_option = st.sidebar.selectbox("Select Model", ["-- Enter manually --"] + available_models)
    if model_option == "-- Enter manually --":
        model_name = st.sidebar.text_input("Model Name", value=default_model)
    else:
        model_name = model_option
else:
    model_name = st.sidebar.text_input("Model", value=default_model)

LLMClient.set_session_provider(provider, provider_base_url, model_name)

# AI-026: Saved package loader (sidebar)
SavedPackagePanel().render_sidebar()

st.sidebar.divider()
st.sidebar.title("Pages To Scrape")

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

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
# Mascot logo — alongside the title using a flexbox HTML container
_logo_path = Path(__file__).resolve().parent / "assets" / "logo.png"
if _logo_path.exists():
    # Read logo as base64 to embed in inline HTML
    import base64

    with open(_logo_path, "rb") as f:
        _logo_b64 = base64.b64encode(f.read()).decode()
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:20px;margin-bottom:8px;">
            <img src="data:image/png;base64,{_logo_b64}" style="width:100px;height:100px;object-fit:contain;flex-shrink:0;border-radius:12px;" />
            <div>
                <h1 style="margin:0;font-size:2.5rem;">AI Playwright Test Generator</h1>
                <p style="margin:4px 0 0 0;color:#ccc;font-size:1rem;">Generate placeholder-first pytest sync Playwright tests, then resolve them against scraped pages.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.title("AI Playwright Test Generator")
    st.markdown("Generate placeholder-first pytest sync Playwright tests, then resolve them against scraped pages.")

# Baseline preset button
if st.sidebar.button("Load baseline (automationexercise.com)", type="secondary"):
    st.session_state._load_baseline_requested = True
    st.rerun()

# ---------------------------------------------------------------------------
# Requirements input
# ---------------------------------------------------------------------------
input_mode, raw_requirements_raw, _, _ = RequirementsInput.render(base_url, urls_input)

# Ensure we use the committed widget value on reruns.
if input_mode == "Upload File":
    raw_requirements = raw_requirements_raw
else:
    raw_requirements = str(
        st.session_state.get("requirements_text") or st.session_state.get("Requirements") or raw_requirements_raw
    )

user_story, criteria = parse_requirements_text(raw_requirements) if raw_requirements.strip() else ("", "")

if raw_requirements.strip():
    st.divider()
    st.subheader("Living Test Plan")
    st.caption("Review, edit, and sign off all derived conditions before generation is unlocked.")

    build_plan_col, plan_state_col = st.columns([1, 2])
    with build_plan_col:
        if st.button("Build Living Test Plan", type="secondary"):
            try:
                st.session_state.test_plan = build_test_plan(
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
                st.rerun()

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
            plan_rows_from_plan(current_plan),
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
                "intent": st.column_config.SelectboxColumn(
                    "Intent",
                    options=[
                        "element_presence",
                        "element_behavior",
                        "state_assertion",
                        "journey_step",
                        "journey_outcome",
                    ],
                ),
                "text": st.column_config.TextColumn("Condition"),
                "expected": st.column_config.TextColumn("Expected"),
                "source": st.column_config.TextColumn("Source"),
                "flagged": st.column_config.CheckboxColumn("Flagged"),
                "src": st.column_config.SelectboxColumn("Source Kind", options=["ai", "manual", "automation"]),
            },
        )
        if hasattr(edited_rows_raw, "to_dict"):  # type: ignore[attr-defined]
            edited_rows = edited_rows_raw.to_dict("records")  # type: ignore[attr-defined]
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

# ---------------------------------------------------------------------------
# Credential profiles and journey builder (rendered once per page load)
# ---------------------------------------------------------------------------
additional_urls_list = [u.strip() for u in str(urls_input).splitlines() if u.strip()]
st.session_state._active_credential_profile = render_credential_profiles()
st.session_state._active_journey_steps = render_journey_builder(additional_urls_list) if additional_urls_list else None

# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------
run_disabled = bool(raw_requirements.strip()) and not bool(st.session_state.plan_confirmed)
if st.button("Run Intelligent Pipeline", type="primary", disabled=run_disabled):
    st.session_state.pipeline_error = ""
    raw_requirements_for_run = str(
        st.session_state.get("requirements_text") or st.session_state.get("Requirements") or raw_requirements or ""
    )
    user_story, criteria = (
        parse_requirements_text(raw_requirements_for_run) if raw_requirements_for_run.strip() else ("", "")
    )

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
    target_urls = parse_target_urls(
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

                # Build session wrapper for ui_pipeline
                session = PipelineSessionState({str(k): v for k, v in st.session_state.items()})
                # Use credential/journey values rendered at module level
                asyncio.run(
                    run_pipeline(
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
                        session=session,
                        credential_profile=st.session_state._active_credential_profile,
                        journey_steps=st.session_state._active_journey_steps,
                        pom_mode=pom_mode,
                    )
                )
                # Sync pipeline-managed keys back to st.session_state.
                # Use a whitelist to avoid overwriting widget-owned keys
                # (e.g. test_plan_signoff_notes) which would raise:
                #   st.session_state.<key> cannot be modified after the widget
                #   with key <key> is instantiated
                _PIPELINE_KEYS = {
                    "pipeline_results",
                    "pipeline_skeleton",
                    "pipeline_saved_path",
                    "pipeline_manifest_path",
                    "pipeline_error",
                    "pipeline_unresolved",
                    "pipeline_scraped_pages",
                    "pipeline_urls",
                    "pipeline_criteria",
                    "pipeline_conditions",
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
                }
                for key in _PIPELINE_KEYS:
                    value = session.get(key)
                    if value is not None:
                        st.session_state[key] = value
                status.update(label="Pipeline complete", state="complete", expanded=False)
        except Exception as exc:
            st.session_state.pipeline_error = str(exc)

if st.session_state.pipeline_error:
    st.error(st.session_state.pipeline_error)

# ---------------------------------------------------------------------------
# Export panel — clean test package without EvidenceTracker
# ---------------------------------------------------------------------------
if st.session_state.pipeline_saved_path:
    st.divider()
    st.subheader("📦 Export Test Package")

    export_mode_choice = st.selectbox(
        "Export Mode",
        options=["Flat (inline locators)", "POM (page-object modules)"],
        help="Flat: single test files with inline locators. POM: separate page-object modules.",
        key="export_mode_selection",
    )

    if st.button("Export Clean Package", type="primary", key="export_button"):
        from pathlib import Path

        from src.export_service import export_clean_suite
        from src.pipeline_models import ExportMode

        source_path = Path(st.session_state.pipeline_saved_path)
        export_mode = ExportMode.FLAT if "Flat" in export_mode_choice else ExportMode.POM

        try:
            with st.status("Exporting clean test package...", expanded=True) as status:
                st.write(f"Source: {source_path}")
                st.write(f"Mode: {'POM' if export_mode == ExportMode.POM else 'Flat'}")

                result = export_clean_suite(
                    source_package_dir=source_path,
                    export_mode=export_mode,
                    output_base_dir="exported_tests",
                    story_slug=st.session_state.get("story_slug", ""),
                )

                st.success(f"✅ Exported to: `{result.export_dir}`")
                st.write(f"  - Test files: {len(result.test_files)}")
                st.write(f"  - Page objects: {len(result.page_objects)}")
                st.write("  - Conftest: 1")
                st.write("  - README: 1")

                st.session_state.export_result = result
                status.update(label="Export complete", state="complete", expanded=False)
        except FileNotFoundError as exc:
            st.error(f"Export failed: {exc}")
        except Exception as exc:
            st.error(f"Export failed: {exc}")

    # Show previous export result if stored
    export_result = st.session_state.get("export_result")
    if export_result and not st.session_state.get("export_button_pressed"):
        st.info(f"Last export: `{export_result.export_dir}` — {len(export_result.test_files)} test(s)")

# ---------------------------------------------------------------------------
# Scraper error surfacing (Task 5)
# ---------------------------------------------------------------------------
if st.session_state.get("pipeline_scraper_warnings"):
    for warning in st.session_state.pipeline_scraper_warnings:
        st.warning(f"⚠️ Scraper: {warning}")

if st.session_state.get("pipeline_scraper_errors"):
    for error in st.session_state.pipeline_scraper_errors:
        st.error(f"❌ Scraper: {error}")

if st.session_state.get("pipeline_journey_captured_count"):
    st.success(f"✅ Captured context from {st.session_state.pipeline_journey_captured_count} pages")

# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
if st.session_state.pipeline_results:
    st.divider()
    ResultsPanel.render_tabs(
        results=st.session_state.pipeline_results,
        skeleton=st.session_state.pipeline_skeleton,
        saved_path=st.session_state.pipeline_saved_path,
        manifest_path=st.session_state.pipeline_manifest_path,
    )
    ResultsPanel.render_run_section()

    run_result = st.session_state.pipeline_run_result
    if isinstance(run_result, RunResult):
        RunResultsDisplay.render(run_result)

    # Bug report display
    if st.session_state.get("pipeline_bug_report"):
        st.divider()
        st.subheader("Bug Report")
        st.code(st.session_state.pipeline_bug_report, language="text")
        if st.session_state.get("pipeline_bug_report_path"):
            st.download_button(
                label="Download Bug Report",
                data=st.session_state.pipeline_bug_report,
                file_name="bug_report.txt",
                mime="text/plain",
            )

# ---------------------------------------------------------------------------
# AI-026: Saved package main panel (rendered when a package is loaded)
# ---------------------------------------------------------------------------
SavedPackagePanel().render_main_panel()

# ---------------------------------------------------------------------------
# Evidence viewer
# ---------------------------------------------------------------------------
st.divider()
base_dir = get_storage().generated_tests_dir()
EvidenceViewer(base_dir).render()
