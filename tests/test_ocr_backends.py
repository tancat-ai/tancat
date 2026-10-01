"""Tests for OCR backend adapter (Phase 1i + AI-055 tiered CPU-first OCR).

Covers:
- PyMuPDFBackend: parse_pdf, parse_markdown, availability (tier 0)
- RapidOCRBackend: availability, parse_page (tier-1 CPU OCR — AI-055)
- AutoOcrBackend: tier-0 whole-doc + tier-1 CPU per-page (AI-055 default)
- UnlimitedOCRBackend: availability detection, lazy loading, error paths (tier 3)
- get_ocr_backend: factory with tiered selection, refusal behavior
- Integration with PipelineGraph._parse_document
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.agents.pipeline_graph import PipelineGraph
from src.ocr_backends import (
    AutoOcrBackend,
    OcrBackendUnavailableError,
    PyMuPDFBackend,
    RapidOCRBackend,
    UnlimitedOCRBackend,
    configured_ocr_backend_error,
    get_ocr_backend,
)

# ---------------------------------------------------------------------------
# PyMuPDF backend
# ---------------------------------------------------------------------------


class TestPyMuPDFBackend:
    """Default CPU backend."""

    def test_name(self) -> None:
        assert PyMuPDFBackend().name == "pymupdf"

    def test_available_is_true_when_the_pdf_library_is_present(self) -> None:
        with patch("src.ocr_backends._pdf_library_available", return_value=True):
            assert PyMuPDFBackend().available is True

    def test_available_is_false_without_the_pdf_library(self) -> None:
        with patch("src.ocr_backends._pdf_library_available", return_value=False):
            assert PyMuPDFBackend().available is False

    def test_parse_markdown_reads_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Title\n\nContent")
            f.flush()
            path = f.name

        try:
            backend = PyMuPDFBackend()
            text = backend.parse_markdown(path)
            assert "# Title" in text
            assert "Content" in text
        finally:
            Path(path).unlink(missing_ok=True)

    def test_parse_pdf_delegates_to_ingest_pdf(self) -> None:
        with patch("src.pdf_ingest.ingest_pdf") as mock_ingest:
            mock_chunk = MagicMock()
            mock_chunk.text = "PDF content"
            mock_ingest.return_value = [mock_chunk]

            backend = PyMuPDFBackend()
            text = backend.parse_pdf("/fake/doc.pdf")
            assert text == "PDF content"
            mock_ingest.assert_called_once()


# ---------------------------------------------------------------------------
# Unlimited OCR backend
# ---------------------------------------------------------------------------
# RapidOCR backend (tier-1 CPU OCR — AI-055)
# ---------------------------------------------------------------------------


class TestRapidOCRBackend:
    """Tier-1 CPU OCR backend (RapidOCR / PP-OCR, ONNX Runtime)."""

    def test_name(self) -> None:
        assert RapidOCRBackend().name == "rapidocr"

    def test_not_available_without_engine(self) -> None:
        """When ``rapidocr_onnxruntime`` can't be imported, reports unavailable."""
        # Make the import inside ``available`` raise ImportError.
        with patch.dict(sys.modules, {"rapidocr_onnxruntime": None}):
            backend = RapidOCRBackend()
            assert backend.available is False

    def test_available_when_engine_importable(self) -> None:
        """When the engine module and the PDF library are importable, reports available."""
        with (
            patch.dict(sys.modules, {"rapidocr_onnxruntime": MagicMock()}),
            patch("src.ocr_backends._pdf_library_available", return_value=True),
        ):
            backend = RapidOCRBackend()
            assert backend.available is True

    def test_available_is_false_without_the_pdf_library(self) -> None:
        """The engine alone is not enough: the page still needs PyMuPDF to render."""
        with (
            patch.dict(sys.modules, {"rapidocr_onnxruntime": MagicMock()}),
            patch("src.ocr_backends._pdf_library_available", return_value=False),
        ):
            backend = RapidOCRBackend()
            assert backend.engine_available is True
            assert backend.available is False

    def test_parse_page_out_of_range_returns_empty(self) -> None:
        """A page number outside the PDF's range returns empty (no crash)."""
        backend = RapidOCRBackend()
        with (
            patch.object(backend, "_ensure_engine", return_value=MagicMock()),
            patch("src.pdf_ingest.render_page_png", return_value=False),
        ):
            result = backend.parse_page("/fake/doc.pdf", 99)
        assert result == ""

    def test_result_to_text_boxes_texts_scores(self) -> None:
        """RapidOCR (boxes, texts, scores) tuple → joined text lines."""
        boxes = [[0, 0, 100, 20], [0, 30, 100, 50]]
        texts = ["Line one", "Line two"]
        scores = [0.9, 0.8]
        assert RapidOCRBackend._result_to_text((boxes, texts, scores)) == "Line one\nLine two"

    def test_result_to_text_empty(self) -> None:
        assert RapidOCRBackend._result_to_text(None) == ""
        assert RapidOCRBackend._result_to_text(()) == ""


