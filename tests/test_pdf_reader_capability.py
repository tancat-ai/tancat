"""The PDF-reader capability the UI shows when document mode cannot read a PDF.

The shipped image must have the ``[pdf]`` extra (pypdfium2 + pdfplumber).  These
tests pin the honest capability check and the message that names what to install.
They never import the reader itself, so they run on a build that does not have it.
"""

from __future__ import annotations

import importlib.util

from src.pdf_ingest import (
    PDF_READER_INSTALL_HINT,
    PDF_READER_PACKAGES,
    pdf_reader_available,
    pdf_reader_missing_message,
)


def test_pdf_reader_available_tracks_the_packages() -> None:
    expected = all(importlib.util.find_spec(pkg) is not None for pkg in PDF_READER_PACKAGES)
    assert pdf_reader_available() == expected


def test_reader_packages_are_licence_clean() -> None:
    assert "pypdfium2" in PDF_READER_PACKAGES
    assert "pdfplumber" in PDF_READER_PACKAGES
    # The AGPL reader must never come back.
    assert "fitz" not in PDF_READER_PACKAGES


def test_missing_message_names_the_install() -> None:
    message = pdf_reader_missing_message()
    assert "--extra pdf" in message
    assert PDF_READER_INSTALL_HINT in message
    assert "PyMuPDF" not in message


def test_install_hint_names_both_installers() -> None:
    assert "uv sync --extra pdf" in PDF_READER_INSTALL_HINT
    assert "pypdfium2" in PDF_READER_INSTALL_HINT
    assert "pdfplumber" in PDF_READER_INSTALL_HINT
