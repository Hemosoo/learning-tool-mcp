"""PDF text extraction and paragraph chunking."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

_PARAGRAPH_BREAK = re.compile(r"(?:[ \t\r\f\v]*\n){2,}[ \t\r\f\v]*")
"""Two or more newlines separated only by optional horizontal whitespace."""


class PdfIngestionError(RuntimeError):
    """Raised when a PDF cannot be found, parsed, or yields no text."""


def extract_text(pdf_path: str) -> str:
    """Extract the full text of a PDF.

    Args:
        pdf_path: Filesystem path to the PDF.

    Returns:
        The document text, with pages joined by a blank line.

    Raises:
        PdfIngestionError: If the file is missing, cannot be parsed, or
            contains no extractable text.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise PdfIngestionError(f"PDF not found: {pdf_path}")

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises many types on malformed input
        raise PdfIngestionError(f"Failed to read PDF: {pdf_path}") from exc

    text = "\n\n".join(pages)
    if not text.strip():
        raise PdfIngestionError(
            f"PDF has no extractable text (it may be scanned images): {pdf_path}"
        )
    return text


def chunk_text(text: str) -> list[str]:
    """Split text into stripped paragraph chunks.

    Args:
        text: The extracted document text.

    Returns:
        One chunk per non-empty paragraph, in order.
    """
    return [chunk for raw in _PARAGRAPH_BREAK.split(text) if (chunk := raw.strip())]
