"""Streamlit UI for the intelligent scraping pipeline.

Multi-page layout:
  - Test Generator — requirements → plan → pipeline → export
  - Run & Fix — run the current suite, repair locators, review this run's evidence
  - Evidence & Reports — evidence viewer, Gantt, heatmap, run history, saved packages
"""

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
from src.pytest_output_parser import is_run_result
from src.settings_store import load_setting, save_setting
from src.storage import get_storage, init_storage
from src.test_plan import TestPlan, apply_editor_rows
from src.test_table import TestTable, table_to_conditions
from src.test_table import apply_editor_rows as apply_test_table_rows
from src.ui.ui_evidence import EvidenceViewer
from src.ui.ui_journey import render_credential_profiles, render_journey_builder
from src.ui.ui_requirements import RequirementsInput
from src.ui.ui_results import ResultsPanel
from src.ui.ui_run_comparison import RunComparison
from src.ui.ui_run_results import RunResultsDisplay
from src.ui.ui_saved_packages import SavedPackagePanel
from src.ui.ui_sidebar import (
    SETTING_CONSENT_MODE,
    SETTING_JIRA_PROJECT_KEY,
    SETTING_LAST_PACKAGE,
    SETTING_MODEL_NAME,
    SETTING_WORKSPACE,
    SidebarConfig,
)
from src.ui_pipeline import (
    PipelineSessionState,
    build_test_plan,
    build_test_table,
    parse_requirements_text,
    parse_target_urls,
    plan_rows_from_plan,
    run_pipeline,
    test_table_rows,
)

st.set_page_config(page_title="TanCat — AI Playwright Test Generator", page_icon="assets/logo.png", layout="wide")


