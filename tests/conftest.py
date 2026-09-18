"""Shared test helpers: a hand-built minimal PDF and common fixtures."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest


def _escape(text: str) -> str:
    """Escape a string for use inside a PDF literal string.

    Args:
        text: ASCII text to escape.

    Returns:
        The text with backslashes and parentheses escaped.
    """
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: Sequence[str]) -> bytes:
    """Render one page's content stream.

    Args:
        lines: The page's text lines.

    Returns:
        The page's drawing instructions.
    """
    if not lines:
        return b""
    drawn = "\n".join(f"({_escape(line)}) Tj\nT*" for line in lines)
    return f"BT\n/F1 12 Tf\n16 TL\n72 720 Td\n{drawn}\nET\n".encode("ascii")


def build_minimal_pdf(pages: Sequence[Sequence[str]]) -> bytes:
    """Hand-build a valid PDF drawing the given ASCII lines, one list per page.

    The cross-reference table carries real byte offsets so that a real PDF
    parser accepts the result; no PDF library is used to produce it.

    Args:
        pages: One sequence of text lines per page. An empty page yields a
            page with no extractable text.

    Returns:
        The complete PDF file bytes.
    """
    page_count = len(pages)
    first_page_obj = 4  # 1 catalog, 2 page tree, 3 font
    kids = " ".join(f"{first_page_obj + 2 * i} 0 R" for i in range(page_count))

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, lines in enumerate(pages):
        content = _content_stream(lines)
        page_obj = first_page_obj + 2 * index
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {page_obj + 1} 0 R >>".encode("ascii")
        )
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii")
            + content
            + b"endstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode("ascii") + b" 0 obj\n" + body + b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii")
    out += f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    return bytes(out)


@pytest.fixture
def pdf_factory(tmp_path: Path):
    """Return a factory writing minimal PDFs into the temp directory.

    Returns:
        A callable taking one page's text lines (or, via ``pages``, several
        pages) and returning the path of the written PDF.
    """

    def make(
        lines: Sequence[str] | None = None,
        name: str = "sample.pdf",
        pages: Sequence[Sequence[str]] | None = None,
    ) -> Path:
        path = tmp_path / name
        path.write_bytes(
            build_minimal_pdf(pages if pages is not None else [lines or []])
        )
        return path

    return make
