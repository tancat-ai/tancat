"""OCR backend adapter for the document parsing node (Phase 1i).

Provides a pluggable, **tiered** backend interface for PDF → text
conversion (AI-055 tiered CPU-first OCR):

- **Tier 0 — PyMuPDF** (always on): extracts embedded text directly.  Fast,
  zero OCR cost, handles text-based PDFs.  Whole documents always go through
  this tier so a mostly-text PDF stays fast.
- **Tier 1 — RapidOCR / PP-OCR (ONNX Runtime)** (AI-055 new default OCR tier):
  CPU-only OCR for scanned / image-only pages on **any machine, no network**.
  The ``auto`` backend (default) uses tier 0 for whole docs and tier 1 for
  image-only pages, so a scanned page is handled on any customer hardware.
- **Tier 3 — Unlimited-OCR** (existing wired GPU VLM, opt-in): Baidu's 3B
  vision-language model for the hardest complex docs.  Kept as the single
  tier-3 for v1 (spec §5); re-pick deferred to TanCat Cloud.

Usage::

    from src.ocr_backends import get_ocr_backend

    backend = get_ocr_backend()  # persisted setting > OCR_BACKEND env > auto
    text = backend.parse_pdf("path/to/document.pdf")
    page_text = backend.parse_page("path/to/scanned.pdf", 3)  # tier-1 CPU OCR

Backend / tier selection (B-036 Phase 4 persisted setting wins; AI-055 tiers)::

    auto             # default — tier 0 (whole-doc) + tier-1 CPU OCR (image-only)
    cpu              # tier-1 CPU forced (RapidOCR)
    high-accuracy    # tier 2 (not built in v1) → falls to tier-1 CPU
    power            # tier-3 GPU VLM (Unlimited-OCR)
    unlimited-ocr    # legacy alias → maps to the tier-3 GPU VLM
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from src.settings_store import load_setting

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

    def parse_page(self, path: str | Path, page_number: int) -> str:
        """OCR a single PDF page (1-indexed) — for image-only page fallback.

        Backends without page-level OCR return an empty string.  The
        production ingest path calls this only for pages where PyMuPDF
        found too few characters (i.e. scanned/image-only pages).
        """
        return ""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for logging.""" ""
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

    def parse_page(self, path: str | Path, page_number: int) -> str:
        """PyMuPDF has no OCR — it can only read embedded text, which an
        image-only page does not have.  Return empty so the caller skips."""
        return ""


# ---------------------------------------------------------------------------
# RapidOCR backend (tier-1 CPU OCR — AI-055)
# ---------------------------------------------------------------------------