def _init_session_state() -> None:
    """Initialise session state defaults — called once per module load."""
    # B-036 Phase 4: workspace comes from the persisted settings store first,
    # with the WORKSPACE env var as a dev fallback, then "default".
    workspace = load_setting(SETTING_WORKSPACE, None) or os.environ.get("WORKSPACE", "default")
    init_storage(workspace=workspace)

    defaults: dict[str, Any] = {
        "pipeline_results": None,
        "pipeline_skeleton": "",
        "pipeline_saved_path": "",
        "pipeline_manifest_path": "",
        "pipeline_error": "",
        "pipeline_unresolved": [],
        "run_tests_error": "",
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
        "test_table": None,
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


# ---------------------------------------------------------------------------
# Top-level setup
# ---------------------------------------------------------------------------
_init_session_state()

# Handle delayed baseline load (triggered by sidebar button via st.rerun)
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
# Shared sidebar (renders before pages so every page sees the same config)
# ---------------------------------------------------------------------------
# B-041: capture the previously-saved provider BEFORE the sidebar saves the
# newly selected one, so a provider switch below can reset the base URL / model
# instead of leaking stale values from a different provider.
_previous_provider = str(load_setting("provider", "") or "")

config = SidebarConfig.render()
provider = config["provider"]
pom_mode = config.get("pom_mode", False)

default_provider_url, default_model = get_provider_defaults(provider)

# B-041: a base URL / model persisted under a DIFFERENT provider (e.g.
# ollama's http://localhost:11434 left over from an earlier session) must
# never leak into the newly selected provider's fields. On a provider switch,
# reset to the current provider's defaults; the save-on-change block below
# then overwrites the stale values in the settings store.
_provider_switched = bool(_previous_provider) and _previous_provider != provider
_base_url_value = (
    default_provider_url
    if _provider_switched
    else (str(load_setting("provider_base_url", "") or "") or default_provider_url)
)
_model_value = (
    default_model if _provider_switched else (str(load_setting(SETTING_MODEL_NAME, "") or "") or default_model)
)

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

provider_base_url = st.sidebar.text_input(
    "Provider Base URL",
    value=_base_url_value,
    # Key includes the provider so switching providers resets the field —
    # Streamlit ignores `value` once a widget has session state (B-041).
    key=f"provider_base_url_{provider}",
)

# Propagate user-selected provider to ALL fallback LLMClient() instances
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
        model_name = st.sidebar.text_input("Model Name", value=_model_value, key=f"model_name_{provider}")
    else:
        model_name = model_option
else:
    model_name = st.sidebar.text_input("Model", value=_model_value, key=f"model_name_{provider}")

LLMClient.set_session_provider(provider, provider_base_url, model_name)

# B-036 Phase 4: persist base URL + model so the full provider selection
# (not just the provider key) survives restarts.
_stored_base_url = str(load_setting("provider_base_url", "") or "")
if provider_base_url != _stored_base_url:
    save_setting("provider_base_url", provider_base_url)
_stored_model = str(load_setting(SETTING_MODEL_NAME, "") or "")
if model_name != _stored_model:
    save_setting(SETTING_MODEL_NAME, model_name)

# Phase 6d — BYO-LLM health check: first-run "check my LLM" probe. Reuses the
# same LLMClient construction path as generation so "what the user configured"
# is exactly "what the probe checks". Runs on click; the report is cached in
# session state so the result survives the Streamlit rerun that follows a click.
if st.sidebar.button("🩺 Check My LLM", use_container_width=True, key="check_my_llm_btn"):
    from src.llm_health import build_client, check_llm, render_report

    with st.sidebar.spinner("Checking LLM endpoint…"):
        _hc_client = build_client(provider, base_url=provider_base_url, model=model_name)
        _hc_result = check_llm(_hc_client, requested_model=model_name)
    st.session_state["llm_health_report"] = render_report(_hc_result)
    st.session_state["llm_health_ok"] = _hc_result.ok

if st.session_state.get("llm_health_report") is not None:
    _hc_report = st.session_state["llm_health_report"]
    if st.session_state.get("llm_health_ok"):
        st.sidebar.success("LLM connected.")
    else:
        st.sidebar.error("LLM check failed — see details.")
    st.sidebar.code(_hc_report, language=None)

# Phase 6e — license status banner + local Usage panel (offline).
SidebarConfig.render_license_usage()

# B-036 Phase 4: persisted Settings panel (OCR backend, workspace, RAG
# learned-pattern stats). Re-initialises storage immediately when the
# workspace setting changed, so evidence/tests land in the right place.
_settings = SidebarConfig.render_settings()
_workspace = str(_settings.get("workspace", "default") or "default")
if get_storage().workspace != _workspace:
    init_storage(workspace=_workspace)

# Saved package loader (sidebar slot)
SavedPackagePanel().render_sidebar()

st.sidebar.divider()
st.sidebar.title("Pages To Scrape")

# Migrate legacy auto-keys (label-based) into stable keys
if not st.session_state.get("starting_url") and st.session_state.get("Starting URL"):
    st.session_state.starting_url = st.session_state.get("Starting URL")
if not st.session_state.get("additional_urls") and st.session_state.get("Additional URLs"):
    st.session_state.additional_urls = st.session_state.get("Additional URLs")

# ---- Commonly-used fields (always visible) ----
base_url = st.sidebar.text_input(
    "Starting URL",
    placeholder="https://your-site.example/",
    key="starting_url",
)

# ---- Advanced: less-commonly-tweaked settings ----
with st.sidebar.expander("Advanced", expanded=False):
    urls_input = st.text_area(
        "Additional URLs",
        placeholder="https://your-site.example/products\nhttps://your-site.example/cart",
        height=120,
        key="additional_urls",
    )
    # B-036 Phase 4: consent mode persists through the SettingsStore.
    _stored_consent = load_setting(SETTING_CONSENT_MODE, "auto-dismiss")
    consent_mode = st.selectbox(
        "Consent Handling",
        ["auto-dismiss", "leave-as-is", "test-consent-flow"],
        index=["auto-dismiss", "leave-as-is", "test-consent-flow"].index(
            _stored_consent
            if _stored_consent in ["auto-dismiss", "leave-as-is", "test-consent-flow"]
            else "auto-dismiss"
        ),
        key="consent_mode",
        help=(
            "Auto-dismiss is best for normal local app testing. "
            "Use the other modes when consent behavior is part of what you want to test."
        ),
    )
    if consent_mode != _stored_consent:
        save_setting(SETTING_CONSENT_MODE, consent_mode)
    if st.button("Load baseline (automationexercise.com)", type="secondary"):
        st.session_state._load_baseline_requested = True
        st.rerun()

# Persist the latest non-empty values so a rerun doesn't accidentally
# wipe the run configuration during button-triggered rerenders.
if base_url.strip():
    st.session_state.last_starting_url = base_url
if urls_input.strip():
    st.session_state.last_additional_urls = urls_input


# ---------------------------------------------------------------------------
# Page: Test Generator
# ---------------------------------------------------------------------------
def _render_logo_header() -> None:
    """Render the mascot logo + title header."""
    _logo_path = Path(__file__).resolve().parent / "assets" / "logo.png"
    if _logo_path.exists():
        import base64

        with open(_logo_path, "rb") as f:
            _logo_b64 = base64.b64encode(f.read()).decode()
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:20px;margin-bottom:8px;">
                <img src="data:image/png;base64,{_logo_b64}"
                     style="width:100px;height:100px;object-fit:contain;flex-shrink:0;border-radius:12px;" />
                <div>
                    <h1 style="margin:0;font-size:2.5rem;">TanCat</h1>
                    <p style="margin:4px 0 0 0;color:#ccc;font-size:1rem;">
                        Generate placeholder-first pytest sync Playwright tests,
                        then resolve them against scraped pages.
                    </p>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.title("TanCat")
        st.markdown("Generate placeholder-first pytest sync Playwright tests, then resolve them against scraped pages.")


def generator_page() -> None:
    """Test Generator page — the full generation pipeline."""
    _render_logo_header()

    # ------------------------------------------------------------------
    # Requirements input
    # ------------------------------------------------------------------
    input_mode, raw_requirements_raw, _, _ = RequirementsInput.render(base_url, urls_input)

    if input_mode == "Upload File":
        raw_requirements = raw_requirements_raw
    else:
        raw_requirements = str(
            st.session_state.get("requirements_text") or st.session_state.get("Requirements") or raw_requirements_raw
        )

    user_story, criteria = parse_requirements_text(raw_requirements) if raw_requirements.strip() else ("", "")

    # ------------------------------------------------------------------
    # Living Test Plan
    # ------------------------------------------------------------------
    if raw_requirements.strip():
        with st.expander(
            "📋 Living Test Plan",
            expanded=not st.session_state.get("plan_confirmed", False),
        ):
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
                        st.session_state.test_table = None
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
                    flagged_ids_sorted = sorted(c.id for c in current_plan.conditions if c.flagged)
                    if flagged_ids_sorted:
                        st.warning(
                            f"⚑ Flagged: {len(flagged_ids_sorted)} condition(s) "
                            f"({', '.join(flagged_ids_sorted)}) — ambiguous/exploratory; "
                            "review the expected outcome before signing off."
                        )
                else:
                    st.write("Build the plan to review AI-derived conditions before generation.")

            current_plan = st.session_state.test_plan
            if isinstance(current_plan, TestPlan):
                edited_rows_raw = st.data_editor(
                    plan_rows_from_plan(current_plan, st.session_state.test_table),
                    width="stretch",
                    num_rows="dynamic",
                    key="living_test_plan_editor",
                    column_config={
                        "reviewed": st.column_config.CheckboxColumn("Reviewed"),
                        "id": st.column_config.TextColumn("ID", disabled=True),
                        "tests": st.column_config.NumberColumn("Tests", disabled=True),
                        "type": st.column_config.SelectboxColumn(
                            "Type",
                            options=[
                                "happy_path",
                                "boundary",
                                "negative",
                                "exploratory",
                                "regression",
                                "ambiguity",
                            ],
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
                        "flagged": st.column_config.CheckboxColumn(
                            "Flagged",
                            help="Needs attention — ambiguity/exploratory conditions are auto-flagged "
                            "by the analyzer; tick to flag manually.",
                        ),
                        "src": st.column_config.SelectboxColumn(
                            "Source Kind",
                            options=["ai", "manual", "automation"],
                        ),
                    },
                    # Reviewed sits last so the row-header delete checkboxes
                    # (far left, headerless) never abut another checkbox column.
                    column_order=[
                        "id",
                        "tests",
                        "type",
                        "intent",
                        "text",
                        "expected",
                        "source",
                        "flagged",
                        "reviewed",
                    ],
                )
                if hasattr(edited_rows_raw, "to_dict"):  # type: ignore[attr-defined]
                    edited_rows = edited_rows_raw.to_dict("records")  # type: ignore[attr-defined]
                else:
                    edited_rows = list(edited_rows_raw)

                st.caption(
                    "Checkboxes on the far left select rows for deletion "
                    "(or use the 'Delete row(s)' button) — the **Reviewed** tick (far right) approves a condition."
                )

                plan_action_col, signoff_col = st.columns([3, 2])
                with plan_action_col:
                    st.caption("Optional: save edits without signing off.")
                    if st.button("Save Test Plan Edits", type="secondary"):
                        st.session_state.test_plan = apply_editor_rows(current_plan, edited_rows)
                        st.session_state.test_table = None
                        st.session_state.plan_confirmed = st.session_state.test_plan.is_ready_for_generation

                with signoff_col:
                    tester_name = st.text_input(
                        "Tester Name",
                        value=current_plan.tester_name,
                        key="test_plan_tester_name",
                    )
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
                        st.session_state.test_table = None
                        st.session_state.plan_confirmed = signed_plan.is_ready_for_generation

                if current_plan.unreviewed_ids:
                    pending_ids = ", ".join(sorted(current_plan.unreviewed_ids))
                    st.warning(f"Generation remains locked until every condition is reviewed. Pending: {pending_ids}")
                elif not current_plan.is_ready_for_generation:
                    st.info("All conditions are reviewed. Add tester sign-off to unlock generation.")
                else:
                    st.success("The living test plan is signed off and generation is unlocked.")

    # ------------------------------------------------------------------
    # Test Table (AI-034 Phase 2) — expand conditions into concrete rows
    # ------------------------------------------------------------------
    if isinstance(st.session_state.get("test_plan"), TestPlan) and st.session_state.plan_confirmed:
        with st.expander(
            "🧪 Test Table",
            expanded=st.session_state.test_table is None,
        ):
            st.caption(
                "Expand each condition into concrete test rows. One skeleton will be generated "
                "per confirmed row — edit or split rows before generation."
            )

            build_table_col, table_state_col = st.columns([1, 2])
            with build_table_col:
                if st.button("Expand Conditions into Test Rows", type="secondary"):
                    try:
                        st.session_state.test_table = build_test_table(
                            plan=st.session_state.test_plan,
                            provider=provider,
                            provider_base_url=provider_base_url,
                            model_name=model_name,
                        )
                        st.session_state.pipeline_error = ""
                        st.rerun()
                    except Exception as exc:
                        st.session_state.pipeline_error = f"Failed to expand test rows: {exc}"
                        st.rerun()

            with table_state_col:
                current_table = st.session_state.test_table
                if isinstance(current_table, TestTable):
                    total_rows = len(current_table.rows)
                    reviewed_rows = len(current_table.confirmed_row_ids)
                    expanded_conditions = len({row.condition_ref for row in current_table.rows})
                    st.write(f"Test rows reviewed: `{reviewed_rows}/{total_rows}`")
                    st.write(f"Conditions expanded: `{expanded_conditions}` → `{total_rows}` rows")
                else:
                    st.write("Expand the plan to preview the concrete test rows that will be generated.")

            current_table = st.session_state.test_table
            if isinstance(current_table, TestTable):
                table_rows_raw = st.data_editor(
                    test_table_rows(current_table),
                    width="stretch",
                    num_rows="dynamic",
                    key="test_table_editor",
                    column_config={
                        "reviewed": st.column_config.CheckboxColumn("Reviewed"),
                        "id": st.column_config.TextColumn("ID", disabled=True),
                        "condition_ref": st.column_config.TextColumn("Condition", disabled=True),
                        "intent": st.column_config.TextColumn("Intent"),
                        "expected_action": st.column_config.SelectboxColumn(
                            "Action",
                            options=["SELECT", "CLICK", "FILL", "ASSERT", "NAVIGATE"],
                        ),
                        "expected_target": st.column_config.TextColumn("Target"),
                    },
                )
                if hasattr(table_rows_raw, "to_dict"):  # type: ignore[attr-defined]
                    table_edited_rows = table_rows_raw.to_dict("records")  # type: ignore[attr-defined]
                else:
                    table_edited_rows = list(table_rows_raw)

                table_action_col, table_confirm_col = st.columns([3, 2])
                with table_action_col:
                    if st.button("Save Test Table Edits", type="secondary"):
                        st.session_state.test_table = apply_test_table_rows(current_table, table_edited_rows)
                with table_confirm_col:
                    if st.button("Confirm All Test Rows", type="primary"):
                        saved_table = apply_test_table_rows(current_table, table_edited_rows)
                        st.session_state.test_table = TestTable(
                            rows=saved_table.rows,
                            confirmed_ids=set(saved_table.row_ids),
                        )

                if not current_table.is_fully_confirmed:
                    pending_rows = ", ".join(sorted(current_table.unreviewed_row_ids))
                    st.warning(f"Rows pending review: {pending_rows}")
                else:
                    st.success("All test rows are confirmed.")

    # ------------------------------------------------------------------
    # Credential profiles & journey builder
    # ------------------------------------------------------------------
    additional_urls_list = [u.strip() for u in str(urls_input).splitlines() if u.strip()]
    st.session_state._active_credential_profile = render_credential_profiles()
    st.session_state._active_journey_steps = (
        render_journey_builder(additional_urls_list) if additional_urls_list else None
    )

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------
    run_disabled = bool(raw_requirements.strip()) and not bool(st.session_state.plan_confirmed)
    if st.button("Run Intelligent Pipeline", type="primary", disabled=run_disabled):
        st.session_state.pipeline_error = ""
        st.session_state.run_tests_error = ""
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

                    session = PipelineSessionState({str(k): v for k, v in st.session_state.items()})
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
                                table_to_conditions(st.session_state.test_table)
                                if isinstance(st.session_state.test_table, TestTable)
                                and st.session_state.test_table.confirmed_row_ids
                                else (
                                    st.session_state.test_plan.conditions
                                    if isinstance(st.session_state.test_plan, TestPlan)
                                    else None
                                )
                            ),
                            session=session,
                            credential_profile=st.session_state._active_credential_profile,
                            journey_steps=st.session_state._active_journey_steps,
                            pom_mode=pom_mode,
                        )
                    )
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
    # ------------------------------------------------------------------
    # Scraper warnings / errors
    # ------------------------------------------------------------------
    if st.session_state.get("pipeline_scraper_warnings"):
        for warning in st.session_state.pipeline_scraper_warnings:
            st.warning(f"⚠️ Scraper: {warning}")

    if st.session_state.get("pipeline_scraper_errors"):
        for error in st.session_state.pipeline_scraper_errors:
            st.error(f"❌ Scraper: {error}")

    if st.session_state.get("pipeline_journey_captured_count"):
        st.success(f"✅ Captured context from {st.session_state.pipeline_journey_captured_count} pages")

    # ------------------------------------------------------------------
    # Handoff to Run & Fix
    # ------------------------------------------------------------------
    if st.session_state.get("pipeline_results"):
        st.success("Suite generated — move to **▶️ Run & Fix** to execute it, repair locators, and review evidence.")
        if st.button("▶️ Go to Run & Fix", type="primary"):
            st.switch_page(_PAGE_RUN_FIX)


