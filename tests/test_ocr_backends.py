"""Tests for OCR backend adapter (Phase 1i).

Covers:
- PyMuPDFBackend: parse_pdf, parse_markdown, availability
- UnlimitedOCRBackend: availability detection, lazy loading, error paths
- get_ocr_backend: factory with env var, fallback behavior
- Integration with PipelineGraph._parse_document
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ocr_backends import (
    PyMuPDFBackend,
    UnlimitedOCRBackend,
    get_ocr_backend,
)
from src.agents.pipeline_graph import PipelineGraph

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
    """get_ocr_backend() factory with env var and fallback."""

    def test_default_is_pymupdf(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            backend = get_ocr_backend()
            assert isinstance(backend, PyMuPDFBackend)

    def test_explicit_pymupdf(self) -> None:
        backend = get_ocr_backend("pymupdf")
        assert isinstance(backend, PyMuPDFBackend)

    def test_unlimited_ocr_without_gpu_falls_back(self) -> None:
        with patch("torch.cuda.is_available", return_value=False):
            backend = get_ocr_backend("unlimited-ocr")
            assert isinstance(backend, PyMuPDFBackend)  # fallback

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
                assert isinstance(backend, PyMuPDFBackend)  # GPU check fails → fallback

    def test_explicit_backend_overrides_env_var(self) -> None:
        with patch.dict(os.environ, {"OCR_BACKEND": "unlimited-ocr"}):
            backend = get_ocr_backend("pymupdf")
            assert isinstance(backend, PyMuPDFBackend)


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
        """PDF parsing goes through the OCR backend, not direct ingest_pdf."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False, encoding="utf-8") as f:
            f.write("%PDF-1.4\nfake pdf\n%%EOF")
            f.flush()
            path = f.name

        try:
            with patch(
                "src.ocr_backends.PyMuPDFBackend.parse_pdf",
                return_value="OCR'd content from backend",
            ) as mock_parse:
                from src.agents.pipeline_state import PipelineState

                state = PipelineState(
                    input_mode="document",
                    document_source=path,
                )
                result = await graph._parse_document(state)

                mock_parse.assert_called_once()
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
        """OCR backend failure returns structured error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False, encoding="utf-8") as f:
            f.write("junk")
            f.flush()
            path = f.name

        try:
            with patch(
                "src.ocr_backends.PyMuPDFBackend.parse_pdf",
                side_effect=RuntimeError("Corrupt PDF"),
            ):
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
