"""Render a document's study items as Anki-importable CSV text."""

from __future__ import annotations

import csv
import io
import re
import string

from learning_tool.storage.models import Document, QuestionType

SEPARATOR_DIRECTIVE = "#separator:Comma"
"""Declares the column separator to Anki's text importer."""

HTML_DIRECTIVE = "#html:false"
"""Declares that fields are plain text, not HTML."""

TAGS_COLUMN_DIRECTIVE = "#tags column:3"
"""Declares which column carries tags (1-based)."""

OPTION_LETTERS = string.ascii_uppercase
"""Letters prefixed to multiple-choice options, in order."""

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
"""Run of characters that cannot appear in an Anki tag."""


def tag_for(title: str) -> str:
    """Convert a document title into a single Anki tag.

    Anki tags cannot contain spaces, so every non-alphanumeric run collapses
    to one hyphen.

    Args:
        title: The document's title.

    Returns:
        The tag, lowercased and hyphenated.
    """
    return _NON_ALPHANUMERIC.sub("-", title.lower()).strip("-")


def _question_front(question_text: str, options: list[str]) -> str:
    """Build the front field of a quiz row.

    Args:
        question_text: The question as stored.
        options: Multiple-choice options, empty for short answers.

    Returns:
        The question, with any options appended as lettered lines.
    """
    if not options:
        return question_text
    lettered = [
        f"{OPTION_LETTERS[index]}. {option}"
        for index, option in enumerate(options)
        if index < len(OPTION_LETTERS)
    ]
    return "\n".join([question_text, *lettered])


def render_csv(document: Document, include_quiz: bool = True) -> str:
    """Render a document's items as Anki text-import CSV.

    Args:
        document: The document to export.
        include_quiz: Whether to include quiz questions alongside flashcards.

    Returns:
        The complete CSV text, directives first.

    Raises:
        ValueError: If the document has no exportable items.
    """
    tag = tag_for(document.title)
    rows: list[tuple[str, str, str]] = [
        (card.front, card.back, tag) for card in document.flashcards
    ]
    if include_quiz:
        rows.extend(
            (
                _question_front(
                    question.question,
                    list(question.options)
                    if question.question_type is QuestionType.MULTIPLE_CHOICE
                    else [],
                ),
                question.answer,
                tag,
            )
            for question in document.quiz_questions
        )

    if not rows:
        raise ValueError(
            f"Document {document.id} has no items to export"
            f"{'' if include_quiz else ' (quiz questions excluded)'}"
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    directives = "\n".join(
        [SEPARATOR_DIRECTIVE, HTML_DIRECTIVE, TAGS_COLUMN_DIRECTIVE, ""]
    )
    return directives + buffer.getvalue()