def _render_run_evidence(package_root: str) -> None:
    """Render this run's evidence (sidecars + screenshots) for the current package.

    The sidecars are written fresh on every test run, so the files present in
    ``<package>/evidence/`` are by construction the current run's evidence.
    Screenshot paths inside the sidecar steps reference this run's PNGs.
    """
    pkg = Path(package_root)
    if pkg.is_file():
        pkg = pkg.parent
    evidence_dir = pkg / "evidence"
    if not evidence_dir.exists():
        return
    sidecars = sorted(evidence_dir.glob("*.evidence.json"))
    if not sidecars:
        return

    st.divider()
    with st.expander(f"📸 Evidence — this run ({len(sidecars)} tests)", expanded=False):
        for sidecar in sidecars:
            from src.gantt_utils import safe_read_sidecar

            data = safe_read_sidecar(sidecar)
            if not data:
                continue
            test_meta = data.get("test") or {}
            test_name = str(test_meta.get("name", sidecar.stem))
            status = str(test_meta.get("status", "unknown"))
            icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}.get(status, "⏳")
            steps = data.get("steps") or []
            screenshots: list[Path] = []
            for s in steps:
                shot = s.get("screenshot")
                if shot:
                    candidate = evidence_dir / Path(str(shot)).name
                    if candidate.exists():
                        screenshots.append(candidate)
            with st.expander(f"{icon} {test_name}", expanded=False):
                st.caption(f"Status: {status} · Steps: {len(steps)} · Screenshots: {len(screenshots)}")
                for s in steps:
                    r = s.get("result") or {}
                    label = str(s.get("label") or s.get("type") or "?")
                    step_status = str(r.get("status") or "?")
                    mark = {"passed": "✅", "failed": "❌"}.get(step_status, "⏳")
                    shot = s.get("screenshot")
                    has_shot = bool(shot and (evidence_dir / Path(str(shot)).name).exists())
                    st.write(f"{mark} {label}{' 📸' if has_shot else ''}")
                    if has_shot:
                        st.image(str(evidence_dir / Path(str(shot)).name), width="stretch")


