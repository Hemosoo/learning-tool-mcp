"""Tests for Anki CSV rendering (future/anki-csv-export)."""

from __future__ import annotations

import csv
import io

import pytest

from learning_tool.export.anki import (
    HTML_DIRECTIVE,
    SEPARATOR_DIRECTIVE,
    TAGS_COLUMN_DIRECTIVE,
    render_csv,
    tag_for,
)
from learning_tool.storage.models import (
    Document,
    Flashcard,
    QuestionType,
    QuizQuestion,
)


def document(**overrides) -> Document:
    """Build a document with one flashcard and one quiz question.

    Args:
        **overrides: Fields to replace on the default document.

    Returns:
        The document.
    """
    defaults = dict(
        id=1,
        title="Cell Biology",
        source_path="/tmp/cell.pdf",
        flashcards=[Flashcard(id=1, front="What is ATP?", back="Energy currency")],
        quiz_questions=[
            QuizQuestion(
                id=2,
                question="Which organelle makes ATP?",
                answer="mitochondria",
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=["mitochondria", "ribosome"],
            )
        ],
    )
    defaults.update(overrides)
    return Document(**defaults)


def rows_of(csv_text: str) -> list[list[str]]:
    """Parse the data rows of rendered CSV, skipping directives.

    Args:
        csv_text: The rendered export.

    Returns:
        One list of fields per row.
    """
    body = "\n".join(line for line in csv_text.splitlines() if not line.startswith("#"))
    return list(csv.reader(io.StringIO(body)))


def test_directives_lead_the_file_in_order() -> None:
    """Anki reads the import settings from the leading directive lines."""
    lines = render_csv(document()).splitlines()

    assert lines[:3] == [SEPARATOR_DIRECTIVE, HTML_DIRECTIVE, TAGS_COLUMN_DIRECTIVE]
    assert SEPARATOR_DIRECTIVE == "#separator:Comma"
    assert HTML_DIRECTIVE == "#html:false"
    assert TAGS_COLUMN_DIRECTIVE == "#tags column:3"


def test_every_row_has_three_columns_ending_in_the_tag() -> None:
    """Rows are front, back, tags."""
    rows = rows_of(render_csv(document()))

    assert len(rows) == 2
    assert all(len(row) == 3 for row in rows)
    assert {row[2] for row in rows} == {"cell-biology"}


def test_flashcards_map_front_and_back_as_stored() -> None:
    """A flashcard exports verbatim."""
    rows = rows_of(render_csv(document()))

    assert rows[0][:2] == ["What is ATP?", "Energy currency"]


def test_multiple_choice_options_are_lettered_in_the_front_field() -> None:
    """The front carries the question and its lettered options."""
    rows = rows_of(render_csv(document()))

    assert rows[1][0] == "Which organelle makes ATP?\nA. mitochondria\nB. ribosome"
    assert rows[1][1] == "mitochondria"


def test_short_answer_questions_carry_no_options() -> None:
    """A short-answer front is the question alone."""
    doc = document(
        quiz_questions=[
            QuizQuestion(
                id=2,
                question="Define osmosis",
                answer="water moving down its gradient",
                question_type=QuestionType.SHORT_ANSWER,
            )
        ]
    )

    assert rows_of(render_csv(doc))[1][0] == "Define osmosis"


def test_fields_with_separators_quotes_and_newlines_round_trip() -> None:
    """Quoting follows CSV rules, verified by reading the output back."""
    doc = document(
        flashcards=[
            Flashcard(
                id=1,
                front='He said "hello", loudly',
                back="line one\nline two, with a comma",
            )
        ],
        quiz_questions=[],
    )

    rows = rows_of(render_csv(doc))

    assert rows[0][0] == 'He said "hello", loudly'
    assert rows[0][1] == "line one\nline two, with a comma"


def test_tags_collapse_non_alphanumeric_runs_to_single_hyphens() -> None:
    """Anki tags cannot contain spaces."""
    assert tag_for("Cell Biology, Ch. 3!") == "cell-biology-ch-3"
    assert tag_for("  Physics 101  ") == "physics-101"
    assert tag_for("A---B") == "a-b"


def test_excluding_quiz_exports_only_flashcards() -> None:
    """include_quiz false drops the quiz rows."""
    rows = rows_of(render_csv(document(), include_quiz=False))

    assert len(rows) == 1
    assert rows[0][0] == "What is ATP?"


def test_document_without_items_raises_rather_than_rendering_nothing() -> None:
    """An empty export is silent failure, so it is an error."""
    with pytest.raises(ValueError, match="no items to export"):
        render_csv(document(flashcards=[], quiz_questions=[]))


def test_quiz_only_document_with_quiz_excluded_raises() -> None:
    """Excluding the only items there are is still an empty export."""
    doc = document(flashcards=[])

    with pytest.raises(ValueError, match="no items to export"):
        render_csv(doc, include_quiz=False)
