"""The study service: orchestration, grading, parsing, and output shaping."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from learning_tool.export.anki import render_csv
from learning_tool.ingestion.pdf import chunk_text, extract_text
from learning_tool.scheduling.sm2 import ItemSchedule
from learning_tool.storage.models import (
    Confidence,
    Document,
    Flashcard,
    ItemType,
    QuestionType,
    QuizQuestion,
)
from learning_tool.storage.repository import (
    NewFlashcard,
    NewQuizQuestion,
    Repository,
    SessionState,
)

SELF_REPORT_CORRECT = "correct"
"""Accepted flashcard self-report meaning the user got the card right."""

SELF_REPORT_INCORRECT = "incorrect"
"""Accepted flashcard self-report meaning the user got the card wrong."""

_WHITESPACE = re.compile(r"\s+")
"""Run of whitespace collapsed during answer normalization."""

_EnumT = TypeVar("_EnumT", bound=Enum)
"""Any of the domain's string enums."""


def _parse_enum(value: str, enum: type[_EnumT], field: str) -> _EnumT:
    """Convert a string into one of an enum's members.

    Args:
        value: The untrusted string.
        enum: The target string enum.
        field: Field name used in the error message.

    Returns:
        The matching enum member.

    Raises:
        ValueError: If the string is not one of the enum's values.
    """
    try:
        return enum(value)
    except ValueError:
        valid = ", ".join(member.value for member in enum)
        raise ValueError(f"{field} must be one of: {valid}") from None


def parse_item_type(value: str) -> ItemType:
    """Parse an item type string.

    Args:
        value: The untrusted string.

    Returns:
        The item type.

    Raises:
        ValueError: If the value is not a valid item type.
    """
    return _parse_enum(value, ItemType, "item_type")


def parse_question_type(value: str) -> QuestionType:
    """Parse a question type string.

    Args:
        value: The untrusted string.

    Returns:
        The question type.

    Raises:
        ValueError: If the value is not a valid question type.
    """
    return _parse_enum(value, QuestionType, "question_type")


def parse_confidence(value: str | None) -> Confidence | None:
    """Parse an optional confidence string.

    Args:
        value: The untrusted string, or None for no self-report.

    Returns:
        The confidence level, or None.

    Raises:
        ValueError: If the value is neither None nor a valid level.
    """
    if value is None:
        return None
    return _parse_enum(value, Confidence, "confidence")


def normalize_answer(answer: str) -> str:
    """Normalize an answer for comparison.

    Args:
        answer: The raw answer text.

    Returns:
        The answer lowercased, trimmed, with whitespace runs collapsed.
    """
    return _WHITESPACE.sub(" ", answer.strip().lower())


def _parse_self_report(answer: str) -> bool:
    """Interpret a flashcard self-report.

    Args:
        answer: The submitted self-report.

    Returns:
        True for "correct", False for "incorrect".

    Raises:
        ValueError: If the answer is neither accepted value.
    """
    normalized = answer.strip().lower()
    if normalized == SELF_REPORT_CORRECT:
        return True
    if normalized == SELF_REPORT_INCORRECT:
        return False
    raise ValueError(
        f"flashcard answer must be one of: {SELF_REPORT_CORRECT}, "
        f"{SELF_REPORT_INCORRECT}"
    )


def _flashcard_dict(card: Flashcard) -> dict[str, Any]:
    """Shape a flashcard for the wire.

    Args:
        card: The flashcard.

    Returns:
        Its id, front, and back.
    """
    return {"id": card.id, "front": card.front, "back": card.back}


def _quiz_dict(question: QuizQuestion) -> dict[str, Any]:
    """Shape a quiz question for the wire.

    Args:
        question: The quiz question.

    Returns:
        Its id, question, options, answer, and question type string.
    """
    return {
        "id": question.id,
        "question": question.question,
        "options": list(question.options),
        "answer": question.answer,
        "question_type": question.question_type.value,
    }


def _session_dict(state: SessionState) -> dict[str, Any]:
    """Shape a session state for the wire.

    Args:
        state: The bucketed counts.

    Returns:
        The five integer fields plus the confidence breakdown.
    """
    return {
        "mastered": state.mastered,
        "to_review": state.to_review,
        "remaining": state.remaining,
        "in_progress": state.in_progress,
        "total": state.total,
        "confidence": dict(state.confidence),
    }


