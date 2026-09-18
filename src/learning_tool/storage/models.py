"""Pydantic domain models and enums; also the on-disk JSON format."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        The current instant in UTC.
    """
    return datetime.now(timezone.utc)


class ItemType(str, Enum):
    """The kind of study item a response refers to."""

    FLASHCARD = "flashcard"
    QUIZ = "quiz"


class QuestionType(str, Enum):
    """Supported quiz question formats."""

    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"


class Confidence(str, Enum):
    """Optional self-reported confidence attached to a response."""

    GUESSED = "guessed"
    UNSURE = "unsure"
    CONFIDENT = "confident"


class Flashcard(BaseModel):
    """A two-sided study card.

    Attributes:
        id: Item id, assigned by the repository.
        front: Prompt side, non-empty.
        back: Answer side, non-empty.
    """

    id: int
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)


class QuizQuestion(BaseModel):
    """A quiz question, multiple-choice or short-answer.

    Attributes:
        id: Item id, assigned by the repository.
        question: The question text, non-empty.
        answer: The correct answer, non-empty.
        question_type: Which quiz format this question uses.
        options: Choices for multiple-choice questions; empty otherwise.
    """

    id: int
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    question_type: QuestionType
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_options(self) -> QuizQuestion:
        """Enforce the option rules for each question type.

        Returns:
            The validated question.

        Raises:
            ValueError: If a multiple-choice question has fewer than two
                options or an answer that is not one of them, or if a
                short-answer question carries options.
        """
        if self.question_type is QuestionType.MULTIPLE_CHOICE:
            if len(self.options) < 2:
                raise ValueError("multiple_choice question needs at least 2 options")
            if self.answer not in self.options:
                raise ValueError(
                    "multiple_choice answer must be exactly one of the options"
                )
        elif self.options:
            raise ValueError("short_answer question must not have options")
        return self


class Response(BaseModel):
    """One user answer to a single study item.

    Attributes:
        item_type: Whether the answered item is a flashcard or quiz question.
        item_id: The item's id, scoped by item_type.
        answer: The raw submitted text (or self-report).
        is_correct: The graded result.
        confidence: Optional self-reported confidence.
        created_at: Timezone-aware UTC timestamp of the answer.
    """

    item_type: ItemType
    item_id: int
    answer: str
    is_correct: bool
    confidence: Confidence | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Document(BaseModel):
    """A study document: the aggregate root and one JSON file on disk.

    Attributes:
        id: Document id, assigned by the repository.
        title: Human-readable title.
        source_path: Path the material was ingested from.
        concepts: Extracted text chunks.
        flashcards: Saved flashcards.
        quiz_questions: Saved quiz questions.
        responses: Answer history in chronological (insertion) order.
        next_item_id: Shared id counter for flashcards and quiz questions.
        created_at: Timezone-aware UTC creation timestamp.
    """

    id: int
    title: str
    source_path: str
    concepts: list[str] = Field(default_factory=list)
    flashcards: list[Flashcard] = Field(default_factory=list)
    quiz_questions: list[QuizQuestion] = Field(default_factory=list)
    responses: list[Response] = Field(default_factory=list)
    next_item_id: int = 1
    created_at: datetime = Field(default_factory=utc_now)
