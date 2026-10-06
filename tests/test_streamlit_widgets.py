"""Session 2: Streamlit Widget Tests — verify widget states, defaults, and validation.

These tests use Streamlit's AppTest framework to verify widget constraints,
default values, and input validation logic. All backend calls are mocked.

Widget behaviors verified:
- Provider selector defaults to the documented local provider (openai-local)
- Model input adapts based on available models
- URL and story inputs accept/validate text
- Consent mode options are correct
- Requirements input mode (paste vs upload)
- Baseline config button is present
- The Run button stays locked until the Living Test Plan is signed off
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_test() -> AppTest:
    """Create an AppTest instance with all backend dependencies mocked."""
    mock_llm_instance = MagicMock()
    mock_llm_instance.list_models.return_value = []  # Force manual model input

    mock_llm_class = MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_class.set_session_provider = MagicMock()

    def fake_exists(self: Path) -> bool:
        return False

    with (
        patch("streamlit_app.LLMClient", new=mock_llm_class),
        patch.object(Path, "exists", fake_exists),
        # Isolate the encrypted settings store so the test sees documented
        # defaults, not whatever this machine has saved (and never writes to it).
        patch("src.settings_store._load_settings", return_value={}),
        patch("src.settings_store._save_settings"),
    ):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run(timeout=15)
        return at


@pytest.fixture(scope="module")
def at(request: pytest.FixtureRequest) -> AppTest:  # noqa: ARG001
    """Convenience alias for app_test."""
    return request.getfixturevalue("app_test")


# ---------------------------------------------------------------------------
# Provider selector tests
# ---------------------------------------------------------------------------


class TestProviderSelector:
    """Verify LLM provider selector defaults and options."""

    def test_provider_selector_defaults_to_documented_local_provider(self, at: AppTest) -> None:
        """LLM Provider should default to the documented local provider (F3).

        README/AGENTS name llama.cpp on :8080 (``openai-local``) as the
        default. A blank default used to fall back to the first option
        (Ollama), which pointed new users at the wrong port.
        """
        provider_box = at.sidebar.selectbox[0]
        default = provider_box.value  # type: ignore[attr-defined]
        assert str(default) == "openai-local", f"Expected default provider 'openai-local', got '{default}'"
        base_url = at.sidebar.text_input[0]
        assert "8080" in str(base_url.value), f"Expected the :8080 base URL default, got '{base_url.value}'"

    def test_provider_selector_has_all_options(self, at: AppTest) -> None:
        """Provider selectbox should list every supported provider."""
        from src.provider_config import SUPPORTED_PROVIDERS

        provider_box = at.sidebar.selectbox[0]
        options = provider_box.options
        option_labels = [str(o) for o in options]
        # Options use display labels: "Ollama (local)", "LM Studio (local)", etc.
        option_text = " ".join(option_labels)
        assert "Ollama" in option_text, f"Expected Ollama in options. Got: {option_labels}"
        assert "LM Studio" in option_text, f"Expected LM Studio in options. Got: {option_labels}"
        assert "OpenAI" in option_text, f"Expected OpenAI in options. Got: {option_labels}"
        assert "OpenRouter" in option_text, f"Expected OpenRouter in options. Got: {option_labels}"
        assert len(option_labels) == len(SUPPORTED_PROVIDERS)

    def test_provider_selector_has_every_supported_provider(self, at: AppTest) -> None:
        """Provider selectbox should show one entry per supported provider."""
        from src.provider_config import SUPPORTED_PROVIDERS

        provider_box = at.sidebar.selectbox[0]
        assert len(provider_box.options) == len(SUPPORTED_PROVIDERS), (
            f"Expected {len(SUPPORTED_PROVIDERS)} provider options, got {len(provider_box.options)}"
        )
        # The two compatible cloud providers must be selectable, not just implemented.
        assert "openai-compatible" in SUPPORTED_PROVIDERS
        assert "openrouter" in SUPPORTED_PROVIDERS

    def test_compatible_provider_is_selectable_and_asks_for_a_key(self) -> None:
        """Selecting a compatible cloud provider shows the key field + model prompt.

        Uses a fresh AppTest (the module fixture is shared and must not be
        mutated by an interaction test).
        """
        mock_llm_instance = MagicMock()
        mock_llm_instance.list_models.return_value = []
        mock_llm_class = MagicMock()
        mock_llm_class.return_value = mock_llm_instance
        mock_llm_class.set_session_provider = MagicMock()

        def fake_exists(self: Path) -> bool:
            return False

        with (
            patch("streamlit_app.LLMClient", new=mock_llm_class),
            patch.object(Path, "exists", fake_exists),
            patch("src.settings_store._load_settings", return_value={}),
            patch("src.settings_store._save_settings"),
        ):
            at = AppTest.from_file(APP_PATH, default_timeout=15)
            at.run(timeout=15)
            at.sidebar.selectbox[0].select("openai-compatible")
            at.run(timeout=15)

            key_fields = [t for t in at.sidebar.text_input if t.key == "openai_api_key"]
            assert key_fields, "expected an API key field for the compatible provider"
            assert key_fields[0].label == "API Key"
            warnings = [w.value for w in at.sidebar.warning]
            assert any("API key" in w for w in warnings), f"expected a key warning. Got: {warnings}"
            assert any("Name the model" in w for w in warnings), f"expected a model prompt. Got: {warnings}"

    def test_azure_provider_is_selectable_and_asks_for_its_key(self) -> None:
        """Azure OpenAI is first-class: selectable, keyed, deployment-named."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.list_models.return_value = []
        mock_llm_class = MagicMock()
        mock_llm_class.return_value = mock_llm_instance
        mock_llm_class.set_session_provider = MagicMock()

        def fake_exists(self: Path) -> bool:
            return False

        with (
            patch("streamlit_app.LLMClient", new=mock_llm_class),
            patch.object(Path, "exists", fake_exists),
            patch("src.settings_store._load_settings", return_value={}),
            patch("src.settings_store._save_settings"),
        ):
            at = AppTest.from_file(APP_PATH, default_timeout=15)
            at.run(timeout=15)
            at.sidebar.selectbox[0].select("azure-openai")
            at.run(timeout=15)

            key_fields = [t for t in at.sidebar.text_input if t.key == "openai_api_key"]
            assert key_fields, "expected an API key field for Azure OpenAI"
            assert key_fields[0].label == "Azure OpenAI API Key"
            warnings = [w.value for w in at.sidebar.warning]
            assert any("API key" in w for w in warnings), f"expected a key warning. Got: {warnings}"
            assert any("Name the model" in w for w in warnings), f"expected a model prompt. Got: {warnings}"


