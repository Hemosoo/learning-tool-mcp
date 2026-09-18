"""File-backed repository: the single boundary between logic and storage."""

from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from learning_tool.scheduling.sm2 import ItemSchedule, compute_schedule
from learning_tool.storage.models import (
    Confidence,
    Document,
    Flashcard,
    ItemType,
    QuestionType,
    QuizQuestion,
    Response,
)

MASTERY_THRESHOLD = 2
"""Total correct answers after which an item counts as mastered."""

UNREPORTED_CONFIDENCE = "unreported"
"""Confidence key for an answered item whose latest response reported none."""

CONFIDENCE_KEYS = (*(level.value for level in Confidence), UNREPORTED_CONFIDENCE)
"""Every key the confidence breakdown carries, always all present."""

_DOCUMENTS_DIRNAME = "documents"
"""Name of the subdirectory holding one JSON file per document."""

_TEMP_SUFFIX = ".tmp"
"""Suffix of in-progress writes; not `.json`, so id discovery ignores them."""


class DocumentNotFoundError(LookupError):
    """Raised when no document exists for a requested id."""


class ItemNotFoundError(LookupError):
    """Raised when no flashcard or quiz question exists for a requested id."""


@dataclass(frozen=True)
class NewFlashcard:
    """An id-less flashcard to be created.

    Attributes:
        front: Prompt side.
        back: Answer side.
    """

    front: str
    back: str


@dataclass(frozen=True)
class NewQuizQuestion:
    """An id-less quiz question to be created.

    Attributes:
        question: The question text.
        answer: The correct answer.
        question_type: Which quiz format the question uses.
        options: Choices for multiple-choice questions.
    """

    question: str
    answer: str
    question_type: QuestionType
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionState:
    """Counts of items per mastery bucket, plus a confidence breakdown.

    Attributes:
        mastered: Items answered correctly at least the threshold times.
        to_review: Items whose last answer was incorrect.
        remaining: Items never answered.
        in_progress: Answered, not mastered, last answer correct.
        total: Flashcards plus quiz questions.
        confidence: Answered items counted by their latest response's
            confidence, keyed by every value in CONFIDENCE_KEYS. The counts
            sum to total minus remaining.
    """

    mastered: int
    to_review: int
    remaining: int
    in_progress: int
    total: int
    confidence: dict[str, int]


