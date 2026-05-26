"""Streamlit rendering helpers — pure UI, no business logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import streamlit as st

if TYPE_CHECKING:
    from src.journey_scraper import CredentialProfile, JourneyStep
import streamlit.components.v1 as components

from src.coverage_utils import build_coverage_analysis, build_coverage_display_rows
from src.failure_classifier import FailureCategory, classify_failure
from src.gantt_utils import (
    build_gantt_chart,
    build_gantt_summary_sentences,
    load_gantt_entries,
    safe_read_sidecar,
)
from src.heatmap_utils import build_confidence_heatmap, build_story_confidence
from src.pytest_output_parser import RunResult, TestResult
from src.report_utils import generate_annotated_journey, generate_suite_heatmap

# ---------------------------------------------------------------------------
# Type aliases for credential/journey UI state
# ---------------------------------------------------------------------------

_CredentialProfileDict = dict[str, str]  # {"label": str, "username": str, "password": str}
_JourneyStepDict = dict[str, str]  # {"action": str, "url"?: str, "selector"?: str, ...}

# ---------------------------------------------------------------------------
# Credential Profiles section
# ---------------------------------------------------------------------------


def render_credential_profiles() -> CredentialProfile | None:
    """Render the authentication section of the UI.

    Returns the active credential profile, or None if authentication is disabled.
    Credentials are stored in session state only — never persisted to disk.
    """
    from src.journey_scraper import CredentialProfile

    # Initialise session state keys
    if "credential_profiles" not in st.session_state:
        st.session_state["credential_profiles"] = []
    if "active_credential_index" not in st.session_state:
        st.session_state["active_credential_index"] = 0
    if "auth_enabled" not in st.session_state:
        st.session_state["auth_enabled"] = False

    with st.expander("🔐 Authentication (optional)", expanded=st.session_state.auth_enabled):
        st.caption(
            "Define credential profiles for authenticated pages. "
            "Use `{{username}}` and `{{password}}` in journey fill steps."
        )

        st.session_state.auth_enabled = st.toggle("Pages require login", value=st.session_state.auth_enabled)

        if not st.session_state.auth_enabled:
            st.info("Authentication is disabled. Add profiles below and toggle this on to use them.")
            return None

        profiles = st.session_state.credential_profiles

        # Render existing profiles
        for idx, profile in enumerate(profiles):
            label_col, user_col, pass_col, action_col = st.columns([1, 2, 2, 1])
            with label_col:
                profiles[idx]["label"] = st.text_input(
                    "Profile label",
                    value=profile.get("label", ""),
                    key=f"cred_label_{idx}",
                )
            with user_col:
                profiles[idx]["username"] = st.text_input(
                    "Username",
                    value=profile.get("username", ""),
                    key=f"cred_user_{idx}",
                )
            with pass_col:
                # Show masked password
                current_password = profile.get("password", "")
                profiles[idx]["password"] = st.text_input(
                    "Password",
                    value=current_password,
                    type="password",
                    key=f"cred_pass_{idx}",
                )
            with action_col:
                if st.button(f"Remove #{idx + 1}", key=f"cred_remove_{idx}"):
                    st.session_state.credential_profiles.pop(idx)
                    if st.session_state.active_credential_index >= len(st.session_state.credential_profiles):
                        st.session_state.active_credential_index = max(0, len(st.session_state.credential_profiles) - 1)
                    st.rerun()

        # Add new profile button
        if st.button("➕ Add profile"):
            st.session_state.credential_profiles.append(
                {
                    "label": f"Profile {len(profiles) + 1}",
                    "username": "",
                    "password": "",
                }
            )
            st.rerun()

        # Active profile selector
        if profiles:
            profile_labels = [p.get("label", f"Profile {i + 1}") for i, p in enumerate(profiles)]
            st.session_state.active_credential_index = st.selectbox(
                "Active profile",
                options=range(len(profiles)),
                format_func=lambda i: profile_labels[i],
                index=min(st.session_state.active_credential_index, len(profiles) - 1),
            )

            # Return the active CredentialProfile
            active = profiles[st.session_state.active_credential_index]
            return CredentialProfile(
                label=active.get("label", ""),
                username=active.get("username", ""),
                password=active.get("password", ""),
            )

        st.info("No profiles defined yet. Click 'Add profile' to create one.")
        return None


# ---------------------------------------------------------------------------
# Journey Builder section
# ---------------------------------------------------------------------------


def render_journey_builder(additional_urls: list[str]) -> list[JourneyStep] | None:
    """Render the journey builder section of the UI.

    Args:
        additional_urls: Current URL list for "Build from URL list" auto-populate.

    Returns:
        List of JourneyStep objects, or None if journey builder is not used.
    """
    # Initialise session state keys
    if "journey_steps" not in st.session_state:
        st.session_state["journey_steps"] = []
    if "journey_enabled" not in st.session_state:
        st.session_state["journey_enabled"] = False

    with st.expander(
        "🗺️ Journey steps (optional — for dynamic or authenticated pages)",
        expanded=st.session_state.journey_enabled,
    ):
        st.caption(
            "Define the steps the scraper will follow. Add a Capture step wherever you want page context collected."
        )

        steps = st.session_state.journey_steps

        # Build from URL list button
        url_col, enable_col = st.columns([3, 1])
        with url_col:
            if st.button("📋 Build from URL list", disabled=(not additional_urls)):
                new_steps = _urls_to_journey_step_dicts(additional_urls)
                st.session_state.journey_steps.extend(new_steps)
                st.session_state.journey_enabled = True
                st.rerun()
        with enable_col:
            st.session_state.journey_enabled = st.toggle(
                "Journey builder",
                value=st.session_state.journey_enabled,
                key="journey_toggle",
            )

        # Render each step
        for idx, step in enumerate(steps):
            step = _render_single_step(idx, step)
            steps[idx] = step

        # Add step button
        if st.button("➕ Add step"):
            st.session_state.journey_steps.append(
                {
                    "action": "goto",
                    "url": "",
                    "selector": "",
                    "text": "",
                    "label": "",
                    "description": "",
                }
            )
            st.rerun()

        # Convert to JourneyStep objects
        if steps and st.session_state.journey_enabled:
            return [_dict_to_journey_step(s) for s in steps]
        return None


def _render_single_step(idx: int, step: _JourneyStepDict) -> _JourneyStepDict:
    """Render a single journey step row and return the updated dict."""
    action_options = ["goto", "click", "fill", "capture", "wait"]
    action_col, fields_col, remove_col = st.columns([1, 4, 0.5])

    with action_col:
        step["action"] = st.selectbox(
            f"Step {idx + 1}",
            options=action_options,
            index=action_options.index(step.get("action", "goto")),
            key=f"journey_action_{idx}",
        )

    with fields_col:
        action = step.get("action", "goto")
        if action == "goto":
            step["url"] = st.text_input(
                "URL",
                value=step.get("url", ""),
                key=f"journey_url_{idx}",
                help="URL to navigate to",
            )
            step["description"] = st.text_input(
                "Description",
                value=step.get("description", f"Navigate to {step.get('url', '')}"),
                key=f"journey_desc_{idx}",
            )

        elif action == "click":
            step["selector"] = st.text_input(
                "Selector",
                value=step.get("selector", ""),
                key=f"journey_selector_{idx}",
                help="CSS selector or visible text to click",
            )
            step["description"] = st.text_input(
                "Description",
                value=step.get("description", "click element"),
                key=f"journey_desc_{idx}",
            )

        elif action == "fill":
            step["selector"] = st.text_input(
                "Selector",
                value=step.get("selector", ""),
                key=f"journey_selector_{idx}",
                help="CSS selector for the input field",
            )
            step["text"] = st.text_input(
                "Value",
                value=step.get("text", ""),
                key=f"journey_text_{idx}",
                help="Use {{username}} or {{password}} for credential templates",
            )
            step["description"] = st.text_input(
                "Description",
                value=step.get("description", "fill field"),
                key=f"journey_desc_{idx}",
            )

        elif action == "capture":
            step["label"] = st.text_input(
                "Label",
                value=step.get("label", ""),
                key=f"journey_label_{idx}",
                help="Human-readable label for this capture point",
            )
            step["description"] = st.text_input(
                "Description",
                value=step.get("description", f"Capture {step.get('label', 'page')}"),
                key=f"journey_desc_{idx}",
            )

        elif action == "wait":
            step["selector"] = st.text_input(
                "Selector (optional)",
                value=step.get("selector", ""),
                key=f"journey_selector_{idx}",
                help="CSS selector to wait for, or leave blank for time-based wait",
            )
            step["text"] = st.text_input(
                "Duration (seconds)",
                value=step.get("text", "1.0"),
                key=f"journey_text_{idx}",
            )
            step["description"] = st.text_input(
                "Description",
                value=step.get("description", "wait"),
                key=f"journey_desc_{idx}",
            )

    with remove_col:
        if st.button("🗑️", key=f"journey_remove_{idx}"):
            st.session_state.journey_steps.pop(idx)
            st.rerun()

    return step


def _urls_to_journey_step_dicts(urls: list[str]) -> list[_JourneyStepDict]:
    """Convert a list of URLs into goto + capture journey step dicts."""
    steps: list[_JourneyStepDict] = []
    for url in urls:
        steps.append(
            {
                "action": "goto",
                "url": url,
                "selector": "",
                "text": "",
                "label": "",
                "description": f"Navigate to {url}",
            }
        )
        steps.append(
            {
                "action": "capture",
                "url": "",
                "selector": "",
                "text": "",
                "label": url,
                "description": f"Capture {url}",
            }
        )
    return steps


def _dict_to_journey_step(d: _JourneyStepDict) -> JourneyStep:
    """Convert a dict from session state into a JourneyStep dataclass."""
    from src.journey_scraper import JourneyStep

    # Map UI action names to JourneyStep action names
    action_map = {
        "goto": "navigate",
        "click": "click",
        "fill": "fill",
        "capture": "capture",
        "wait": "wait",
    }
    action = action_map.get(d.get("action", "goto"), d.get("action", ""))

    return JourneyStep(
        action=action,
        url=d.get("url"),
        selector=d.get("selector"),
        text=d.get("text"),
        description=d.get("description", ""),
    )


# ---------------------------------------------------------------------------
# Sidebar configuration panel
# ---------------------------------------------------------------------------


class SidebarConfig:
    """Renders the configuration sidebar and returns the selected values."""

    @staticmethod
    def render() -> dict[str, str]:
        """Render sidebar and return provider configuration."""
        st.sidebar.title("Configuration")
        provider_labels = {
            "ollama": "Ollama (local)",
            "lm-studio": "LM Studio (local)",
            "openai-local": "OpenAI-Compatible (local)",
            "openai": "OpenAI (cloud)",
        }
        provider_options = ("ollama", "lm-studio", "openai-local", "openai")

        def _format_provider(value: str) -> str:
            return provider_labels[value]

        provider = cast(
            str,
            st.sidebar.selectbox(
                "LLM Provider",
                provider_options,
                format_func=_format_provider,
            ),
        )
        return {"provider": provider}


# ---------------------------------------------------------------------------
# Requirements input panel
# ---------------------------------------------------------------------------


class RequirementsInput:
    """Renders the requirements input section."""

    # Baseline preset for reproducible debugging runs.
    BASELINE_STARTING_URL = "https://automationexercise.com/"
    BASELINE_ADDITIONAL_URLS = ""
    BASELINE_REQUIREMENTS: str = """## User Story