class RapidOCRBackend(OcrBackend):
    """Tier-1 **CPU** OCR backend (RapidOCR / PP-OCRv5-v6 via ONNX Runtime).

    Scanned / image-only pages are handled on **any machine, CPU-only, no
    network** — the new default OCR tier for the local air-gapped product
    (AI-055).  Rasterises the single page to a 300 DPI PNG via PyMuPDF and
    runs the ONNX OCR on it.  PaddleOCR-level recognition accuracy at
    ~50–80 MB and 0.5–1 s/page.

    Requires:
        - ``pip install rapidocr_onnxruntime`` (the CPU-only distribution)
          — installed as the ``[ocr]`` optional extra so the default install
          stays light and an air-gapped customer who doesn't need OCR
          doesn't pull it.

    The engine is lazily loaded on first ``parse_page()`` call.  This
    backend only implements :meth:`parse_page` (the per-page image-only
    fallback) — whole-document parsing still goes through the PyMuPDF
    pipeline (tier 0), so a mostly-text PDF stays fast and only image-only
    pages hit OCR.  :meth:`parse_pdf` is provided for completeness (runs
    PyMuPDF on the whole doc) but is not used by the production ingest
    path.

    Zero egress: a local CPU ONNX model makes **no** network calls.
    """

    def __init__(self) -> None:
        self._engine: Any = None

    @property
    def name(self) -> str:
        return "rapidocr"

    @property
    def available(self) -> bool:
        """Whether the CPU ONNX OCR engine is importable in this environment."""
        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError:
            logger.debug(
                "rapidocr_onnxruntime not installed — run: pip install rapidocr_onnxruntime (or the [ocr] extra)"
            )
            return False
        return True

    def _ensure_engine(self) -> Any:
        """Lazy-load the ONNX OCR engine on first use."""
        if self._engine is not None:
            return self._engine

        import rapidocr_onnxruntime  # type: ignore[import-not-found]

        logger.info("Loading RapidOCR (PP-OCR, ONNX Runtime) — pure CPU, no network...")
        self._engine = rapidocr_onnxruntime.RapidOCR()
        logger.info("RapidOCR loaded successfully.")
        return self._engine

    def parse_pdf(self, path: str | Path) -> str:
        """Whole-document parsing via PyMuPDF (tier 0).

        Not used by the production ingest path (which calls :meth:`parse_page`
        per image-only page), but provided so the backend satisfies the
        ``OcrBackend`` contract.  An image-only page has no embedded text, so
        this returns the PyMuPDF text (empty for fully-scanned docs).
        """
        from src.pdf_ingest import ingest_pdf

        chunks = ingest_pdf(Path(path))
        return "\n\n".join(chunk.text for chunk in chunks)

    def parse_markdown(self, path: str | Path) -> str:
        """Markdown files are read directly — no OCR needed."""
        return Path(path).read_text(encoding="utf-8")

    def parse_page(self, path: str | Path, page_number: int) -> str:
        """OCR a single PDF page (1-indexed) — the image-only-page fallback.

        Rasterises just that page to a 300 DPI PNG and runs the CPU ONNX OCR
        on the single image.  Returns the recognised text (may be empty for a
        genuinely blank page).  Zero network calls — the model is local.
        """
        import shutil
        import tempfile

        import fitz  # PyMuPDF

        engine = self._ensure_engine()

        pdf_path = Path(path)
        doc = fitz.open(str(pdf_path))
        if page_number < 1 or page_number > doc.page_count:
            doc.close()
            logger.warning(
                "parse_page: page %d out of range (1-%d) for %s",
                page_number,
                doc.page_count,
                pdf_path.name,
            )
            return ""
        page = doc[page_number - 1]
        tmp_dir = tempfile.mkdtemp(prefix="rapidocr_page_")
        mat = fitz.Matrix(300 / 72, 300 / 72)
        try:
            out = Path(tmp_dir) / "page.png"
            page.get_pixmap(matrix=mat).save(str(out))

            result = engine(str(out))
            text = self._result_to_text(result)
            if text.strip():
                logger.info(
                    "  %s: page %d extracted via CPU OCR (%d chars)",
                    pdf_path.name,
                    page_number,
                    len(text.strip()),
                )
            return text
        finally:
            doc.close()
            if os.getenv("PIPELINE_DEBUG") != "1":
                shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _result_to_text(result: Any) -> str:
        """Convert a RapidOCR result to plain text.

        ``RapidOCR(path)`` returns a tuple ``(boxes, texts, scores)`` (and in
        some versions a fourth ``elapse``).  We join the recognised text
        lines in reading order (the engine already returns them ordered).
        """
        if not result:
            return ""
        # RapidOCR >= 1.0 returns (boxes, texts, scores) — texts is the 2nd element.
        # Older / variant shapes may return just the texts list or a dict; handle defensively.
        if isinstance(result, dict):
            texts = result.get("texts") or result.get("rec_texts") or []
            return "\n".join(str(t) for t in texts if t)
        if isinstance(result, (list, tuple)):
            # (boxes, texts, scores[, elapse]) → texts at index 1
            if len(result) >= 2 and isinstance(result[1], (list, tuple)):
                return "\n".join(str(t) for t in result[1] if t)
            # Variant: a flat list of text lines
            return "\n".join(str(t) for t in result if isinstance(t, str))
        # Fallback: str-ify
        return str(result)


# ---------------------------------------------------------------------------
# Auto backend (tier 0 whole-doc + tier-1 CPU per-page — AI-055 default)
# ---------------------------------------------------------------------------