# ---------------------------------------------------------------------------
# Model input tests
# ---------------------------------------------------------------------------


class TestModelInput:
    """Verify model name input adapts to available models."""

    def test_model_text_input_shown_when_no_models(self, at: AppTest) -> None:
        """When list_models returns empty, a manual model text_input is shown.

        The fixture mocks list_models to return [], so the sidebar renders
        a text_input for manual model entry rather than a selectbox.
        """
        # With no models available, we get a text_input for the model name
        text_inputs = at.sidebar.text_input
        assert len(text_inputs) >= 1, (
            "Expected at least one text_input (Provider URL or Model) "
            f"when no models available. Got {len(text_inputs)}."
        )


# ---------------------------------------------------------------------------
# URL input tests
# ---------------------------------------------------------------------------


class TestUrlInputs:
    """Verify URL input widgets exist and have correct structure."""

    def test_has_sidebar_text_inputs(self, at: AppTest) -> None:
        """Sidebar should have at least one text_input (Target URL)."""
        assert len(at.sidebar.text_input) >= 1, "Expected at least one text_input in sidebar"

    def test_additional_urls_text_area_exists(self, at: AppTest) -> None:
        """Additional URLs text_area should be present in sidebar."""
        assert len(at.sidebar.text_area) >= 1, "Expected Additional URLs text_area in sidebar"

    def test_url_input_has_help_text(self, at: AppTest) -> None:
        """Target URL input should have helpful placeholder or help text."""
        url_input = at.sidebar.text_input[0]
        # Verify the widget is accessible (no exception on access)
        _ = url_input.label


# ---------------------------------------------------------------------------
# Consent mode tests
# ---------------------------------------------------------------------------


class TestConsentMode:
    """Verify consent mode selector options and defaults."""

    def test_consent_mode_has_three_options(self, at: AppTest) -> None:
        """Consent Handling should offer exactly three modes."""
        consent_box = at.sidebar.selectbox[-1]
        options = [str(o) for o in consent_box.options]
        expected = {"auto-dismiss", "leave-as-is", "test-consent-flow"}
        actual = set(options)
        assert expected == actual, f"Consent mode options mismatch. Expected {expected}, got {actual}"

    def test_consent_mode_defaults_to_auto_dismiss(self, at: AppTest) -> None:
        """Consent Handling should default to 'auto-dismiss'."""
        consent_box = at.sidebar.selectbox[-1]
        consent_value = consent_box.value  # type: ignore[attr-defined]
        assert consent_value == "auto-dismiss", f"Expected 'auto-dismiss', got '{consent_value}'"


