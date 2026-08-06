"""Sidebar configuration panel."""

from __future__ import annotations

from typing import Any, cast

import streamlit as st

from src.provider_config import PROVIDER_LABELS, SUPPORTED_PROVIDERS
from src.settings_store import DEFAULT_SETTINGS, load_setting, save_setting

# Keys whose settings are edited from this panel — kept in one place so
# streamlit_app.py and the panel never disagree on naming.
SETTING_POM_MODE = "pom_mode"
SETTING_CONSENT_MODE = "consent_mode"
SETTING_PROVIDER = "provider"
SETTING_MODEL_NAME = "model_name"
SETTING_WORKSPACE = "workspace"
# Last package loaded via the sidebar — auto-restored on fresh sessions so a
# page reload / reconnect (or a session reset) does not blank Run & Fix.
SETTING_LAST_PACKAGE = "last_package"
SETTING_OCR_BACKEND = "ocr_backend"
SETTING_JIRA_PROJECT_KEY = "jira_project_key"


def _saved_index(options: tuple[str, ...], stored_value: str, default: str) -> int:
    """Return the selectbox index for *stored_value* (falling back to *default*)."""
    if stored_value in options:
        return options.index(stored_value)
    if default in options:
        return options.index(default)
    return 0


class SidebarConfig:
    """Renders the configuration sidebar and returns the selected values."""

    @staticmethod
    def render() -> dict[str, Any]:
        """Render sidebar and return provider configuration.

        Returns a dict with:
        - provider: str — selected LLM provider key
        - pom_mode: bool — Page Object Model generation mode

        B-036 Phase 4: both values persist through the SettingsStore so
        choices survive app restarts.
        """
        st.sidebar.title("Configuration")
        provider_options = SUPPORTED_PROVIDERS

        def _format_provider(value: str) -> str:
            return PROVIDER_LABELS[value]

        stored_provider = cast(str, load_setting(SETTING_PROVIDER, ""))
        provider = cast(
            str,
            st.sidebar.selectbox(
                "LLM Provider",
                provider_options,
                format_func=_format_provider,
                index=_saved_index(provider_options, stored_provider, DEFAULT_SETTINGS["provider"]),
            ),
        )
        if provider != stored_provider:
            save_setting(SETTING_PROVIDER, provider)

        # AI-010 Phase 4: POM mode toggle
        if "pom_mode" not in st.session_state:
            st.session_state["pom_mode"] = bool(load_setting(SETTING_POM_MODE, False))

        st.sidebar.divider()
        st.sidebar.subheader("Test Structure")
        pom_mode = st.sidebar.toggle(
            "Page Object Model",
            value=st.session_state.pom_mode,
            help="Generate tests using Page Object Model classes with evidence-aware locators",
        )
        st.session_state.pom_mode = pom_mode
        if pom_mode != bool(load_setting(SETTING_POM_MODE, False)):
            save_setting(SETTING_POM_MODE, pom_mode)

        return {"provider": provider, "pom_mode": pom_mode}

    @staticmethod
    def render_settings() -> dict[str, Any]:
        """Render the persisted Settings panel (B-036 Phase 4).

        Shows app-level persisted settings (OCR backend, workspace) plus
        the RAG store "Learned Patterns" statistics from the B-036 Phase 3
        learning loop. Returns the settings that consumers read elsewhere:
        ocr_backend and workspace.
        """
        st.sidebar.divider()
        st.sidebar.subheader("Settings")

        with st.sidebar.expander("App Settings", expanded=False):
            stored_ocr = cast(str, load_setting(SETTING_OCR_BACKEND, "pymupdf"))
            ocr_backend = st.selectbox(
                "OCR Backend (document mode)",
                ["pymupdf", "unlimited-ocr"],
                index=0 if stored_ocr != "unlimited-ocr" else 1,
                help=(
                    "Backend used to parse PDFs in document mode. "
                    "pymupdf is fast and offline; unlimited-ocr needs a GPU."
                ),
                key="ocr_backend_setting",
            )
            if ocr_backend != stored_ocr:
                save_setting(SETTING_OCR_BACKEND, ocr_backend)

            stored_workspace = cast(str, load_setting(SETTING_WORKSPACE, "default"))
            workspace = st.text_input(
                "Workspace",
                value=stored_workspace,
                help="Isolates generated tests / evidence under a subdirectory. Applies immediately.",
                key="workspace_setting",
            )
            if workspace != stored_workspace:
                save_setting(SETTING_WORKSPACE, workspace)

        SidebarConfig._render_learned_patterns()

        return {"ocr_backend": ocr_backend, "workspace": workspace}

    @staticmethod
    def _render_learned_patterns() -> None:
        """Show RAG store statistics from the B-036 Phase 3 learning loop.

        Best-effort: a missing/unopenable store degrades to a short note
        instead of an error (same philosophy as always-on RAG).
        """
        try:
            from src.rag_bundled import store_stats

            stats = store_stats()
        except Exception:
            st.sidebar.caption("Learned Patterns: store unavailable (RAG off or not yet initialised).")
            return

        if not stats:
            st.sidebar.caption("Learned Patterns: no RAG store yet.")
            return

        learned = int(stats.get("learned", 0))
        golden = int(stats.get("golden", 0))
        docs = int(stats.get("doc", 0))
        total = int(stats.get("total", learned + golden + docs))

        st.sidebar.subheader("RAG Store")
        st.sidebar.caption(f"**Learned:** {learned} · **Golden:** {golden} · **Docs:** {docs} · **Total:** {total}")

        prune_key = "prune_learned_confirm"
        if learned and st.sidebar.button(
            "Prune learned patterns",
            type="secondary",
            help="Delete patterns learned from your own runs; golden patterns and docs stay.",
            key="prune_learned_button",
        ):
            st.session_state[prune_key] = True
        if st.session_state.get(prune_key, False):
            st.sidebar.caption("Click again to confirm pruning all learned patterns.")
            if st.sidebar.button("Yes — prune learned patterns", type="primary", key="prune_learned_confirm_btn"):
                try:
                    from src.rag_bundled import prune_learned

                    pruned = prune_learned()
                    st.sidebar.success(f"Pruned {pruned} learned pattern(s).")
                except Exception as exc:
                    st.sidebar.error(f"Prune failed: {exc}")
                st.session_state[prune_key] = False