def _due_dict(item: Flashcard | QuizQuestion, schedule: ItemSchedule) -> dict[str, Any]:
    """Shape one due item plus its schedule for the wire.

    Args:
        item: The due flashcard or quiz question.
        schedule: Its computed schedule.

    Returns:
        The scheduling fields merged with the item's own fields.
    """
    is_flashcard = isinstance(item, Flashcard)
    entry: dict[str, Any] = {
        "item_type": (ItemType.FLASHCARD if is_flashcard else ItemType.QUIZ).value,
        "item_id": item.id,
        "repetitions": schedule.repetitions,
        "interval_days": schedule.interval_days,
        "next_review": (
            schedule.next_review.isoformat() if schedule.next_review else None
        ),
    }
    if isinstance(item, Flashcard):
        entry.update(front=item.front, back=item.back)
    else:
        entry.update(
            question=item.question,
            options=list(item.options),
            answer=item.answer,
            question_type=item.question_type.value,
        )
    return entry


class StudyService:
    """Orchestrates ingestion, storage, grading, and progress reporting."""

    def __init__(self, data_dir: Path) -> None:
        """Build the service over a data directory.

        Args:
            data_dir: Root directory for stored data.
        """
        self._data_dir = Path(data_dir)
        self._repo = Repository(self._data_dir)

    @staticmethod
    def _now() -> datetime:
        """Resolve the current instant as timezone-aware UTC.

        Returns:
            The current time in UTC.
        """
        return datetime.now(timezone.utc)

    def ingest_material(
        self, pdf_path: str, title: str | None = None
    ) -> dict[str, Any]:
        """Extract a PDF's text, chunk it, and store it as a new document.

        Args:
            pdf_path: Path to the PDF.
            title: Optional title; defaults to the PDF's file name.

        Returns:
            document_id, title, and concept_count.

        Raises:
            PdfIngestionError: If the PDF is missing, unparseable, or textless.
        """
        concepts = chunk_text(extract_text(pdf_path))
        document = self._repo.create_document(
            title=title or Path(pdf_path).name,
            source_path=pdf_path,
            concepts=concepts,
        )
        return {
            "document_id": document.id,
            "title": document.title,
            "concept_count": len(document.concepts),
        }

    def get_material(self, document_id: int) -> dict[str, Any]:
        """Return a document's stored source material.

        Args:
            document_id: The document's id.

        Returns:
            document_id, title, and the concept chunks.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        document = self._repo.get_document(document_id)
        return {
            "document_id": document.id,
            "title": document.title,
            "concepts": list(document.concepts),
        }

    def list_documents(self) -> list[dict[str, Any]]:
        """Enumerate stored documents.

        Returns:
            One entry per document, ascending by id, with counts and the
            ISO-8601 creation timestamp.
        """
        return [
            {
                "document_id": document.id,
                "title": document.title,
                "concept_count": len(document.concepts),
                "flashcard_count": len(document.flashcards),
                "quiz_count": len(document.quiz_questions),
                "created_at": document.created_at.isoformat(),
            }
            for document in self._repo.list_documents()
        ]

    def get_study_items(self, document_id: int) -> dict[str, Any]:
        """Return a document's saved flashcards and quiz questions.

        Args:
            document_id: The document's id.

        Returns:
            document_id, title, flashcards, and quiz_questions.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        document = self._repo.get_document(document_id)
        return {
            "document_id": document.id,
            "title": document.title,
            "flashcards": [_flashcard_dict(card) for card in document.flashcards],
            "quiz_questions": [
                _quiz_dict(question) for question in document.quiz_questions
            ],
        }

    def get_due_items(self, document_id: int) -> dict[str, Any]:
        """Return the items due for review now, most overdue first.

        Args:
            document_id: The document's id.

        Returns:
            document_id, title, the due entries, and due_count.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        now = self._now()
        document = self._repo.get_document(document_id)
        due = self._repo.get_due_items(document_id, now)
        entries = [_due_dict(item, schedule) for item, schedule in due]
        return {
            "document_id": document.id,
            "title": document.title,
            "due": entries,
            "due_count": len(entries),
        }

    def save_flashcards(
        self, document_id: int, cards: Iterable[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """Store host-generated flashcards.

        Args:
            document_id: The document's id.
            cards: Mappings with `front` and `back` keys.

        Returns:
            The stored cards with their assigned ids.

        Raises:
            DocumentNotFoundError: If the id is unknown.
            KeyError: If a card lacks a required key.
            pydantic.ValidationError: If a card side is empty.
        """
        inputs = [
            NewFlashcard(front=card["front"], back=card["back"]) for card in cards
        ]
        created = self._repo.add_flashcards(document_id, inputs)
        return [_flashcard_dict(card) for card in created]

    def save_quiz(
        self, document_id: int, questions: Iterable[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """Store host-generated quiz questions.

        Args:
            document_id: The document's id.
            questions: Mappings with `question`, `answer`, `question_type`,
                and optional `options` keys.

        Returns:
            The stored questions with their assigned ids.

        Raises:
            DocumentNotFoundError: If the id is unknown.
            KeyError: If a question lacks a required key.
            ValueError: If a question_type string is invalid.
            pydantic.ValidationError: If a question violates the option rules.
        """
        inputs = [
            NewQuizQuestion(
                question=question["question"],
                answer=question["answer"],
                question_type=parse_question_type(question["question_type"]),
                options=tuple(question.get("options") or ()),
            )
            for question in questions
        ]
        created = self._repo.add_quiz_questions(document_id, inputs)
        return [_quiz_dict(question) for question in created]

    def submit_response(
        self,
        document_id: int,
        item_type: str,
        item_id: int,
        answer: str,
        confidence: str | None = None,
    ) -> dict[str, Any]:
        """Grade and record one answer, then report fresh progress.

        Quiz answers are auto-graded against the stored answer; flashcards
        are self-reported as "correct" or "incorrect".

        Args:
            document_id: The document's id.
            item_type: "flashcard" or "quiz".
            item_id: The answered item's id.
            answer: The submitted answer or self-report.
            confidence: Optional "guessed", "unsure", or "confident".

        Returns:
            is_correct and the updated progress dict.

        Raises:
            DocumentNotFoundError: If the document id is unknown.
            ItemNotFoundError: If the item id is unknown.
            ValueError: If item_type, confidence, or a flashcard self-report
                is invalid.
        """
        parsed_type = parse_item_type(item_type)
        parsed_confidence = parse_confidence(confidence)

        if parsed_type is ItemType.QUIZ:
            question = self._repo.get_quiz_question(document_id, item_id)
            is_correct = normalize_answer(answer) == normalize_answer(question.answer)
        else:
            self._repo.get_flashcard(document_id, item_id)
            is_correct = _parse_self_report(answer)

        self._repo.record_response(
            document_id=document_id,
            item_type=parsed_type,
            item_id=item_id,
            answer=answer,
            is_correct=is_correct,
            confidence=parsed_confidence,
        )
        return {
            "is_correct": is_correct,
            "progress": _session_dict(self._repo.get_session_state(document_id)),
        }

    def get_session_state(self, document_id: int) -> dict[str, Any]:
        """Return a document's mastery buckets and confidence breakdown.

        Args:
            document_id: The document's id.

        Returns:
            mastered, to_review, remaining, in_progress, total, and the
            confidence mapping.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        return _session_dict(self._repo.get_session_state(document_id))

    def delete_document(self, document_id: int) -> dict[str, Any]:
        """Delete a document and everything stored against it.

        Args:
            document_id: The document's id.

        Returns:
            document_id, the deleted title, and deleted=True.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        document = self._repo.delete_document(document_id)
        return {"document_id": document.id, "title": document.title, "deleted": True}

    def export_document(
        self,
        document_id: int,
        output_path: str | None = None,
        include_quiz: bool = True,
    ) -> dict[str, Any]:
        """Write a document's items to an Anki-importable CSV file.

        The file is rendered in full before anything is written, so a
        document with nothing to export leaves no file behind.

        Args:
            document_id: The document's id.
            output_path: Where to write; defaults to
                ``<data_dir>/exports/document-<id>-anki.csv``.
            include_quiz: Whether to include quiz questions.

        Returns:
            document_id, title, path, flashcard_count, and quiz_count.

        Raises:
            DocumentNotFoundError: If the id is unknown.
            ValueError: If the document has no exportable items.
        """
        document = self._repo.get_document(document_id)
        csv_text = render_csv(document, include_quiz=include_quiz)

        target = (
            Path(output_path).expanduser()
            if output_path
            else self._data_dir / "exports" / f"document-{document.id}-anki.csv"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(csv_text, encoding="utf-8")

        return {
            "document_id": document.id,
            "title": document.title,
            "path": str(target),
            "flashcard_count": len(document.flashcards),
            "quiz_count": len(document.quiz_questions) if include_quiz else 0,
        }

    def reset_progress(self, document_id: int) -> dict[str, Any]:
        """Erase a document's answer history, keeping its items.

        Args:
            document_id: The document's id.

        Returns:
            document_id, title, and responses_cleared.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        document: Document = self._repo.get_document(document_id)
        cleared = self._repo.reset_progress(document_id)
        return {
            "document_id": document.id,
            "title": document.title,
            "responses_cleared": cleared,
        }