class AutoOcrBackend(OcrBackend):
    """The ``auto`` tier (AI-055 default): tier-0 PyMuPDF whole-doc + tier-1
    CPU RapidOCR for image-only pages.

    Whole-document parsing goes through PyMuPDF (tier 0, zero OCR cost — a
    mostly-text PDF stays fast).  Image-only pages hit the tier-1 CPU OCR via
    :meth:`parse_page` — so a scanned page is handled on **any machine,
    CPU-only, no network** (the AI-055 core change).  If the CPU OCR engine
    is not installed, :meth:`parse_page` returns empty and the production
    ingest path skips the page with a loud WARNING (never fails ingestion
    because an optional tier is missing).
    """

    def __init__(self) -> None:
        self._text: PyMuPDFBackend = PyMuPDFBackend()
        self._ocr: RapidOCRBackend = RapidOCRBackend()

    @property
    def name(self) -> str:
        return "auto"

    @property
    def available(self) -> bool:
        """Tier 0 (PyMuPDF) is always on; tier-1 CPU OCR is best-effort."""
        return self._text.available

    def parse_pdf(self, path: str | Path) -> str:
        """Whole-doc parsing via PyMuPDF (tier 0)."""
        return self._text.parse_pdf(path)

    def parse_markdown(self, path: str | Path) -> str:
        """Markdown read directly."""
        return self._text.parse_markdown(path)

    def parse_page(self, path: str | Path, page_number: int) -> str:
        """Image-only-page fallback via the tier-1 CPU OCR (RapidOCR).

        Returns empty when the CPU OCR engine is absent so the caller skips
        the page (graceful degradation — never fail ingestion for a missing
        optional tier).
        """
        if not self._ocr.available:
            logger.debug(
                "auto.parse_page: CPU OCR (rapidocr) not installed — image-only page %d will be skipped",
                page_number,
            )
            return ""
        return self._ocr.parse_page(path, page_number)


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

    def parse_page(self, path: str | Path, page_number: int) -> str:
        """OCR a single PDF page (1-indexed) — the image-only-page fallback.

        Rasterises just that page to a 300 DPI PNG and runs the vision model
        on the single image.  Much cheaper than :meth:`parse_pdf` (no whole-
        document pass), which is why the production ingest path calls this
        per skipped page rather than re-OCRing the document.
        """
        import shutil
        import tempfile

        import fitz  # PyMuPDF

        self._ensure_model()
        assert self._model is not None
        assert self._tokenizer is not None

        pdf_path = Path(path)
        doc = fitz.open(str(pdf_path))
        if page_number < 1 or page_number > doc.page_count:
            doc.close()
            logger.warning("parse_page: page %d out of range (1-%d) for %s", page_number, doc.page_count, pdf_path.name)
            return ""
        page = doc[page_number - 1]
        tmp_dir = tempfile.mkdtemp(prefix="unlimited_ocr_page_")
        mat = fitz.Matrix(300 / 72, 300 / 72)
        try:
            out = Path(tmp_dir) / "page.png"
            page.get_pixmap(matrix=mat).save(str(out))

            self._model.infer_multi(
                self._tokenizer,
                prompt="<image>Single page parsing.",
                image_files=[str(out)],
                output_path=str(Path(tmp_dir) / "output"),
                image_size=1024,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=1024,
                save_results=True,
            )
            return self._collect_output_text(Path(tmp_dir) / "output")
        finally:
            doc.close()
            if os.getenv("PIPELINE_DEBUG") != "1":
                shutil.rmtree(tmp_dir, ignore_errors=True)

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
# Legacy tier mapping (AI-055 §5)
# ---------------------------------------------------------------------------

# Maps a backend name (persisted setting / ``OCR_BACKEND`` env / explicit
# arg) to the tier it represents, so existing ``OCR_BACKEND=unlimited-ocr``
# settings keep working while the new ``auto``/``cpu``/``high-accuracy``/
# ``power`` tier vocabulary lands.  ``unlimited-ocr`` is the existing wired
# tier-3 GPU VLM; it stays the single tier-3 for v1 (spec §5 leaning: keep
# for v1, revisit the model re-pick at TanCat Cloud).
_LEGACY_TO_TIER: dict[str, str] = {
    "auto": "auto",
    "pymupdf": "auto",  # legacy default → auto (tier 0 + tier-1 CPU)
    "cpu": "cpu",  # tier-1 CPU forced
    "rapidocr": "cpu",  # alias for tier-1
    "high-accuracy": "high-accuracy",  # tier 2 (not built in v1 → falls to lower tier)
    "power": "power",  # tier 3
    "unlimited-ocr": "power",  # legacy tier-3 alias
    "unlimited_ocr": "power",  # legacy tier-3 alias
}