# ---------------------------------------------------------------------------
# Auto backend (tier 0 whole-doc + tier-1 CPU per-page — AI-055 default)
# ---------------------------------------------------------------------------


class TestAutoOcrBackend:
    """The ``auto`` default tier: PyMuPDF whole-doc + CPU OCR image-only pages."""

    def test_parse_page_uses_cpu_ocr_when_available(self) -> None:
        """An image-only page on the auto tier hits the CPU OCR (tier 1)."""
        backend = AutoOcrBackend()
        with (
            patch(
                "src.ocr_backends.RapidOCRBackend.available",  # type: ignore[call-arg]
                new_callable=lambda: property(lambda self: True),
            ),
            patch("src.ocr_backends.RapidOCRBackend.parse_page", return_value="OCR'd page") as mock_parse,
        ):
            text = backend.parse_page("/fake/doc.pdf", 2)
            assert text == "OCR'd page"
            mock_parse.assert_called_once()

    def test_parse_page_empty_when_cpu_ocr_absent(self) -> None:
        """Graceful degradation: no CPU OCR engine → empty (page skipped)."""
        backend = AutoOcrBackend()
        with (
            patch(
                "src.ocr_backends.RapidOCRBackend.available",  # type: ignore[call-arg]
                new_callable=lambda: property(lambda self: False),
            ),
            patch("src.ocr_backends.RapidOCRBackend.parse_page") as mock_parse,
        ):
            text = backend.parse_page("/fake/doc.pdf", 2)
            assert text == ""
            mock_parse.assert_not_called()

    def test_parse_page_skip_log_names_the_engine_when_it_is_missing(self, caplog: pytest.LogCaptureFixture) -> None:
        """The skip line names the OCR engine when the PDF library is present."""
        backend = AutoOcrBackend()
        with (
            patch("src.ocr_backends._pdf_library_available", return_value=True),
            patch(
                "src.ocr_backends.RapidOCRBackend.engine_available",
                new_callable=PropertyMock,
                return_value=False,
            ),
            caplog.at_level(logging.DEBUG, logger="src.ocr_backends"),
        ):
            text = backend.parse_page("/fake/doc.pdf", 2)

        assert text == ""
        assert "CPU OCR engine (rapidocr_onnxruntime)" in caplog.text
        assert "PDF library" not in caplog.text

    def test_parse_page_skip_log_names_the_pdf_library_when_it_is_missing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The skip line blames PyMuPDF when that is the true cause, not rapidocr."""
        backend = AutoOcrBackend()
        with (
            patch("src.ocr_backends._pdf_library_available", return_value=False),
            caplog.at_level(logging.DEBUG, logger="src.ocr_backends"),
        ):
            text = backend.parse_page("/fake/doc.pdf", 2)

        assert text == ""
        assert "PDF library (PyMuPDF)" in caplog.text
        assert "rapidocr" not in caplog.text

    def test_parse_markdown_reads_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# T\n\nC")
            f.flush()
            path = f.name
        try:
            assert "# T" in AutoOcrBackend().parse_markdown(path)
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------


class TestUnlimitedOCRBackend:
    """GPU-accelerated vision model backend."""

    def test_name(self) -> None:
        assert UnlimitedOCRBackend().name == "unlimited-ocr"

    def test_not_available_without_cuda(self) -> None:
        """Without CUDA, the backend reports unavailable."""
        with patch("torch.cuda.is_available", return_value=False):
            backend = UnlimitedOCRBackend()
            assert backend.available is False

    def test_available_with_cuda(self) -> None:
        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("transformers.AutoModel", create=True),
            patch("transformers.AutoTokenizer", create=True),
            patch("src.ocr_backends._pdf_library_available", return_value=True),
        ):
            backend = UnlimitedOCRBackend()
            assert backend.available is True

    def test_available_is_false_without_the_pdf_library(self) -> None:
        """The GPU stack alone is not enough: the page still needs PyMuPDF to render."""
        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("transformers.AutoModel", create=True),
            patch("transformers.AutoTokenizer", create=True),
            patch("src.ocr_backends._pdf_library_available", return_value=False),
        ):
            backend = UnlimitedOCRBackend()
            assert backend.engine_available is True
            assert backend.available is False

    def test_ensure_model_raises_without_cuda(self) -> None:
        backend = UnlimitedOCRBackend()
        with patch("torch.cuda.is_available", return_value=False):
            with pytest.raises(RuntimeError, match="CUDA or ROCm"):
                backend._ensure_model()

    def test_ensure_model_loads_once(self) -> None:
        """Model is only loaded on first call — subsequent calls are no-ops."""
        backend = UnlimitedOCRBackend()

        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.is_bf16_supported", return_value=True),
            patch("torch.cuda.get_device_name", return_value="Test GPU"),
            patch("transformers.AutoTokenizer.from_pretrained") as mock_tok,
            patch("transformers.AutoModel.from_pretrained") as mock_model,
        ):
            mock_tok.return_value = MagicMock()
            mock_model.return_value = MagicMock()

            backend._ensure_model()
            backend._ensure_model()  # second call

            # Model loaded exactly once
            mock_tok.assert_called_once()
            mock_model.assert_called_once()

    def test_parse_markdown_reads_directly(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Doc\n\nBody")
            f.flush()
            path = f.name

        try:
            backend = UnlimitedOCRBackend()
            text = backend.parse_markdown(path)
            assert "# Doc" in text
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestGetOcrBackend:
    """get_ocr_backend() factory with settings store, env var and fallback."""

    @pytest.fixture(autouse=True)
    def _isolate_settings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep the settings store and the PDF library out of these tests.

        The factory tests exercise tier selection, so they take the PDF library
        as present; the two tests that need it absent patch it False themselves.
        """
        settings_file = tmp_path / "settings.enc"
        monkeypatch.setattr("src.settings_store._settings_path", lambda: settings_file)
        if settings_file.exists():
            settings_file.unlink()
        monkeypatch.setattr("src.ocr_backends._pdf_library_available", lambda: True)

    def test_default_is_auto(self) -> None:
        """AI-055: the default tier is ``auto`` (tier-0 whole-doc + tier-1 CPU OCR)."""
        with patch.dict(os.environ, {}, clear=True):
            backend = get_ocr_backend()
            assert isinstance(backend, AutoOcrBackend)

    def test_auto_name_and_available(self) -> None:
        backend = AutoOcrBackend()
        assert backend.name == "auto"
        # Tier 0 (PyMuPDF) is always on; tier-1 CPU OCR is best-effort.
        assert backend.available is True

    def test_auto_parse_pdf_delegates_to_pymupdf(self) -> None:
        """Whole-doc parsing on the auto tier goes through PyMuPDF (tier 0)."""
        with patch("src.ocr_backends.PyMuPDFBackend.parse_pdf", return_value="PDF text") as mock_parse:
            backend = AutoOcrBackend()
            text = backend.parse_pdf("/fake/doc.pdf")
            assert text == "PDF text"
            mock_parse.assert_called_once()

    def test_explicit_pymupdf_maps_to_auto(self) -> None:
        """Legacy ``pymupdf`` name maps to the auto tier."""
        backend = get_ocr_backend("pymupdf")
        assert isinstance(backend, AutoOcrBackend)

    def test_cpu_tier_returns_rapidocr(self) -> None:
        """``cpu`` forces the tier-1 CPU OCR (RapidOCR)."""
        with patch(
            "src.ocr_backends.RapidOCRBackend.engine_available",
            new_callable=PropertyMock,
            return_value=True,
        ):
            backend = get_ocr_backend("cpu")
            assert isinstance(backend, RapidOCRBackend)

    def test_rapidocr_alias_for_cpu(self) -> None:
        with patch(
            "src.ocr_backends.RapidOCRBackend.engine_available",
            new_callable=PropertyMock,
            return_value=True,
        ):
            backend = get_ocr_backend("rapidocr")
            assert isinstance(backend, RapidOCRBackend)

    def test_cpu_tier_without_engine_refuses(self) -> None:
        """CPU tier requested but engine absent → refuses, no silent downgrade."""
        with (
            patch(
                "src.ocr_backends.RapidOCRBackend.engine_available",
                new_callable=PropertyMock,
                return_value=False,
            ),
            pytest.raises(OcrBackendUnavailableError, match="rapidocr_onnxruntime"),
        ):
            get_ocr_backend("cpu")

    def test_high_accuracy_refuses_even_with_the_cpu_engine(self) -> None:
        """Tier 2 is not built in v1 → refused, never silently the CPU engine."""
        with (
            patch(
                "src.ocr_backends.RapidOCRBackend.available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            pytest.raises(OcrBackendUnavailableError, match="not built in v1"),
        ):
            get_ocr_backend("high-accuracy")

    def test_unlimited_ocr_without_gpu_refuses(self) -> None:
        """Tier-3 GPU VLM requested but no GPU → refuses, no silent CPU swap."""
        with (
            patch("torch.cuda.is_available", return_value=False),
            pytest.raises(OcrBackendUnavailableError, match="Unlimited-OCR"),
        ):
            get_ocr_backend("unlimited-ocr")

    def test_unlimited_ocr_with_gpu_returns_ocr_backend(self) -> None:
        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("transformers.AutoModel", create=True),
            patch("transformers.AutoTokenizer", create=True),
        ):
            backend = get_ocr_backend("unlimited-ocr")
            assert isinstance(backend, UnlimitedOCRBackend)

    def test_env_var_power_without_gpu_refuses_and_names_the_env(self) -> None:
        """OCR_BACKEND=power on a GPU-less build refuses; the line names the env var."""
        with (
            patch.dict(os.environ, {"OCR_BACKEND": "unlimited-ocr"}),
            patch("torch.cuda.is_available", return_value=False),
            pytest.raises(OcrBackendUnavailableError, match="OCR_BACKEND"),
        ):
            get_ocr_backend()

    def test_env_var_auto(self) -> None:
        with patch.dict(os.environ, {"OCR_BACKEND": "auto"}):
            backend = get_ocr_backend()
            assert isinstance(backend, AutoOcrBackend)

    def test_explicit_backend_overrides_env_var(self) -> None:
        with patch.dict(os.environ, {"OCR_BACKEND": "unlimited-ocr"}):
            backend = get_ocr_backend("pymupdf")
            assert isinstance(backend, AutoOcrBackend)  # explicit pymupdf → auto

    # ---- B-036 Phase 4: persisted setting wins; env is a fallback ----

    def test_persisted_setting_wins_over_env(self) -> None:
        from src.settings_store import save_setting

        save_setting("ocr_backend", "unlimited-ocr")
        with patch.dict(os.environ, {"OCR_BACKEND": "pymupdf"}):
            with (
                patch("torch.cuda.is_available", return_value=True),
                patch("transformers.AutoModel", create=True),
                patch("transformers.AutoTokenizer", create=True),
            ):
                backend = get_ocr_backend()
                assert isinstance(backend, UnlimitedOCRBackend)

    def test_env_is_fallback_when_setting_never_saved(self) -> None:
        with (
            patch.dict(os.environ, {"OCR_BACKEND": "unlimited-ocr"}),
            patch("torch.cuda.is_available", return_value=False),
            pytest.raises(OcrBackendUnavailableError, match="OCR_BACKEND"),
        ):
            get_ocr_backend()

    # ---- refusal: both routes, plus the UI helper ----

    def test_saved_power_without_gpu_refuses_and_names_the_setting(self) -> None:
        """A stale saved 'power' setting refuses; the line names the saved setting."""
        from src.settings_store import save_setting

        save_setting("ocr_backend", "power")
        with (
            patch("torch.cuda.is_available", return_value=False),
            pytest.raises(OcrBackendUnavailableError, match="saved setting"),
        ):
            get_ocr_backend()

    def test_unknown_backend_refuses(self) -> None:
        """An unrecognised explicit name is refused, not quietly re-mapped to auto."""
        with pytest.raises(OcrBackendUnavailableError, match="not recognised"):
            get_ocr_backend("banana")

    def test_configured_error_is_none_for_the_auto_default(self) -> None:
        """The documented default still resolves quietly - auto is best-effort by design."""
        with patch.dict(os.environ, {}, clear=True):
            assert configured_ocr_backend_error() is None

    def test_configured_error_names_the_env_route(self) -> None:
        """The UI helper returns the same refusal line the factory raises."""
        with (
            patch.dict(os.environ, {"OCR_BACKEND": "power"}, clear=True),
            patch("torch.cuda.is_available", return_value=False),
        ):
            line = configured_ocr_backend_error()

        assert line is not None
        assert "OCR_BACKEND" in line
        assert "Unlimited-OCR" in line
        assert "silently" in line

    def test_auto_still_resolves_but_reports_unavailable_without_fitz(self) -> None:
        """auto degrades by design, but its ``available`` now tells the truth."""
        with patch("src.ocr_backends._pdf_library_available", return_value=False):
            backend = get_ocr_backend("auto")
            assert isinstance(backend, AutoOcrBackend)
            assert backend.available is False

    def test_cpu_refusal_names_the_pdf_library_when_that_is_the_cause(self) -> None:
        """With the engine present but fitz absent, the line blames the PDF library."""
        with (
            patch.dict(sys.modules, {"rapidocr_onnxruntime": MagicMock()}),
            patch("src.ocr_backends._pdf_library_available", return_value=False),
            pytest.raises(OcrBackendUnavailableError, match="PyMuPDF"),
        ):
            get_ocr_backend("cpu")

    def test_persisted_backend_name_normalised(self) -> None:
        from src.settings_store import save_setting

        save_setting("ocr_backend", "UNLIMITED_OCR")  # alternate alias
        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("transformers.AutoModel", create=True),
            patch("transformers.AutoTokenizer", create=True),
        ):
            backend = get_ocr_backend()
            assert isinstance(backend, UnlimitedOCRBackend)


