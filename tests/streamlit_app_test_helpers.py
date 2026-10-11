"""Shared harness and the exact expected sidebar inventory for the Streamlit shell.

The sidebar is assembled from three places:

- ``src/ui/ui_sidebar.py`` - provider, POM toggle, settings, licence & usage
- ``src/ui/ui_saved_packages.py`` - saved-package loader
- the top of ``streamlit_app.py`` - base URL, model, "Check My LLM", Pages To Scrape

The helpers pin the *exact* set of widgets the first render produces, so a
restored or newly added widget fails the layout tests instead of hiding behind
a ``>= 1`` count. That lenient style is exactly how the removed "Load baseline"
preset could have slipped back in. When this guard fails because you added a
widget on purpose, add that label to the expected set here - do not loosen the
assertion back to ``>= 1``.

Deliberately left OUT of the exact base inventory, with the reason:

1. ``OCR Backend (document mode)`` selectbox - rendered only when the optional
   ``[pdf]`` extra (pypdfium2 + pdfplumber) is installed. CI runs
   ``uv sync --frozen`` without extras and shows capability warnings instead.
   ``expected_selectbox_labels()`` follows ``pdf_reader_available()`` so the
   expectation stays exact for either build.
2. Saved-package widgets (``Load package`` selectbox, ``Run Project``,
   ``Load Package``) - rendered only when ``generated_tests/`` already holds
   packages, so they are data-driven, not layout. The builder patches
   ``find_existing_packages`` to ``[]`` to keep the base layout stable.
3. The licence action button - its label is ``Enter a licence`` before a
   licence is installed and ``Replace licence`` after. Either is accepted; the
   total sidebar button count stays exact.
4. The model input - the builder forces ``list_models() -> []``, so the slot is
   the ``Model`` text input. With models available the same slot is a
   ``Select Model`` selectbox plus a ``Model Name`` text input; that pair has
   its own test.

Note: the app's Run button (``Run Intelligent Pipeline``) is main content, not
sidebar, so it is asserted in the main-content tests, not in this inventory.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")

CHECK_LLM_BUTTON = "🩺 Check My LLM"
LICENCE_BUTTON_LABELS = ("Enter a licence", "Replace licence")
OCR_BACKEND_SELECTBOX = "OCR Backend (document mode)"

BASE_SELECTBOX_LABELS = frozenset({"LLM Provider", "Consent Handling"})
BASE_TEXT_AREA_LABELS = frozenset({"Additional URLs"})
BASE_TOGGLE_LABELS = frozenset({"Page Object Model"})


def expected_selectbox_labels(*, with_models: bool = False) -> set[str]:
    """The exact sidebar selectbox label set for this build.

    Follows ``pdf_reader_available()`` so a base install (no ``[pdf]`` extra)
    expects no OCR selectbox, while a full install expects it. ``with_models``
    adds the ``Select Model`` selectbox the sidebar renders when the provider
    offers a model list.
    """
    from src.pdf_ingest import pdf_reader_available

    labels = set(BASE_SELECTBOX_LABELS)
    if with_models:
        labels.add("Select Model")
    if pdf_reader_available():
        labels.add(OCR_BACKEND_SELECTBOX)
    return labels


def expected_text_input_labels(*, with_models: bool = False) -> set[str]:
    """The exact sidebar text_input label set for this build."""
    return {"Provider Base URL", "Model Name" if with_models else "Model", "Project", "Starting URL"}


def build_sidebar_app(models: list[str] | None = None) -> AppTest:
    """Return an AppTest of the app's first render with the sidebar isolated.

    ``models`` is what the mocked LLM client returns from ``list_models()``.
    The default (``[]``) drives the sidebar's "enter a model by hand" path.
    """
    mock_llm_instance = MagicMock()
    mock_llm_instance.list_models.return_value = list(models or [])

    mock_llm_class = MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_class.set_session_provider = MagicMock()

    def fake_path_exists(self: Path) -> bool:
        return False

    with (
        # Patch the SOURCE class. AppTest executes streamlit_app.py itself, and
        # the script does ``from src.llm_client import LLMClient``, so patching
        # ``streamlit_app.LLMClient`` (a separate import of the file) never
        # reaches the executed script - the sidebar would then hit whatever
        # LLM server the host has running and change the rendered widget set.
        patch("src.llm_client.LLMClient", new=mock_llm_class),
        patch.object(Path, "exists", fake_path_exists),
        # Never read or write this machine's saved settings.
        patch("src.settings_store._load_settings", return_value={}),
        patch("src.settings_store._save_settings"),
        # Saved-package widgets depend on generated_tests/ contents, not layout.
        patch("src.pipeline_artifact_manager.find_existing_packages", return_value=[]),
    ):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run(timeout=15)
    return at