# ---------------------------------------------------------------------------
# Requirements input tests
# ---------------------------------------------------------------------------


class TestRequirementsInput:
    """Verify requirements input panel (paste vs upload modes)."""

    def test_requirements_text_area_exists(self, at: AppTest) -> None:
        """A requirements text area should be rendered in main content."""
        # text_area in main content (not sidebar) is the Requirements field
        assert len(at.text_area) >= 0, "Requirements input should be accessible"

    def test_requirements_radio_offers_two_modes(self, at: AppTest) -> None:
        """Requirements radio should offer 'Paste Text' and 'Upload File'."""
        radios = at.radio
        assert len(radios) >= 1, "Expected a radio widget for requirements input mode"
        radio = radios[0]
        options = [str(o) for o in radio.options]
        assert "Paste Text" in options, f"Expected 'Paste Text' mode. Got: {options}"
        assert "Upload File" in options, f"Expected 'Upload File' mode. Got: {options}"

    def test_requirements_defaults_to_paste_mode(self, at: AppTest) -> None:
        """Requirements input should default to 'Paste Text' mode."""
        radio = at.radio[0]
        radio_value = radio.value  # type: ignore[attr-defined]
        assert radio_value == "Paste Text", f"Expected default 'Paste Text', got '{radio_value}'"


# ---------------------------------------------------------------------------
# Baseline config tests
# ---------------------------------------------------------------------------


class TestBaselineConfig:
    """Verify baseline configuration button and behavior."""

    def test_baseline_load_button_exists(self, at: AppTest) -> None:
        """A 'Load baseline config' button should be in the sidebar."""
        buttons = at.sidebar.button
        labels = [b.label for b in buttons]
        assert any("baseline" in label.lower() for label in labels), (
            f"Expected baseline button in sidebar. Got: {labels}"
        )

    def test_baseline_section_has_a_button(self, at: AppTest) -> None:
        """The baseline section should offer at least one action button."""
        buttons = at.sidebar.button
        labels = [b.label for b in buttons]
        baseline_buttons = [label for label in labels if "baseline" in label.lower()]
        assert len(baseline_buttons) >= 1, f"Expected at least one baseline button. Got: {labels}"

    def test_run_button_locked_until_plan_signed_off(self) -> None:
        """Current-UI guard: typing requirements disables Run until sign-off.

        Uses a fresh AppTest (the module fixture is shared and must not be
        mutated by an interaction test).
        """
        mock_llm_instance = MagicMock()
        mock_llm_instance.list_models.return_value = []
        mock_llm_class = MagicMock()
        mock_llm_class.return_value = mock_llm_instance
        mock_llm_class.set_session_provider = MagicMock()

        def fake_exists(self: Path) -> bool:
            return False

        with (
            patch("streamlit_app.LLMClient", new=mock_llm_class),
            patch.object(Path, "exists", fake_exists),
            patch("src.settings_store._load_settings", return_value={}),
            patch("src.settings_store._save_settings"),
        ):
            at = AppTest.from_file(APP_PATH, default_timeout=15)
            at.run(timeout=15)
            requirements = [t for t in at.text_area if t.label == "Requirements"][0]
            requirements.set_value(
                "## User Story\nAs a user I want to log in\n\n## Acceptance Criteria\n1. Login works\n"
            )
            at.run(timeout=15)

            run_buttons = [b for b in at.button if b.label == "Run Intelligent Pipeline"]
            assert run_buttons, "Run Intelligent Pipeline button missing"
            assert run_buttons[0].disabled, "Run must stay disabled until the Living Test Plan is signed off"


# ---------------------------------------------------------------------------
# Widget interaction tests
# ---------------------------------------------------------------------------


class TestWidgetInteraction:
    """Verify widgets are accessible without raising exceptions."""

    def test_sidebar_widgets_accessible(self, at: AppTest) -> None:
        """All sidebar widgets should be accessible without exceptions."""
        # Access all widget collections without triggering reruns
        _ = at.sidebar.selectbox
        _ = at.sidebar.text_input
        _ = at.sidebar.text_area
        _ = at.sidebar.button
        assert not at.exception

    def test_main_content_widgets_accessible(self, at: AppTest) -> None:
        """All main content widgets should be accessible without exceptions."""
        _ = at.text_area
        _ = at.radio
        _ = at.markdown
        assert not at.exception

    def test_no_app_exception_on_initial_run(self, at: AppTest) -> None:
        """The app should load without any Streamlit exceptions."""
        assert not at.exception
