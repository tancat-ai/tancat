"""OCR backend adapter for the document parsing node (Phase 1i).

Provides a pluggable backend interface for PDF → text conversion.
Two backends are available:

- **PyMuPDFBackend** (default): Uses PyMuPDF to extract text directly
  from PDFs.  Fast, zero GPU requirement, handles ~95% of real-world PDFs.

- **UnlimitedOCRBackend** (opt-in): Uses Baidu's 3B-parameter vision-language
  model to OCR document images.  Handles scanned PDFs, complex layouts,
  and image-only pages that PyMuPDF can't process.

Usage::

    from src.ocr_backends import get_ocr_backend

    backend = get_ocr_backend()  # reads OCR_BACKEND env var
    text = backend.parse_pdf("path/to/document.pdf")

Backend selection::

    OCR_BACKEND=pymupdf          # default — fast, offline
    OCR_BACKEND=unlimited-ocr    # GPU required — vision model
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------


class OcrBackend(ABC):
    """Abstract interface for PDF-to-text conversion."""

    @abstractmethod
    def parse_pdf(self, path: str | Path) -> str:
        """Convert a PDF file to plain text.

        Args:
            path: Path to a PDF file.

        Returns:
            Extracted text with paragraphs separated by blank lines.
        """
        ...

    @abstractmethod
    def parse_markdown(self, path: str | Path) -> str:
        """Read a Markdown file directly (no OCR needed)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for logging."""
        ...

    @property
    def available(self) -> bool:
        """Whether this backend can operate in the current environment."""
        return True


# ---------------------------------------------------------------------------
# PyMuPDF backend (default)
# ---------------------------------------------------------------------------


class PyMuPDFBackend(OcrBackend):
    """Extract text from PDFs using PyMuPDF.

    The existing ``src/pdf_ingest.ingest_pdf()`` pipeline — heading
    detection, table extraction, chunking.  Handles text-based PDFs
    with structured layout.
    """

    @property
    def name(self) -> str:
        return "pymupdf"

    def parse_pdf(self, path: str | Path) -> str:
        from src.pdf_ingest import ingest_pdf

        chunks = ingest_pdf(Path(path))
        return "\n\n".join(chunk.text for chunk in chunks)

    def parse_markdown(self, path: str | Path) -> str:
        return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Unlimited OCR backend (GPU-accelerated vision model)
# ---------------------------------------------------------------------------


class UnlimitedOCRBackend(OcrBackend):
    """Baidu Unlimited-OCR vision-language model for PDF parsing.

    Renders each PDF page to a 300 DPI PNG via PyMuPDF, then feeds
    the image sequence to the 3B-parameter model for long-horizon
    document transcription.

    Requires:
        - NVIDIA GPU with CUDA 12.9+ (or AMD ROCm build of PyTorch)
        - ``pip install transformers>=4.57 torch>=2.10 pymupdf Pillow einops``
        - First run downloads ~6 GB model weights from Hugging Face

    The model is lazily loaded on first ``parse_pdf()`` call.
    """

    MODEL_NAME: str = "baidu/Unlimited-OCR"

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None
        self._dtype: Any = None

    @property
    def name(self) -> str:
        return "unlimited-ocr"

    @property
    def available(self) -> bool:
        """Check whether GPU + required packages are available.

        Supports NVIDIA CUDA and AMD ROCm (via HIP).
        """
        try:
            import torch  # noqa: F401
        except ImportError:
            return False

        # NVIDIA CUDA or AMD ROCm — both report True for is_available
        # when a compatible PyTorch build is installed.
        if not torch.cuda.is_available():
            logger.debug("No GPU detected — Unlimited-OCR requires CUDA or ROCm")
            return False

        try:
            import transformers  # noqa: F401
        except ImportError:
            logger.debug("transformers not installed — run: pip install transformers>=4.57")
            return False

        return True

    def _ensure_model(self) -> None:
        """Lazy-load the model on first use."""
        if self._model is not None:
            return

        import torch
        from transformers import AutoModel, AutoTokenizer

        if not torch.cuda.is_available():
            raise RuntimeError(
                "Unlimited-OCR requires a GPU with CUDA or ROCm support. "
                "Install a GPU-compatible PyTorch build, or set "
                "OCR_BACKEND=pymupdf for CPU-only PDF parsing."
            )

        use_bf16 = torch.cuda.is_bf16_supported()
        self._dtype = torch.bfloat16 if use_bf16 else torch.float16

        gpu_name = torch.cuda.get_device_name(0)
        logger.info("Loading Unlimited-OCR on %s (dtype=%s)...", gpu_name, self._dtype)
        logger.info("First load downloads ~6 GB from Hugging Face — this may take a few minutes.")

        self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME, trust_remote_code=True)
        self._model = AutoModel.from_pretrained(
            self.MODEL_NAME,
            trust_remote_code=True,
            use_safetensors=True,
            torch_dtype=self._dtype,
        )
        self._model = self._model.eval().cuda()
        logger.info("Unlimited-OCR loaded successfully.")

    def parse_pdf(self, path: str | Path) -> str:
        """Render PDF pages to images → OCR via Unlimited-OCR model.

        Uses the Gundam tiled mode (crop_mode=True, image_size=640)
        for high-fidelity text recognition on dense documents.
        """
        import tempfile
        from pathlib import Path

        import fitz  # PyMuPDF

        self._ensure_model()
        assert self._model is not None
        assert self._tokenizer is not None

        pdf_path = Path(path)
        logger.info("Parsing PDF %s with Unlimited-OCR...", pdf_path.name)

        # Render pages to images at 300 DPI
        doc = fitz.open(str(pdf_path))
        tmp_dir = tempfile.mkdtemp(prefix="unlimited_ocr_")
        mat = fitz.Matrix(300 / 72, 300 / 72)
        image_paths: list[str] = []

        try:
            for i, page in enumerate(doc):
                out = Path(tmp_dir) / f"page_{i + 1:04d}.png"
                page.get_pixmap(matrix=mat).save(str(out))
                image_paths.append(str(out))
            doc.close()

            logger.info("Rasterised %d pages for OCR", len(image_paths))

            # Single forward pass over all pages
            self._model.infer_multi(
                self._tokenizer,
                prompt="<image>Multi page parsing.",
                image_files=image_paths,
                output_path=str(Path(tmp_dir) / "output"),
                image_size=1024,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=1024,
                save_results=True,
            )

            # Read the generated markdown output
            output_dir = Path(tmp_dir) / "output"
            result_text = self._collect_output_text(output_dir)

        finally:
            # Clean up temp files (keep for debugging if PIPELINE_DEBUG=1)
            import shutil

            if os.getenv("PIPELINE_DEBUG") != "1":
                shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                logger.debug("OCR temp files kept at: %s", tmp_dir)

        return result_text

    def parse_markdown(self, path: str | Path) -> str:
        """Markdown files are read directly — no OCR needed."""
        return Path(path).read_text(encoding="utf-8")

    @staticmethod
    def _collect_output_text(output_dir: Path) -> str:
        """Collect text from Unlimited-OCR output files.

        The model writes ``.mmd`` (markdown) and ``.txt`` files.
        Prefers ``.mmd`` for structured output, falls back to ``.txt``.
        """
        mmd_files = sorted(output_dir.glob("*.mmd"))
        if mmd_files:
            return "\n\n".join(f.read_text(encoding="utf-8") for f in mmd_files)

        txt_files = sorted(output_dir.glob("*.txt"))
        if txt_files:
            return "\n\n".join(f.read_text(encoding="utf-8") for f in txt_files)

        # Fallback: scan for any text-like output
        for ext in (".md", ".json"):
            for f in sorted(output_dir.glob(f"*{ext}")):
                return f.read_text(encoding="utf-8")

        logger.warning("No text output found in %s", output_dir)
        return ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_ocr_backend(backend_name: str | None = None) -> OcrBackend:
    """Return the configured OCR backend.

    Reads ``OCR_BACKEND`` environment variable, or uses the provided
    ``backend_name``.  Falls back to PyMuPDF if the requested backend
    is unavailable.

    Args:
        backend_name: Override for testing.  Reads ``OCR_BACKEND`` env var if None.

    Returns:
        A ready-to-use ``OcrBackend`` instance.
    """
    name = backend_name or os.getenv("OCR_BACKEND", "pymupdf").strip().lower()

    if name in ("unlimited-ocr", "unlimited_ocr"):
        backend = UnlimitedOCRBackend()
        if backend.available:
            logger.info("OCR backend: unlimited-ocr (GPU)")
            return backend
        logger.warning("Unlimited-OCR requested but GPU not available — falling back to PyMuPDF")

    logger.debug("OCR backend: pymupdf (CPU)")
    return PyMuPDFBackend()
