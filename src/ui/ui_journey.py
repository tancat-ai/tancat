"""Credential profiles and journey builder UI components."""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from src.journey_scraper import CredentialProfile, JourneyStep

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
