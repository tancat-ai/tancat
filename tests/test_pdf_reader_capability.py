"""The PDF-reader capability the UI shows when document mode cannot read a PDF.

The shipped image has no ``[pdf]`` extra, so ``fitz`` is absent and document
mode has no reader.  These tests pin the honest capability check and the message
that names what to install.  They do not import ``fitz``, so they run on a build
that does not have it (the shipped image).
"""

from __future__ import annotations

import importlib.util

from src.pdf_ingest import (
    PDF_READER_INSTALL_HINT,
    pdf_reader_available,
    pdf_reader_missing_message,
)


def test_pdf_reader_available_tracks_fitz() -> None:
    assert pdf_reader_available() == (importlib.util.find_spec("fitz") is not None)


def test_missing_message_names_pymupdf_and_the_install() -> None:
    message = pdf_reader_missing_message()
    assert "PyMuPDF" in message
    assert "--extra pdf" in message
    assert PDF_READER_INSTALL_HINT in message


def test_install_hint_names_both_installers() -> None:
    assert "uv sync --extra pdf" in PDF_READER_INSTALL_HINT
    assert "pip install PyMuPDF" in PDF_READER_INSTALL_HINT