# ---------------------------------------------------------------------------
# Page: Run & Fix
# ---------------------------------------------------------------------------
def run_fix_page() -> None:
    """Run & Fix page — execute the current suite, repair failures, review evidence."""
    st.title("▶️ Run & Fix")
    st.caption("Run the current suite, fix failing/skipped tests, and review this run's evidence.")

    # A package loaded from the sidebar should surface here without forcing a
    # re-run first — hydrate the pipeline state from the loaded manifest.
    loaded_manifest = st.session_state.get("loaded_package_manifest")
    if not loaded_manifest:
        # Auto-restore the last-loaded package (persisted in the settings
        # store) so a fresh session / page reload does not blank the page.
        from src.pipeline_artifact_manager import find_existing_packages

        _last = str(load_setting(SETTING_LAST_PACKAGE, "") or "")
        if _last:
            for _pkg in find_existing_packages(get_storage().generated_tests_dir()):
                if _pkg.package_name == _last:
                    st.session_state.loaded_package_manifest = _pkg.to_dict()
                    st.session_state.loaded_package_root = str(get_storage().generated_tests_dir() / _last)
                    loaded_manifest = st.session_state.get("loaded_package_manifest")
                    break
    if not st.session_state.get("pipeline_results") and loaded_manifest:
        loaded_root = st.session_state.get("loaded_package_root", "")
        if loaded_root and Path(loaded_root).exists():
            test_files = list(loaded_manifest.get("generated_test_files") or [])
            test_paths = [Path(loaded_root) / f for f in test_files]
            test_paths = [tp for tp in test_paths if tp.exists()] or sorted(Path(loaded_root).glob("test_*.py"))
            if test_paths:
                st.session_state.pipeline_saved_path = str(loaded_root)
                st.session_state.pipeline_manifest_path = str(Path(loaded_root) / "package_manifest.json")
                st.session_state.pipeline_results = "\n".join(tp.read_text(encoding="utf-8") for tp in test_paths)
                save_setting(SETTING_LAST_PACKAGE, loaded_manifest.get("package_name", ""))
                # Hydrate criteria too — reports and the coverage traceability
                # table build rows from pipeline_criteria, which is empty when
                # a package is loaded without generating in this session.
                if not st.session_state.get("pipeline_criteria"):
                    from src.ui_pipeline import parse_requirements_text

                    _story = str(loaded_manifest.get("source_story") or "")
                    _, _criteria = parse_requirements_text(_story)
                    st.session_state.pipeline_criteria = _criteria

    has_suite = bool(
        st.session_state.get("pipeline_results")
        or st.session_state.get("pipeline_saved_path")
        or is_run_result(st.session_state.get("pipeline_run_result"))
    )
    if not has_suite:
        st.info(
            "No current suite loaded. Generate tests on the **Test Generator** page, "
            "or load a saved package from the sidebar."
        )
        if st.button("🧪 Go to Test Generator", type="primary"):
            st.switch_page(_PAGE_GENERATOR)
        return

    # ------------------------------------------------------------------
    # Results display (moved from the Test Generator page)
    # ------------------------------------------------------------------
    if st.session_state.get("pipeline_results"):
        st.divider()
        ResultsPanel.render_tabs(
            results=st.session_state.pipeline_results,
            skeleton=st.session_state.pipeline_skeleton,
            saved_path=st.session_state.pipeline_saved_path,
            manifest_path=st.session_state.pipeline_manifest_path,
        )
        ResultsPanel.render_run_section()

    run_result = st.session_state.get("pipeline_run_result")
    if is_run_result(run_result):
        RunResultsDisplay.render(run_result)

    # This-run evidence — gated on a run actually happening in this session,
    # so the page never shows stale sidecars from a previous session/run as
    # "this run" (sidecars persist on disk across sessions).
    if is_run_result(st.session_state.get("pipeline_run_result")):
        _run_evidence_root = st.session_state.get("pipeline_saved_path") or st.session_state.get("loaded_package_root")
        if _run_evidence_root:
            _render_run_evidence(str(_run_evidence_root))

    # ------------------------------------------------------------------
    # Export panel (lives here so you export the package you can see)
    # ------------------------------------------------------------------
    if st.session_state.pipeline_saved_path:
        with st.expander("📦 Export Test Package", expanded=False):
            export_mode_choice = st.selectbox(
                "Export Mode",
                options=["Flat (inline locators)", "POM (page-object modules)"],
                help=("Flat: single test files with inline locators. POM: separate page-object modules."),
                key="export_mode_selection",
            )

            # B-036 Phase 4: Jira project key is an export-time field —
            # persisted, default "TEST". It feeds Jira test-case IDs and the
            # exported Jira report header (``PipelineReportService``).
            _stored_jira_key = str(load_setting(SETTING_JIRA_PROJECT_KEY, "TEST") or "TEST")
            jira_project_key = st.text_input(
                "Jira Project Key",
                value=_stored_jira_key,
                max_chars=10,
                help="Prefix used for Jira test-case IDs and the Jira report header (default TEST).",
                key="jira_project_key",
            )
            if (jira_project_key or "TEST").strip().upper() != _stored_jira_key.strip().upper():
                save_setting(SETTING_JIRA_PROJECT_KEY, (jira_project_key or "TEST").strip().upper())

            if st.button("Export Clean Package", type="primary", key="export_button"):
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

            export_result = st.session_state.get("export_result")
            if export_result and not st.session_state.get("export_button_pressed"):
                st.info(f"Last export: `{export_result.export_dir}` — {len(export_result.test_files)} test(s)")

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
# Page: Evidence & Reports
# ---------------------------------------------------------------------------
def evidence_page() -> None:
    """Evidence & Reports page — screenshots, Gantt, heatmaps, run history."""
    st.title("📊 Evidence & Reports")
    st.caption("Annotated test journeys, Gantt timelines, coverage heatmaps, and run history.")

    SavedPackagePanel().render_main_panel()

    st.divider()
    base_dir = get_storage().generated_tests_dir()
    EvidenceViewer(base_dir).render()

    RunComparison().render()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
_PAGE_GENERATOR = st.Page(generator_page, title="Test Generator", icon="🧪")
_PAGE_RUN_FIX = st.Page(run_fix_page, title="Run & Fix", icon="▶️")
_PAGE_EVIDENCE = st.Page(evidence_page, title="Evidence & Reports", icon="📊")

pg = st.navigation([_PAGE_GENERATOR, _PAGE_RUN_FIX, _PAGE_EVIDENCE])
pg.run()
