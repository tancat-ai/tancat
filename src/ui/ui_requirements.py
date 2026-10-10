"""Requirements input panel."""

from __future__ import annotations

import streamlit as st


class RequirementsInput:
    """Renders the requirements input section."""

    @staticmethod
    def render(base_url: str, urls_input: str) -> tuple[str, str, str, str]:
        """Render requirements input and return (input_mode, raw_text, base_url, urls_input)."""
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

        return input_mode, raw_requirements, base_url, urls_input