# The OCR tier used as the image-only-page fallback when a higher tier is
# requested but unavailable.  ``auto``/``cpu``/``rapidocr`` all resolve to the
# RapidOCR CPU backend; ``high-accuracy`` (tier 2) is not built in v1 so it
# falls through to the CPU tier; ``power`` (tier 3) is the existing
# Unlimited-OCR GPU VLM.  (Defined after ``UnlimitedOCRBackend`` because it
# references that class.)
_TIER_FALLBACK_BACKEND: dict[str, type[OcrBackend]] = {
    "cpu": RapidOCRBackend,
    "high-accuracy": RapidOCRBackend,  # tier 2 not in v1 → CPU tier
    "power": UnlimitedOCRBackend,  # tier 3
}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_ocr_backend(backend_name: str | None = None) -> OcrBackend:
    """Return the configured OCR backend (AI-055 tiered selection).

    Resolution order (B-036 Phase 4, extended for AI-055 tiers):

    1. Explicit ``backend_name`` argument (tests / programmatic use).
    2. Persisted ``ocr_backend`` setting (SettingsStore).
    3. ``OCR_BACKEND`` env var — transition-window fallback only.
    4. ``auto`` default (tier 0 PyMuPDF whole-doc + tier-1 CPU OCR for
       image-only pages).

    Tiered OCR (AI-055):

    - ``auto`` (default) → :class:`AutoOcrBackend` — tier-0 PyMuPDF for
      whole docs, tier-1 CPU RapidOCR for image-only pages.
    - ``cpu`` / ``rapidocr`` → :class:`RapidOCRBackend` (tier-1 CPU forced).
    - ``high-accuracy`` → tier 2 (not built in v1) → falls to the CPU tier.
    - ``power`` / ``unlimited-ocr`` (legacy) → :class:`UnlimitedOCRBackend`
      (tier-3 GPU VLM; falls back to the CPU tier if no GPU).

    A tier that isn't installed / can't run on this machine is skipped and
    the path falls to the next-lower tier, then to "skip + WARNING."  Never
    fail the ingestion because an optional OCR tier is missing.

    Args:
        backend_name: Override for testing.  When None, consults the
            persisted setting, then the ``OCR_BACKEND`` env var.

    Returns:
        A ready-to-use ``OcrBackend`` instance.
    """
    if backend_name is None:
        # Settings win; env is honoured only when the setting was never saved.
        backend_name = load_setting("ocr_backend") or os.getenv("OCR_BACKEND", "auto")
    name = str(backend_name).strip().lower()
    tier = _LEGACY_TO_TIER.get(name, "auto")

    if tier == "auto":
        logger.debug("OCR backend: auto (tier 0 PyMuPDF + tier-1 CPU OCR)")
        return AutoOcrBackend()

    if tier in ("cpu", "high-accuracy"):
        backend = RapidOCRBackend()
        if backend.available:
            logger.info("OCR backend: %s (tier-1 CPU)", "high-accuracy" if tier == "high-accuracy" else "cpu")
            return backend
        logger.warning(
            "Tier-1 CPU OCR (rapidocr) requested but not installed — "
            "image-only pages will be skipped. Install with: pip install rapidocr_onnxruntime (or the [ocr] extra)"
        )
        # Fall through to a backend whose parse_page returns empty so the
        # ingest path skips image-only pages (graceful degradation).
        return RapidOCRBackend()

    if tier == "power":
        ocr_backend = UnlimitedOCRBackend()
        if ocr_backend.available:
            logger.info("OCR backend: unlimited-ocr (tier-3 GPU)")
            return ocr_backend
        logger.warning("Tier-3 GPU OCR requested but GPU not available — falling back to tier-1 CPU OCR")
        return RapidOCRBackend()

    # Defensive: unknown name → auto
    logger.debug("OCR backend: auto (unknown name %r)", name)
    return AutoOcrBackend()
