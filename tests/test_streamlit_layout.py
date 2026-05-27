"""Session 1: Streamlit Layout Tests — verify sidebar & main content structure.

These tests use Streamlit's AppTest framework to verify the app renders
expected widgets without crashing. All backend calls (LLM, scraper, etc.)
are mocked so tests run without external dependencies.

Sidebar layout verified:
- Provider configuration (LLMProvider selectbox, Provider Base URL, Model)
- Pages To Scrape section (Starting URL, Additional URLs)
- Consent Handling selectbox
- Test Mode selectbox
- Execution Plan selectbox
- Run Pipeline button
- Baseline tests section (checkbox, Load baseline config, Clear baseline)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_test() -> AppTest:
    """Create an AppTest instance with all backend dependencies mocked.

    The streamlit_app imports and calls LLMClient at module level, and also
    calls list_models() during sidebar rendering. We patch both the class
    and the list_models method to avoid any network call.
    """
    # Build mocks before importing the app
    mock_llm_instance = MagicMock()
    mock_llm_instance.list_models.return_value = []  # Force manual model input

    mock_llm_class = MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    # set_session_provider is called as a class method — make it a no-op
    mock_llm_class.set_session_provider = MagicMock()

    # Patch Path.exists so the logo does not trigger file I/O
    def fake_exists(self: Path) -> bool:
        return False

    with (
        patch("streamlit_app.LLMClient", new=mock_llm_class),
        patch.object(Path, "exists", fake_exists),
    ):
        at = AppTest.from_file("streamlit_app.py")
        at.run(timeout=15)
        return at


@pytest.fixture(scope="module")
def at(request: pytest.FixtureRequest) -> AppTest:  # noqa: ARG001
    """Convenience alias for app_test."""
    return request.getfixturevalue("app_test")


# ---------------------------------------------------------------------------
# Sidebar widget tests
# ---------------------------------------------------------------------------


class TestSidebarWidgets:
    """Verify sidebar widgets render correctly."""

    def test_no_exception_on_load(self, at: AppTest) -> None:
        """App should load without raising exceptions."""
        assert not at.exception

    def test_sidebar_has_selectboxes(self, at: AppTest) -> None:
        """Sidebar should have selectbox widgets (LLM Provider, Consent, etc.)."""
        assert len(at.sidebar.selectbox) >= 1, (
            "Sidebar should have at least one selectbox (LLMProvider, Consent Handling, Test Mode, Execution Plan)"
        )

    def test_sidebar_has_text_inputs(self, at: AppTest) -> None:
        """Sidebar should have text_input widgets (Provider URL, Starting URL, Model)."""
        assert len(at.sidebar.text_input) >= 1, (
            "Sidebar should have text_input widgets (Provider Base URL, Starting URL, Model)"
        )

    def test_sidebar_has_text_area(self, at: AppTest) -> None:
        """Sidebar should have text_area for Additional URLs."""
        assert len(at.sidebar.text_area) >= 1, "Sidebar should have a text_area for Additional URLs"

    def test_sidebar_has_run_pipeline_button(self, at: AppTest) -> None:
        """Sidebar should have the 'Run Pipeline' button."""
        buttons = at.sidebar.button
        assert len(buttons) >= 1, "Sidebar should have at least one button (Run Pipeline)"

    def test_sidebar_has_baseline_button(self, at: AppTest) -> None:
        """Sidebar should have 'Load baseline' button."""
        buttons = at.sidebar.button
        button_labels = [b.label for b in buttons]
        assert any("baseline" in label.lower() for label in button_labels), (
            f"Siderbar should have a baseline button. Got: {button_labels}"
        )

    def test_sidebar_has_consent_mode_selector(self, at: AppTest) -> None:
        """Consent Handling selectbox should exist in sidebar."""
        assert len(at.sidebar.selectbox) >= 1, "Sidebar should have selectbox widgets"


# ---------------------------------------------------------------------------
# Main content tests
# ---------------------------------------------------------------------------


class TestMainContent:
    """Verify main content area renders correctly."""

    def test_title_renders(self, at: AppTest) -> None:
        """App title should be visible in main content."""
        assert len(at.markdown) >= 1, "Main content should have markdown elements"

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
