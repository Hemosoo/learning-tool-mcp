"""Tests for PDF ingestion (spec 04)."""

from __future__ import annotations

from pathlib import Path

import pytest

from learning_tool.ingestion.pdf import PdfIngestionError, chunk_text, extract_text


def test_extracts_text_from_a_valid_pdf(pdf_factory) -> None:
    """A real text PDF yields its rendered lines."""
    path = pdf_factory(["Newtons laws describe motion.", "Momentum is conserved."])

    text = extract_text(str(path))

    assert "Newtons laws describe motion." in text
    assert "Momentum is conserved." in text


def test_pages_are_joined_by_a_blank_line(pdf_factory) -> None:
    """Page breaks become paragraph breaks, and textless pages contribute none."""
    path = pdf_factory(
        pages=[["First page body."], [], ["Third page body."]], name="three.pdf"
    )

    text = extract_text(str(path))

    assert "First page body.\n\n" in text
    assert chunk_text(text) == ["First page body.", "Third page body."]


def test_missing_file_raises_naming_the_path(tmp_path: Path) -> None:
    """A path that is not a file is reported as not found."""
    missing = tmp_path / "nope.pdf"

    with pytest.raises(PdfIngestionError, match="PDF not found") as excinfo:
        extract_text(str(missing))

    assert str(missing) in str(excinfo.value)


def test_unparseable_file_raises_with_the_cause_chained(tmp_path: Path) -> None:
    """Parser failures surface as the module's own error type."""
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is definitely not a pdf")

    with pytest.raises(PdfIngestionError, match="Failed to read PDF") as excinfo:
        extract_text(str(broken))

    assert excinfo.value.__cause__ is not None


def test_textless_pdf_raises(pdf_factory) -> None:
    """A PDF with no extractable text is an error, not an empty document."""
    path = pdf_factory(pages=[[]], name="blank.pdf")

    with pytest.raises(PdfIngestionError, match="no extractable text"):
        extract_text(str(path))


def test_chunking_splits_on_blank_lines_and_strips() -> None:
    """Paragraphs become stripped chunks in order."""
    text = "  First paragraph.  \n\nSecond\nparagraph.\n\n\n Third. "

    assert chunk_text(text) == ["First paragraph.", "Second\nparagraph.", "Third."]


def test_chunking_treats_whitespace_only_lines_as_separators() -> None:
    """Lines of spaces still separate paragraphs, and empties are dropped."""
    text = "Alpha\n   \n\t\nBeta\n \n"

    assert chunk_text(text) == ["Alpha", "Beta"]


def test_chunking_blank_input_yields_empty_list() -> None:
    """Chunking never raises; blank input simply yields nothing."""
    assert chunk_text("   \n\n  ") == []
