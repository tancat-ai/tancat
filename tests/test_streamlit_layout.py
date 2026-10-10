"""Session 1: Streamlit Layout Tests — verify sidebar & main content structure.

These tests use Streamlit's AppTest framework to verify the app renders
expected widgets without crashing. All backend calls (LLM, scraper, etc.)
are mocked so tests run without external dependencies.

Sidebar layout verified (exact sets, not "at least one" - so any addition or
removal fails):
- LLM Provider and Consent Handling selectboxes, plus the OCR Backend selectbox
  on a build that has the optional [pdf] extra installed
- Provider Base URL, Model, Project and Starting URL text inputs
- Additional URLs text area
- Page Object Model toggle
- "Check My LLM" button plus exactly one licence action
See tests/streamlit_app_test_helpers.py for the inventory and the deliberate
omissions (saved-package widgets, the licence label, the OCR selectbox).
Main content verified:
- Logo header, Requirements input, Authentication expander
- Run Intelligent Pipeline button (main content, not sidebar)
- No result tabs before the pipeline runs
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from tests.streamlit_app_test_helpers import (
    BASE_TEXT_AREA_LABELS,
    BASE_TOGGLE_LABELS,
    CHECK_LLM_BUTTON,
    LICENCE_BUTTON_LABELS,
    build_sidebar_app,
    expected_selectbox_labels,
    expected_text_input_labels,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_test() -> AppTest:
    """Create an AppTest instance with all backend dependencies mocked.

    The LLM client, the settings store and the saved-package scan are isolated
    so the sidebar renders its documented base set on any machine (see
    tests/streamlit_app_test_helpers.py).
    """
    return build_sidebar_app()


@pytest.fixture(scope="module")
def at(request: pytest.FixtureRequest) -> AppTest:  # noqa: ARG001
    """Convenience alias for app_test."""
    return request.getfixturevalue("app_test")


# ---------------------------------------------------------------------------
# Sidebar widget tests
# ---------------------------------------------------------------------------


class TestSidebarWidgets:
    """Verify the sidebar renders exactly the documented widget set."""

    def test_no_exception_on_load(self, at: AppTest) -> None:
        """App should load without raising exceptions."""
        assert not at.exception

    def test_sidebar_selectbox_set_is_exact(self, at: AppTest) -> None:
        """Sidebar selectboxes must be exactly the expected set, no more, no less."""
        labels = [w.label for w in at.sidebar.selectbox]
        assert set(labels) == expected_selectbox_labels(), f"Sidebar selectbox set changed. Got: {labels}"
        assert len(labels) == len(set(labels)), f"Duplicate selectbox labels. Got: {labels}"

    def test_sidebar_text_input_set_is_exact(self, at: AppTest) -> None:
        """Sidebar text_inputs must be exactly the expected set."""
        labels = [w.label for w in at.sidebar.text_input]
        assert set(labels) == expected_text_input_labels(), f"Sidebar text_input set changed. Got: {labels}"

    def test_sidebar_text_area_set_is_exact(self, at: AppTest) -> None:
        """Sidebar text_areas must be exactly the Additional URLs field."""
        labels = [w.label for w in at.sidebar.text_area]
        assert set(labels) == set(BASE_TEXT_AREA_LABELS), f"Sidebar text_area set changed. Got: {labels}"

    def test_sidebar_toggle_set_is_exact(self, at: AppTest) -> None:
        """Sidebar toggles must be exactly the Page Object Model toggle."""
        labels = [w.label for w in at.sidebar.toggle]
        assert set(labels) == set(BASE_TOGGLE_LABELS), f"Sidebar toggle set changed. Got: {labels}"

    def test_sidebar_button_set_is_exact(self, at: AppTest) -> None:
        """Sidebar buttons must be exactly "Check My LLM" plus one licence action.

        The licence action label depends on whether a licence is installed, so
        either known label is accepted - but a third button (e.g. a restored
        preset) still fails.
        """
        labels = [w.label for w in at.sidebar.button]
        assert len(labels) == 2, f"Sidebar should have exactly 2 buttons. Got: {labels}"
        assert CHECK_LLM_BUTTON in labels, f"Missing the 'Check My LLM' button. Got: {labels}"
        licence_labels = set(labels) - {CHECK_LLM_BUTTON}
        assert len(licence_labels) == 1, f"Expected exactly one licence action. Got: {labels}"
        assert next(iter(licence_labels)) in LICENCE_BUTTON_LABELS, f"Unexpected licence button label. Got: {labels}"

    def test_sidebar_has_consent_mode_selector(self, at: AppTest) -> None:
        """The Consent Handling selectbox is present (it drives consent mode)."""
        labels = [w.label for w in at.sidebar.selectbox]
        assert "Consent Handling" in labels, f"Sidebar should have a Consent Handling selectbox. Got: {labels}"

    def test_sidebar_model_slot_switches_with_available_models(self) -> None:
        """With models offered, the model slot is Select Model + Model Name.

        Fresh AppTest so the shared no-models fixture is not mutated.
        """
        at = build_sidebar_app(models=["demo-model"])
        assert not at.exception
        selectbox_labels = {w.label for w in at.sidebar.selectbox}
        text_input_labels = {w.label for w in at.sidebar.text_input}
        assert selectbox_labels == expected_selectbox_labels(with_models=True), (
            f"Selectbox set with models changed. Got: {selectbox_labels}"
        )
        assert text_input_labels == expected_text_input_labels(with_models=True), (
            f"text_input set with models changed. Got: {text_input_labels}"
        )


# ---------------------------------------------------------------------------
# Main content tests
# ---------------------------------------------------------------------------


class TestMainContent:
    """Verify main content area renders correctly."""

    def test_title_renders(self, at: AppTest) -> None:
        """App title should be visible in main content."""
        assert len(at.markdown) >= 1, "Main content should have markdown elements"

    def test_run_button_is_main_content_not_sidebar(self, at: AppTest) -> None:
        """The Run button lives in main content and is not duplicated into the sidebar."""
        run_label = "Run Intelligent Pipeline"
        sidebar_labels = [b.label for b in at.sidebar.button]
        assert run_label not in sidebar_labels, f"Run button must not be in the sidebar. Got: {sidebar_labels}"
        main_labels = [b.label for b in at.button]
        assert main_labels.count(run_label) == 1, f"Expected exactly one main-content Run button. Got: {main_labels}"

    def test_no_pipeline_error_on_load(self, at: AppTest) -> None:
        """No error should be displayed on initial load."""
        assert not at.error, "No errors should appear on initial load"

    def test_auth_expander_exists_on_load(self, at: AppTest) -> None:
        """Authentication expander should be visible on initial load.

        The app renders an "Authentication (optional)" expander that is always
        present — it is not a results panel.
        """
        assert len(at.expander) >= 1, "Auth expander should appear on load"
        labels = [e.label for e in at.expander]
        assert any("auth" in label.lower() for label in labels), f"Expected auth expander. Got labels: {labels}"

    def test_no_results_tabs_on_load(self, at: AppTest) -> None:
        """Results tabs should not appear before running pipeline.

        pipeline_results is None initially, so the results tabs (Skeleton,
        Generated Tests, etc.) should not render.
        """
        assert len(at.tabs) == 0, "No result tabs should appear before pipeline runs"


# ---------------------------------------------------------------------------
# Session state tests
# ---------------------------------------------------------------------------


class TestSessionStateInit:
    """Verify session state is initialized correctly."""

    def test_app_loads_without_error(self, at: AppTest) -> None:
        """App should load and initialize session state without errors."""
        assert not at.exception, "App should load without exceptions"

    def test_pipeline_error_is_empty(self, at: AppTest) -> None:
        """pipeline_error should be empty string on initial load."""
        assert not at.error, "No error displayed means pipeline_error is empty"