class Repository:
    """Stores documents as one JSON file each under a data directory."""

    def __init__(self, data_dir: Path) -> None:
        """Bind the repository to a data directory without touching disk.

        Args:
            data_dir: Root directory for stored data.
        """
        self._data_dir = Path(data_dir)
        self._documents_dir = self._data_dir / _DOCUMENTS_DIRNAME

    @property
    def documents_dir(self) -> Path:
        """Directory holding the per-document JSON files."""
        return self._documents_dir

    # -- storage primitives -------------------------------------------------

    def _document_path(self, document_id: int) -> Path:
        """Return the file path for a document id.

        Args:
            document_id: The document's id.

        Returns:
            The path of that document's JSON file.
        """
        return self._documents_dir / f"{document_id}.json"

    def _existing_ids(self) -> list[int]:
        """Discover stored document ids from the directory listing.

        Returns:
            Ascending ids; non-numeric filename stems are skipped.
        """
        if not self._documents_dir.is_dir():
            return []
        ids: list[int] = []
        for path in self._documents_dir.glob("*.json"):
            try:
                ids.append(int(path.stem))
            except ValueError:
                continue
        return sorted(ids)

    def _save(self, document: Document) -> None:
        """Persist a document atomically.

        Args:
            document: The document to write.

        Raises:
            BaseException: Whatever the write or replace raised, after the
                temporary file has been cleaned up.
        """
        payload = document.model_dump_json(indent=2)
        self._documents_dir.mkdir(parents=True, exist_ok=True)
        target = self._document_path(document.id)

        handle, temp_name = tempfile.mkstemp(
            dir=self._documents_dir, prefix=f"{document.id}.", suffix=_TEMP_SUFFIX
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
            os.replace(temp_path, target)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

    def _load(self, document_id: int) -> Document:
        """Read and validate one document from disk.

        Args:
            document_id: The document's id.

        Returns:
            The parsed document.

        Raises:
            DocumentNotFoundError: If no file exists for the id.
            pydantic.ValidationError: If the stored JSON is invalid.
        """
        path = self._document_path(document_id)
        if not path.is_file():
            raise DocumentNotFoundError(f"No document with id {document_id}")
        return Document.model_validate_json(path.read_text(encoding="utf-8"))

    # -- documents ----------------------------------------------------------

    def create_document(
        self, title: str, source_path: str, concepts: Sequence[str]
    ) -> Document:
        """Create and persist a new document.

        Args:
            title: Human-readable title.
            source_path: Path the material came from.
            concepts: Extracted text chunks.

        Returns:
            The stored document, with its assigned id.
        """
        existing = self._existing_ids()
        document = Document(
            id=(existing[-1] + 1) if existing else 1,
            title=title,
            source_path=source_path,
            concepts=list(concepts),
        )
        self._save(document)
        return document

    def get_document(self, document_id: int) -> Document:
        """Return a stored document.

        Args:
            document_id: The document's id.

        Returns:
            The parsed document.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        return self._load(document_id)

    def list_documents(self) -> list[Document]:
        """Return every stored document, ascending by id.

        Returns:
            All documents; an empty list when the store is empty.
        """
        return [self._load(document_id) for document_id in self._existing_ids()]

    def delete_document(self, document_id: int) -> Document:
        """Delete a document, returning what was removed.

        Args:
            document_id: The document's id.

        Returns:
            The document as it was before deletion.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        document = self._load(document_id)
        self._document_path(document_id).unlink()
        return document

    def reset_progress(self, document_id: int) -> int:
        """Clear a document's answer history, keeping its items.

        Args:
            document_id: The document's id.

        Returns:
            How many responses were cleared.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        document = self._load(document_id)
        cleared = len(document.responses)
        document.responses = []
        self._save(document)
        return cleared

    # -- items --------------------------------------------------------------

    def add_flashcards(
        self, document_id: int, cards: Iterable[NewFlashcard]
    ) -> list[Flashcard]:
        """Append flashcards to a document in one save.

        Args:
            document_id: The document's id.
            cards: The id-less cards to store.

        Returns:
            The created flashcards with their assigned ids.

        Raises:
            DocumentNotFoundError: If the id is unknown.
        """
        document = self._load(document_id)
        created: list[Flashcard] = []
        for card in cards:
            created.append(
                Flashcard(id=document.next_item_id, front=card.front, back=card.back)
            )
            document.next_item_id += 1
        document.flashcards.extend(created)
        self._save(document)
        return created

    def add_quiz_questions(
        self, document_id: int, questions: Iterable[NewQuizQuestion]
    ) -> list[QuizQuestion]:
        """Append quiz questions to a document in one save.

        All questions are constructed (and therefore validated) before
        anything is written, so an invalid question persists nothing.

        Args:
            document_id: The document's id.
            questions: The id-less questions to store.

        Returns:
            The created questions with their assigned ids.

        Raises:
            DocumentNotFoundError: If the id is unknown.
            pydantic.ValidationError: If any question violates the model rules.
        """
        document = self._load(document_id)
        next_id = document.next_item_id
        created: list[QuizQuestion] = []
        for question in questions:
            created.append(
                QuizQuestion(
                    id=next_id,
                    question=question.question,
                    answer=question.answer,
                    question_type=question.question_type,
                    options=list(question.options),
                )
            )
            next_id += 1
        document.next_item_id = next_id
        document.quiz_questions.extend(created)
        self._save(document)
        return created

    def get_flashcard(self, document_id: int, item_id: int) -> Flashcard:
        """Return one flashcard of a document.

        Args:
            document_id: The document's id.
            item_id: The flashcard's id.

        Returns:
            The flashcard.

        Raises:
            DocumentNotFoundError: If the document id is unknown.
            ItemNotFoundError: If the document has no such flashcard.
        """
        document = self._load(document_id)
        for card in document.flashcards:
            if card.id == item_id:
                return card
        raise ItemNotFoundError(
            f"No flashcard with id {item_id} in document {document_id}"
        )

    def get_quiz_question(self, document_id: int, item_id: int) -> QuizQuestion:
        """Return one quiz question of a document.

        Args:
            document_id: The document's id.
            item_id: The question's id.

        Returns:
            The quiz question.

        Raises:
            DocumentNotFoundError: If the document id is unknown.
            ItemNotFoundError: If the document has no such question.
        """
        document = self._load(document_id)
        for question in document.quiz_questions:
            if question.id == item_id:
                return question
        raise ItemNotFoundError(
            f"No quiz question with id {item_id} in document {document_id}"
        )

    # -- responses and derived state ---------------------------------------

    def record_response(
        self,
        document_id: int,
        item_type: ItemType,
        item_id: int,
        answer: str,
        is_correct: bool,
        confidence: Confidence | None = None,
    ) -> Response:
        """Append one answer to a document's history.

        Args:
            document_id: The document's id.
            item_type: Whether the item is a flashcard or quiz question.
            item_id: The answered item's id.
            answer: The raw submitted text or self-report.
            is_correct: The graded result.
            confidence: Optional self-reported confidence.

        Returns:
            The stored response.

        Raises:
            DocumentNotFoundError: If the document id is unknown.
        """
        document = self._load(document_id)
        response = Response(
            item_type=item_type,
            item_id=item_id,
            answer=answer,
            is_correct=is_correct,
            confidence=confidence,
        )
        document.responses.append(response)
        self._save(document)
        return response

    def get_due_items(
        self, document_id: int, now: datetime
    ) -> list[tuple[Flashcard | QuizQuestion, ItemSchedule]]:
        """Return the document's due items, most overdue first.

        Args:
            document_id: The document's id.
            now: Timezone-aware evaluation instant.

        Returns:
            Pairs of item and schedule: previously reviewed items ascending
            by next review, then never-reviewed items in document order.

        Raises:
            DocumentNotFoundError: If the document id is unknown.
            ValueError: If ``now`` is timezone-naive.
        """
        document = self._load(document_id)
        grouped = _group_responses(document.responses)

        reviewed: list[tuple[datetime, Flashcard | QuizQuestion, ItemSchedule]] = []
        never_reviewed: list[tuple[Flashcard | QuizQuestion, ItemSchedule]] = []
        for item_type, item in _iter_items(document):
            schedule = compute_schedule(grouped[(item_type, item.id)], now)
            if not schedule.is_due:
                continue
            if schedule.next_review is None:
                never_reviewed.append((item, schedule))
            else:
                reviewed.append((schedule.next_review, item, schedule))

        reviewed.sort(key=lambda entry: entry[0])
        overdue = [(item, schedule) for _, item, schedule in reviewed]
        return overdue + never_reviewed

    def get_session_state(self, document_id: int) -> SessionState:
        """Bucket a document's items by mastery.

        Args:
            document_id: The document's id.

        Returns:
            The counts per bucket and the confidence breakdown; the four
            buckets sum to the total, and the confidence counts sum to the
            answered items.

        Raises:
            DocumentNotFoundError: If the document id is unknown.
        """
        document = self._load(document_id)
        grouped = _group_responses(document.responses)

        mastered = to_review = remaining = in_progress = total = 0
        confidence = dict.fromkeys(CONFIDENCE_KEYS, 0)
        for item_type, item in _iter_items(document):
            total += 1
            history = grouped[(item_type, item.id)]
            if not history:
                remaining += 1
                continue

            latest = history[-1].confidence
            key = UNREPORTED_CONFIDENCE if latest is None else latest.value
            confidence[key] += 1

            if _correct_count(history) >= MASTERY_THRESHOLD:
                mastered += 1
            elif not history[-1].is_correct:
                to_review += 1
            else:
                in_progress += 1

        return SessionState(
            mastered=mastered,
            to_review=to_review,
            remaining=remaining,
            in_progress=in_progress,
            total=total,
            confidence=confidence,
        )


def _correct_count(responses: Sequence[Response]) -> int:
    """Count the correct answers in a response history.

    Args:
        responses: The item's responses.

    Returns:
        How many of them were graded correct.
    """
    return sum(1 for response in responses if response.is_correct)


def _iter_items(
    document: Document,
) -> list[tuple[ItemType, Flashcard | QuizQuestion]]:
    """List a document's items, flashcards first, in document order.

    Args:
        document: The document to walk.

    Returns:
        Pairs of item type and item.
    """
    items: list[tuple[ItemType, Flashcard | QuizQuestion]] = [
        (ItemType.FLASHCARD, card) for card in document.flashcards
    ]
    items.extend((ItemType.QUIZ, question) for question in document.quiz_questions)
    return items


def _group_responses(
    responses: Sequence[Response],
) -> dict[tuple[ItemType, int], list[Response]]:
    """Group responses by the item they answer, preserving order.

    Args:
        responses: The document's responses in chronological order.

    Returns:
        A mapping from (item type, item id) to that item's responses,
        oldest first; missing keys yield an empty list.
    """
    grouped: dict[tuple[ItemType, int], list[Response]] = defaultdict(list)
    for response in responses:
        grouped[(response.item_type, response.item_id)].append(response)
    return grouped