As a shopper on automationexercise.com, I want to browse products by category, add items to my cart, review the cart contents, and proceed to checkout so that I can complete a purchase.

## Acceptance Criteria
1. Navigate to the home page and verify the page loads successfully with product categories visible
2. Click on the "Dress" category link and verify the category products page displays a list of products
3. On the category page, click "Add to cart" on a product and verify an "Add to cart confirmation popup" appears
4. Close the confirmation popup by clicking "Continue Shopping" and verify I remain on the category page
5. Click the "View Cart" link in the header navigation and verify the cart page loads showing a table of added items
6. On the cart page, verify the product name, price, and quantity are displayed correctly in the cart table
7. Click the "Proceed to checkout" button on the cart page and verify the checkout page loads with order summary visible
8. On the checkout page, verify I am logged in automatically or prompted to login if not already authenticated

(Total: 8 criteria)
"""

    @staticmethod
    def render(base_url: str, urls_input: str) -> tuple[str, str, str, str]:
        """Render requirements input and return (input_mode, raw_text, base_url, urls_input)."""
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

        with col2:
            st.info(
                "Primary workflow:\n"
                "1. Generate a placeholder-based skeleton.\n"
                "2. Scrape the required pages.\n"
                "3. Resolve placeholders into real locators.\n"
                "4. Save the final Python test file."
            )
            st.caption("The intelligent pipeline is now the only generation path in this UI.")

        return input_mode, raw_requirements, base_url, urls_input


# ---------------------------------------------------------------------------
# Results display panel
# ---------------------------------------------------------------------------


class ResultsPanel:
    """Renders the pipeline results section."""

    @staticmethod
    def render_tabs(results: str, skeleton: str, saved_path: str, manifest_path: str) -> None:
        """Render the final code and skeleton tabs."""
        results_tab, skeleton_tab, scrape_tab = st.tabs(["Final Code", "Skeleton", "Scrape Summary"])

        with results_tab:
            st.code(results, language="python")
            if saved_path:
                st.success(f"Saved to: {saved_path}")
            if manifest_path:
                st.caption(f"Manifest: {manifest_path}")
            st.download_button(
                label="Download Final Test Script",
                data=results,
                file_name="generated_test.py",
                mime="text/x-python",
            )

        with skeleton_tab:
            st.code(skeleton, language="python")

        with scrape_tab:
            st.write("Pages scraped:")
            urls = st.session_state.get("pipeline_urls", [])
            scraped_pages = st.session_state.get("pipeline_scraped_pages", {})
            if urls:
                for url in urls:
                    element_count = len(scraped_pages.get(url, []))
                    st.write(f"- {url} ({element_count} elements)")
            else:
                st.write("- No URLs were available to scrape.")

            unresolved = st.session_state.get("pipeline_unresolved", [])
            if unresolved:
                st.warning("Some placeholders were unresolved and were converted into explicit pytest skips.")
                for unresolved_ph in unresolved:
                    st.code(unresolved_ph, language="python")

    @staticmethod
    def render_run_section() -> None:
        """Render the 'Run Generated Tests' buttons."""
        st.divider()
        st.subheader("Run Generated Tests")
        run_col, rerun_col = st.columns(2)
        saved_path = st.session_state.get("pipeline_saved_path", "")

        with run_col:
            if st.button("Run Generated Tests", disabled=not bool(saved_path)):
                _handle_run_tests()

        with rerun_col:
            previous_run_result = st.session_state.get("pipeline_run_result")
            rerun_disabled = not bool(saved_path) or previous_run_result is None
            if st.button("Re-run Failed Only", disabled=rerun_disabled):
                _handle_rerun_failed()


def _handle_run_tests() -> None:
    """Handle the 'Run Generated Tests' button click."""
    from src.pipeline_run_service import PipelineRunService

    try:
        with st.spinner("Running generated tests with pytest. This can take a couple of minutes..."):
            execution_result = PipelineRunService().run_saved_test(st.session_state.pipeline_saved_path)
            st.session_state.pipeline_run_result = execution_result.run_result
            st.session_state.pipeline_run_output = execution_result.display_output
            st.session_state.pipeline_run_command = " ".join(execution_result.command)
            st.session_state.pipeline_run_return_code = execution_result.return_code
            _store_run_report()
    except Exception as exc:
        st.session_state.pipeline_error = f"Failed to run generated tests: {exc}"


def _handle_rerun_failed() -> None:
    """Handle the 'Re-run Failed Only' button click."""
    from src.pipeline_run_service import PipelineRunService

    previous_run_result = st.session_state.pipeline_run_result
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
            _store_run_report()
    except Exception as exc:
        st.session_state.pipeline_error = f"Failed to rerun generated tests: {exc}"


def _store_run_report() -> None:
    """Build and store the report bundle after a test run."""
    from src.ui_pipeline import PipelineSessionState, build_report_bundle, store_report_bundle

    session = PipelineSessionState({str(k): v for k, v in st.session_state.items()})
    bundle = build_report_bundle(
        criteria_text=st.session_state.pipeline_criteria,
        generated_code=st.session_state.pipeline_results,
        run_result=st.session_state.pipeline_run_result,
        saved_path=st.session_state.pipeline_saved_path,
    )
    store_report_bundle(bundle, session)
    # Sync back to st.session_state
    for key, value in session._state.items():
        if key.startswith("pipeline_"):
            st.session_state[key] = value


# ---------------------------------------------------------------------------
# Run results display (includes AI-023 locator repair buttons)
# ---------------------------------------------------------------------------


class RunResultsDisplay:
    """Renders the test run results with failure classification and repair buttons."""

    @staticmethod
    def render(run_result: RunResult) -> None:
        """Display run metrics, coverage, results table with repair buttons, and downloads."""
        if st.session_state.get("pipeline_run_command"):
            st.caption(f"Command: {st.session_state.pipeline_run_command}")

        if run_result.errors > 0:
            st.error("Pytest hit a collection or import error before the generated tests could run.")

        metric_cols = st.columns(5)
        metric_cols[0].metric("Total", run_result.total)
        metric_cols[1].metric("Passed", run_result.passed)
        metric_cols[2].metric("Failed", run_result.failed)
        metric_cols[3].metric("Skipped", run_result.skipped)
        metric_cols[4].metric("Errors", run_result.errors)

        # Coverage table
        criteria_lines = [line.strip() for line in st.session_state.pipeline_criteria.splitlines() if line.strip()]
        coverage_analysis = build_coverage_analysis(criteria_lines, st.session_state.pipeline_results)
        coverage_rows = build_coverage_display_rows(coverage_analysis["requirements"], run_result.results)
        if coverage_rows:
            st.dataframe([row.to_dict() for row in coverage_rows], width="stretch")

        # Results table with repair buttons
        _render_results_table(run_result.results)

        # Repair panel (shown after user clicks repair button)
        _render_repair_panel()

        # Pytest output
        if st.session_state.get("pipeline_run_output"):
            with st.expander("Pytest Output", expanded=run_result.errors > 0):
                st.code(st.session_state.pipeline_run_output, language="text")

        # Download buttons
        RenderDownloads.render()


def _render_results_table(results: list[TestResult]) -> None:
    """Render per-test results as a table with repair buttons for locator failures."""
    for result in results:
        status_icon = "✅" if result.status == "passed" else ("❌" if result.status == "failed" else "⏭️")
        row_col1, row_col2, row_col3 = st.columns([0.05, 3, 0.5])

        with row_col1:
            st.write(status_icon)
        with row_col2:
            st.write(f"**{result.name}**")
            if result.error_message:
                st.caption(result.error_message[:200] + ("..." if len(result.error_message) > 200 else ""))
        with row_col3:
            st.caption(f"{result.duration:.2f}s")

        # AI-023: Show repair button for locator failures
        if result.status == "failed" and result.error_message:
            detail = classify_failure(result.error_message)
            if detail.category in (FailureCategory.LOCATOR_TIMEOUT, FailureCategory.STRICT_VIOLATION):
                locator_label = detail.raw_locator if detail.raw_locator else "unknown locator"
                if st.button(
                    f"🔧 Fix locator: `{locator_label}`",
                    key=f"repair_{result.name}",
                    help="Open a browser to click the correct element",
                ):
                    st.session_state.repair_target = detail
                    st.session_state.repair_status = "waiting"
                    st.session_state.repair_test_name = result.name
                    st.session_state.repair_test_file = result.file_path
                    st.rerun()
            elif detail.category == FailureCategory.ASSERTION_FAILURE:
                st.caption("ℹ️ Assertion failure — the element was found but page content was unexpected.")
            elif detail.category == FailureCategory.NAVIGATION_ERROR:
                st.caption("ℹ️ Navigation error — check the URL and network connectivity.")


def _render_repair_panel() -> None:
    """Render the locator repair panel when in repair mode."""
    repair_status = st.session_state.get("repair_status")

    if repair_status == "waiting":
        _render_repair_waiting_panel()
    elif repair_status == "browser_requested":
        _render_repair_browser_session()
    elif repair_status in ("patched", "error"):
        _render_repair_result_panel()


def _render_repair_waiting_panel() -> None:
    """Show the 'waiting' repair panel with explanation and action buttons."""
    detail = st.session_state.get("repair_target")
    test_file = st.session_state.get("repair_test_file", "unknown")

    st.divider()
    st.subheader("🔧 Locator Repair Mode")

    locator_label = detail.raw_locator if detail and detail.raw_locator else "unknown"
    st.write(f"**Failed locator:** `{locator_label}`")
    st.write(f"**Test file:** `{test_file}`")
    st.write(f"**Error:** {detail.error_message[:300] if detail else 'Unknown'}")

    st.info(
        "The browser will open at the page where this test got stuck. "
        "Click the element you want to use as the locator. "
        "The test file will be updated automatically."
    )

    fix_col, cancel_col = st.columns([1, 1])
    with fix_col:
        if st.button("🌐 Open browser and fix locator", type="primary"):
            st.session_state.repair_status = "browser_requested"
            st.rerun()
    with cancel_col:
        if st.button("Cancel"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            st.rerun()


def _render_repair_browser_session() -> None:
    """Run the headed browser codegen session and apply the patch."""
    from src.locator_repair import LocatorPatch, apply_patch_to_file

    detail = st.session_state.get("repair_target")
    base_url = st.session_state.get("base_url", "")
    failure_url = detail.failure_url if detail and detail.failure_url else base_url

    if not failure_url:
        st.session_state.repair_status = "error"
        st.session_state.repair_message = "❌ No URL available for browser session."
        st.rerun()

    with st.spinner(f"⏳ Browser is opening at `{failure_url}` — click the element you want to use..."):
        replacement = run_codegen_session(failure_url, timeout_seconds=120)

    if replacement:
        patch = LocatorPatch(
            original_locator=detail.raw_locator if detail and detail.raw_locator else "",
            repaired_locator=replacement,
            line_number=detail.line_number if detail and detail.line_number else 1,
            test_file=st.session_state.get("repair_test_file", st.session_state.get("pipeline_saved_path", "")),
        )
        try:
            apply_patch_to_file(patch)
            st.session_state.repair_status = "patched"
            st.session_state.repair_message = (
                f"✅ Locator patched: `{replacement}`\n"
                f"Changed line(s) in `{patch.test_file}`\n"
                "Click **▶️ Run Generated Tests** to verify the fix."
            )
        except Exception as exc:
            st.session_state.repair_status = "error"
            st.session_state.repair_message = f"❌ Could not patch: {exc}"
    else:
        st.session_state.repair_status = "error"
        st.session_state.repair_message = "❌ No locator captured. The browser may have timed out or been closed."

    st.rerun()


def _render_repair_result_panel() -> None:
    """Show the repair result (success or error) with actions."""
    st.divider()
    st.subheader("🔧 Locator Repair Result")

    message = st.session_state.get("repair_message", "")
    status = st.session_state.get("repair_status")

    if status == "patched":
        st.success(message)
    else:
        st.error(message)

    # Show updated test code if patched
    if status == "patched":
        test_file = st.session_state.get("repair_test_file", "")
        if test_file and Path(test_file).exists():
            with st.expander("Updated test file", expanded=True):
                st.code(Path(test_file).read_text(encoding="utf-8"), language="python")

    re_run_col, reset_col = st.columns([1, 1])
    with re_run_col:
        if st.button("▶️ Run Generated Tests", disabled=(status != "patched"), type="primary"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            _handle_run_tests()
    with reset_col:
        if st.button("Done"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            st.session_state.repair_message = None
            st.rerun()


def run_codegen_session(url: str, timeout_seconds: int = 120) -> str | None:
    """Launch headed Playwright codegen and capture the first locator from the recorded script.

    Args:
        url: URL to navigate to.
        timeout_seconds: Maximum time to wait for a click.

    Returns:
        The locator string captured from the clicked element, or None.
    """
    import re
    import subprocess
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/tmp/repair_locator_{timestamp}.py"

    proc = subprocess.Popen(
        ["playwright", "codegen", "--output", output_file, url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        return None

    if not Path(output_file).exists():
        return None

    content = Path(output_file).read_text(encoding="utf-8")
    Path(output_file).unlink(missing_ok=True)

    # Extract first locator string from the generated script
    # Matches: .locator("..."), .get_by_test_id("..."), .get_by_role("...", name="...")
    locator_pattern = re.compile(
        r'\.(?:locator|get_by_test_id|get_by_label|get_by_text|get_by_title|get_by_placeholder)\(\s*["\']([^"\']+)["\']',
    )
    match = locator_pattern.search(content)
    if match:
        return match.group(1)

    # For get_by_role with name= keyword, extract the selector expression
    role_pattern = re.compile(r'\.get_by_role\(\s*["\']([^"\']+)["\'].*?name=\s*["\']([^"\']+)["\']')
    role_match = role_pattern.search(content)
    if role_match:
        role = role_match.group(1)
        name = role_match.group(2)
        return f"get_by_role('{role}', name='{name}')"

    return None


# ---------------------------------------------------------------------------
# Download buttons
# ---------------------------------------------------------------------------


class RenderDownloads:
    """Render report download buttons."""

    @staticmethod
    def render() -> None:
        download_cols = st.columns(4)
        from src.ui_pipeline import safe_read_text

        download_cols[0].download_button(
            label="Download Manifest",
            data=safe_read_text(st.session_state.get("pipeline_manifest_path", "")),
            file_name="scrape_manifest.json",
            mime="application/json",
            disabled=not bool(st.session_state.get("pipeline_manifest_path")),
        )
        download_cols[1].download_button(
            label="Download Local Report",
            data=st.session_state.get("pipeline_local_report", ""),
            file_name="report_local.md",
            mime="text/markdown",
            disabled=not bool(st.session_state.get("pipeline_local_report")),
        )
        download_cols[2].download_button(
            label="Download Jira Report",
            data=st.session_state.get("pipeline_jira_report", ""),
            file_name="report_jira.md",
            mime="text/markdown",
            disabled=not bool(st.session_state.get("pipeline_jira_report")),
        )
        download_cols[3].download_button(
            label="Download HTML Report",
            data=st.session_state.get("pipeline_html_report", ""),
            file_name="report.html",
            mime="text/html",
            disabled=not bool(st.session_state.get("pipeline_html_report")),
        )

        # Report paths
        if st.session_state.get("pipeline_local_report_path"):
            st.caption(f"Local report: {st.session_state.pipeline_local_report_path}")
        if st.session_state.get("pipeline_jira_report_path"):
            st.caption(f"Jira report: {st.session_state.pipeline_jira_report_path}")
        if st.session_state.get("pipeline_html_report_path"):
            st.caption(f"HTML report: {st.session_state.pipeline_html_report_path}")


# ---------------------------------------------------------------------------
# Evidence viewer
# ---------------------------------------------------------------------------


class EvidenceViewer:
    """Renders the evidence viewer section."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def render(self) -> None:
        st.divider()
        st.subheader("Evidence Viewer")

        from src.ui_pipeline import find_all_evidence_dirs, find_evidence_sidecars

        sidecars = find_evidence_sidecars(self.base_dir)
        evidence_dirs = find_all_evidence_dirs(self.base_dir)

        if not self.base_dir.exists() or not sidecars:
            st.info(
                "No evidence sidecars found yet. Run generated tests to produce "
                "`generated_tests/test_xxx/evidence/*.evidence.json`."
            )
            return

        evidence_tabs = st.tabs(["Annotated Screenshot", "Gantt Timeline", "Coverage Heat Map"])

        with evidence_tabs[0]:
            self._render_annotated_screenshot(sidecars)

        with evidence_tabs[1]:
            self._render_gantt_timeline(evidence_dirs)

        with evidence_tabs[2]:
            self._render_coverage_heatmap(evidence_dirs)

        st.divider()
        self._render_suite_heatmap(sidecars, evidence_dirs)

    def _render_annotated_screenshot(self, sidecars: list[Path]) -> None:
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
            sidecar_path=selected,
            view_mode=view_mode,  # type: ignore[arg-type]
            title=selected.stem,
        )
        components.html(html, height=900, scrolling=True)

    def _render_gantt_timeline(self, evidence_dirs: list[Path]) -> None:
        from src.ui_pipeline import find_sidecar_for_test

        entries = load_gantt_entries(evidence_dirs[0] if evidence_dirs else Path("."))
        if not entries:
            st.info("No Gantt data yet. Run generated tests to produce `.evidence.json` sidecars.")
            return

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
            condition_meta: dict[str, dict[str, str]] = {}
            if st.session_state.get("test_plan"):
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
            sidecar_path = find_sidecar_for_test(self.base_dir, selected_test.test_name)
            if sidecar_path is None:
                st.warning(f"Sidecar not found for {selected_test.test_name}")
            else:
                sidecar = safe_read_sidecar(sidecar_path)
                if sidecar:
                    self._render_sidecar_details(sidecar)

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

    def _render_sidecar_details(self, sidecar: dict[str, Any]) -> None:
        """Render detailed view of a single sidecar."""
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

    def _render_coverage_heatmap(self, evidence_dirs: list[Path]) -> None:
        # Feed test plan confirmation state into heatmap
        test_plan_state: dict[str, list[str]] | None = None
        if st.session_state.get("test_plan"):
            test_plan_state = {"confirmed_ids": list(st.session_state.test_plan.reviewed_ids)}

        stories = build_story_confidence(
            evidence_dirs[0] if evidence_dirs else Path("."),
            test_plan_state=test_plan_state,
        )
        if not stories:
            st.info("No heat map data yet. Run generated tests to produce `.evidence.json` sidecars.")
            return

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

    def _render_suite_heatmap(self, sidecars: list[Path], evidence_dirs: list[Path]) -> None:
        st.subheader("Suite Heatmap (Coverage Overview)")

        # Build URL options from all sidecars by using the `navigate` steps.
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
            return

        selected_url = st.selectbox("Select page URL", options=url_list)
        suite_html = generate_suite_heatmap(
            evidence_dir=evidence_dirs[0] if evidence_dirs else Path("."),
            page_url=selected_url,
        )
        components.html(suite_html, height=850, scrolling=True)
