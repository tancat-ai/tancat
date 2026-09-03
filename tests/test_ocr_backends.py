"""Tests for OCR backend adapter (Phase 1i + AI-055 tiered CPU-first OCR).

Covers:
- PyMuPDFBackend: parse_pdf, parse_markdown, availability (tier 0)
- RapidOCRBackend: availability, parse_page (tier-1 CPU OCR — AI-055)
- AutoOcrBackend: tier-0 whole-doc + tier-1 CPU per-page (AI-055 default)
- UnlimitedOCRBackend: availability detection, lazy loading, error paths (tier 3)
- get_ocr_backend: factory with tiered selection, fallback behavior
- Integration with PipelineGraph._parse_document
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.agents.pipeline_graph import PipelineGraph
from src.ocr_backends import (
    AutoOcrBackend,
    PyMuPDFBackend,
    RapidOCRBackend,
    UnlimitedOCRBackend,
    get_ocr_backend,
)

# ---------------------------------------------------------------------------
# PyMuPDF backend
# ---------------------------------------------------------------------------


class TestPyMuPDFBackend:
    """Default CPU backend."""

    def test_name(self) -> None:
        assert PyMuPDFBackend().name == "pymupdf"

    def test_available_always_true(self) -> None:
        assert PyMuPDFBackend().available is True

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
        """When the engine module is importable, reports available."""
        with patch.dict(sys.modules, {"rapidocr_onnxruntime": MagicMock()}):
            backend = RapidOCRBackend()
            assert backend.available is True

    def test_parse_page_out_of_range_returns_empty(self) -> None:
        """A page number outside the PDF's range returns empty (no crash)."""
        backend = RapidOCRBackend()
        with patch.object(backend, "_ensure_engine", return_value=MagicMock()):
            # fitz is imported inside parse_page; patch the real module's open.
            with patch("fitz.open") as mock_open:
                mock_doc = MagicMock()
                mock_doc.page_count = 3
                mock_open.return_value = mock_doc
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
        ):
            backend = UnlimitedOCRBackend()
            assert backend.available is True

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
        """B-036 Phase 4: keep the persisted settings store out of these tests."""
        settings_file = tmp_path / "settings.enc"
        monkeypatch.setattr("src.settings_store._settings_path", lambda: settings_file)
        if settings_file.exists():
            settings_file.unlink()

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
            "src.ocr_backends.RapidOCRBackend.available",
            new_callable=PropertyMock,
            return_value=True,
        ):
            backend = get_ocr_backend("cpu")
            assert isinstance(backend, RapidOCRBackend)

    def test_rapidocr_alias_for_cpu(self) -> None:
        with patch("src.ocr_backends.RapidOCRBackend.available", return_value=True):
            backend = get_ocr_backend("rapidocr")
            assert isinstance(backend, RapidOCRBackend)

    def test_cpu_tier_without_engine_returns_unavailable_rapidocr(self) -> None:
        """Graceful degradation: CPU tier requested but engine absent → RapidOCRBackend
        whose ``available`` is False (parse_page returns empty, page skipped)."""
        with patch(
            "src.ocr_backends.RapidOCRBackend.available",
            new_callable=PropertyMock,
            return_value=False,
        ):
            backend = get_ocr_backend("cpu")
            assert isinstance(backend, RapidOCRBackend)
            assert backend.available is False

    def test_high_accuracy_falls_to_cpu_tier(self) -> None:
        """Tier 2 not built in v1 → falls to the CPU (RapidOCR) tier."""
        with patch(
            "src.ocr_backends.RapidOCRBackend.available",
            new_callable=PropertyMock,
            return_value=True,
        ):
            backend = get_ocr_backend("high-accuracy")
            assert isinstance(backend, RapidOCRBackend)

    def test_unlimited_ocr_without_gpu_falls_back_to_cpu(self) -> None:
        """Tier-3 GPU VLM requested but no GPU → falls to the CPU (RapidOCR) tier."""
        with patch("torch.cuda.is_available", return_value=False):
            backend = get_ocr_backend("unlimited-ocr")
            assert isinstance(backend, RapidOCRBackend)

    def test_unlimited_ocr_with_gpu_returns_ocr_backend(self) -> None:
        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("transformers.AutoModel", create=True),
            patch("transformers.AutoTokenizer", create=True),
        ):
            backend = get_ocr_backend("unlimited-ocr")
            assert isinstance(backend, UnlimitedOCRBackend)

    def test_env_var_overrides_default(self) -> None:
        with patch.dict(os.environ, {"OCR_BACKEND": "unlimited-ocr"}):
            with patch("torch.cuda.is_available", return_value=False):
                backend = get_ocr_backend()
                assert isinstance(backend, RapidOCRBackend)  # GPU check fails → CPU tier

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
        with patch.dict(os.environ, {"OCR_BACKEND": "unlimited-ocr"}):
            with patch("torch.cuda.is_available", return_value=False):
                backend = get_ocr_backend()
                assert isinstance(backend, RapidOCRBackend)  # requested → GPU fails → CPU tier

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
