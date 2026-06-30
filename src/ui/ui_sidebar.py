"""Sidebar configuration panel."""

from __future__ import annotations

from typing import Any, cast

import streamlit as st

from src.provider_config import PROVIDER_LABELS, SUPPORTED_PROVIDERS


class SidebarConfig:
    """Renders the configuration sidebar and returns the selected values."""

    @staticmethod
    def render() -> dict[str, Any]:
        """Render sidebar and return provider configuration.

        Returns a dict with:
        - provider: str — selected LLM provider key
        - pom_mode: bool — Page Object Model generation mode
        """
        st.sidebar.title("Configuration")
        provider_options = SUPPORTED_PROVIDERS

        def _format_provider(value: str) -> str:
            return PROVIDER_LABELS[value]

        provider = cast(
            str,
            st.sidebar.selectbox(
                "LLM Provider",
                provider_options,
                format_func=_format_provider,
            ),
        )

        # AI-010 Phase 4: POM mode toggle
        if "pom_mode" not in st.session_state:
            st.session_state["pom_mode"] = False

        st.sidebar.divider()
        st.sidebar.subheader("Test Structure")
        pom_mode = st.sidebar.toggle(
            "Page Object Model",
            value=st.session_state.pom_mode,
            help="Generate tests using Page Object Model classes with evidence-aware locators",
        )
        st.session_state.pom_mode = pom_mode

        return {"provider": provider, "pom_mode": pom_mode}
