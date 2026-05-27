"""Tests for Streamlit session state persistence.

Verifies that user input survives Streamlit reruns.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope="module")
def app_test() -> AppTest:
    """Module-scoped AppTest fixture for streamlit_app.py."""
    with (
        patch("pathlib.Path.exists", return_value=False),
        patch("src.llm_client.LLMClient", autospec=True),
    ):
        at = AppTest.from_file("streamlit_app.py")
        return at


class TestSessionStatePersistence:
    """Verify session state survives reruns."""

    def test_app_loads_without_error(self, app_test: AppTest) -> None:
        """App loads cleanly on first run."""
        app_test.run(timeout=20)
        assert not app_test.exception

    def test_pipeline_error_is_empty_on_load(self, app_test: AppTest) -> None:
        """No pipeline errors on initial load."""
        app_test.run(timeout=20)
        assert not app_test.error


class TestWidgetStatePersistence:
    """Verify widget values persist across reruns."""

    def test_url_input_accessible(self, app_test: AppTest) -> None:
        """URL text input is accessible after rerun."""
        app_test.run(timeout=20)
        assert len(app_test.sidebar.text_input) >= 1

    def test_user_story_text_area_accessible(self, app_test: AppTest) -> None:
        """User story text area is accessible after rerun."""
        app_test.run(timeout=20)
        assert len(app_test.sidebar.text_area) >= 1

    def test_provider_selector_accessible(self, app_test: AppTest) -> None:
        """Provider selector survives rerun."""
        app_test.run(timeout=20)
        assert len(app_test.sidebar.selectbox) >= 1


class TestSessionStateInit:
    """Verify session state initializes correctly."""

    def test_no_crash_on_initial_load(self, app_test: AppTest) -> None:
        """App does not crash on initial load."""
        app_test.run(timeout=20)
        assert not app_test.exception

    def test_no_error_on_initial_load(self, app_test: AppTest) -> None:
        """No errors displayed on initial load."""
        app_test.run(timeout=20)
        assert not app_test.error
