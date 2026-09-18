"""Tests for the domain models (spec 03)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from learning_tool.storage.models import (
    Confidence,
    Document,
    Flashcard,
    ItemType,
    QuestionType,
    QuizQuestion,
    Response,
)


def test_enums_serialize_as_their_string_values() -> None:
    """Enum members carry their wire strings."""
    assert ItemType.FLASHCARD.value == "flashcard"
    assert ItemType.QUIZ.value == "quiz"
    assert QuestionType.MULTIPLE_CHOICE.value == "multiple_choice"
    assert QuestionType.SHORT_ANSWER.value == "short_answer"
    assert [c.value for c in Confidence] == ["guessed", "unsure", "confident"]


def test_document_round_trips_through_json_without_loss() -> None:
    """A fully populated document survives serialize/parse unchanged."""
    document = Document(
        id=3,
        title="Physics",
        source_path="/tmp/physics.pdf",
        concepts=["Newton's laws", "Momentum"],
        flashcards=[Flashcard(id=1, front="F=?", back="ma")],
        quiz_questions=[
            QuizQuestion(
                id=2,
                question="Unit of force?",
                answer="newton",
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=["newton", "joule"],
            )
        ],
        responses=[
            Response(
                item_type=ItemType.QUIZ,
                item_id=2,
                answer="newton",
                is_correct=True,
                confidence=Confidence.CONFIDENT,
                created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            )
        ],
        next_item_id=3,
    )

    restored = Document.model_validate_json(document.model_dump_json())

    assert restored == document
    assert restored.responses[0].created_at.tzinfo is not None
    assert restored.responses[0].created_at == document.responses[0].created_at


def test_flashcard_rejects_empty_sides() -> None:
    """Both flashcard sides require at least one character."""
    with pytest.raises(ValidationError):
        Flashcard(id=1, front="", back="back")
    with pytest.raises(ValidationError):
        Flashcard(id=1, front="front", back="")


def test_multiple_choice_needs_at_least_two_options() -> None:
    """A multiple-choice question with one option is rejected."""
    with pytest.raises(ValidationError, match="at least 2 options"):
        QuizQuestion(
            id=1,
            question="Q",
            answer="a",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=["a"],
        )


def test_multiple_choice_answer_must_be_one_of_the_options() -> None:
    """The stored answer has to appear verbatim among the options."""
    with pytest.raises(ValidationError, match="exactly one of the options"):
        QuizQuestion(
            id=1,
            question="Q",
            answer="c",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=["a", "b"],
        )


def test_short_answer_must_not_carry_options() -> None:
    """Options are meaningless for short-answer questions."""
    with pytest.raises(ValidationError, match="must not have options"):
        QuizQuestion(
            id=1,
            question="Q",
            answer="a",
            question_type=QuestionType.SHORT_ANSWER,
            options=["a", "b"],
        )


def test_stored_json_violating_constraints_fails_on_load() -> None:
    """Invalid persisted JSON raises rather than yielding a partial object."""
    payload = (
        '{"id": 1, "title": "t", "source_path": "p", "quiz_questions": '
        '[{"id": 1, "question": "Q", "answer": "z", '
        '"question_type": "multiple_choice", "options": ["a", "b"]}]}'
    )

    with pytest.raises(ValidationError):
        Document.model_validate_json(payload)


def test_response_defaults_to_timezone_aware_utc_now() -> None:
    """An unstamped response is stamped with aware UTC now."""
    before = datetime.now(timezone.utc)

    response = Response(
        item_type=ItemType.FLASHCARD, item_id=1, answer="x", is_correct=True
    )

    assert response.created_at.tzinfo is not None
    assert response.created_at.utcoffset() == timezone.utc.utcoffset(None)
    assert before <= response.created_at <= datetime.now(timezone.utc)
    assert response.confidence is None


def test_document_defaults_are_empty_with_item_counter_at_one() -> None:
    """A fresh document starts empty with next_item_id 1."""
    document = Document(id=1, title="t", source_path="p")

    assert document.concepts == []
    assert document.flashcards == []
    assert document.quiz_questions == []
    assert document.responses == []
    assert document.next_item_id == 1
    assert document.created_at.tzinfo is not None