# ---------------------------------------------------------------------------
# Pipeline graph integration
# ---------------------------------------------------------------------------


class TestParseDocumentWithOcrBackend:
    """PipelineGraph._parse_document uses the OCR backend adapter."""

    @pytest.fixture
    def graph(self) -> PipelineGraph:
        from src.agents.pipeline_graph import PipelineGraph

        return PipelineGraph(client=None, enable_checkpoint=False)

    @pytest.mark.asyncio
    async def test_pdf_uses_ocr_backend(self, graph: PipelineGraph) -> None:
        """PDF parsing goes through page-aware ingestion (16b Phase 2)."""
        from src.rag_store import DocChunk

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False, encoding="utf-8") as f:
            f.write("%PDF-1.4\nfake pdf\n%%EOF")
            f.flush()
            path = f.name

        try:
            with (
                patch(
                    "src.pdf_ingest.ingest_pdf_page_aware",
                    return_value=[
                        DocChunk(text="OCR'd content from backend", source="spec.pdf", page=1, route="text"),
                    ],
                ) as mock_ingest,
                patch("src.ocr_backends.get_ocr_backend") as mock_backend,
            ):
                mock_ocr = MagicMock()
                mock_ocr.available.return_value = False
                mock_backend.return_value = mock_ocr

                from src.agents.pipeline_state import PipelineState

                state = PipelineState(
                    input_mode="document",
                    document_source=path,
                )
                result = await graph._parse_document(state)

                mock_ingest.assert_called_once()
                assert "OCR'd content" in result["raw_document_text"]
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_markdown_uses_ocr_backend(self, graph: PipelineGraph) -> None:
        """Markdown goes through OCR backend's parse_markdown."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test")
            f.flush()
            path = f.name

        try:
            from src.agents.pipeline_state import PipelineState

            state = PipelineState(
                input_mode="document",
                document_source=path,
            )
            result = await graph._parse_document(state)
            assert "# Test" in result["raw_document_text"]
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_backend_error_returns_error(self, graph: PipelineGraph) -> None:
        """Page-aware ingestion failure returns structured error (16b Phase 2)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False, encoding="utf-8") as f:
            f.write("junk")
            f.flush()
            path = f.name

        try:
            with (
                patch(
                    "src.pdf_ingest.ingest_pdf_page_aware",
                    side_effect=RuntimeError("Corrupt PDF"),
                ),
                patch("src.ocr_backends.get_ocr_backend") as mock_backend,
            ):
                mock_ocr = MagicMock()
                mock_ocr.available.return_value = False
                mock_backend.return_value = mock_ocr

                from src.agents.pipeline_state import PipelineState

                state = PipelineState(
                    input_mode="document",
                    document_source=path,
                )
                result = await graph._parse_document(state)
                assert "errors" in result
                assert "Corrupt PDF" in result["errors"][0]
        finally:
            Path(path).unlink(missing_ok=True)
