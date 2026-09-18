"""Tests for the study service (spec 07)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from learning_tool.ingestion.pdf import PdfIngestionError
from learning_tool.service import StudyService, normalize_answer
from learning_tool.storage.repository import (
    MASTERY_THRESHOLD,
    DocumentNotFoundError,
    ItemNotFoundError,
    Repository,
)


@pytest.fixture
def service(tmp_path: Path) -> StudyService:
    """Return a service rooted at the test's temporary directory."""
    return StudyService(tmp_path / "data")


@pytest.fixture
def document(service: StudyService, pdf_factory) -> int:
    """Ingest a small PDF and return its document id."""
    path = pdf_factory(["Kinetic energy is one half m v squared."], name="physics.pdf")
    return service.ingest_material(str(path))["document_id"]


def test_ingest_returns_id_title_and_concept_count(
    service: StudyService, pdf_factory
) -> None:
    """Ingestion reports what it stored."""
    path = pdf_factory(["First fact here."], name="notes.pdf")

    result = service.ingest_material(str(path), title="My Notes")

    assert result == {"document_id": 1, "title": "My Notes", "concept_count": 1}


def test_ingest_without_title_uses_the_pdf_file_name(
    service: StudyService, pdf_factory
) -> None:
    """The file name is the default title."""
    path = pdf_factory(["Body text."], name="chapter-3.pdf")

    assert service.ingest_material(str(path))["title"] == "chapter-3.pdf"


def test_ingest_propagates_ingestion_errors(
    service: StudyService, tmp_path: Path
) -> None:
    """Missing PDFs surface as the ingestion error type."""
    with pytest.raises(PdfIngestionError):
        service.ingest_material(str(tmp_path / "absent.pdf"))


def test_get_material_returns_the_stored_concepts(
    service: StudyService, document: int
) -> None:
    """Material comes back as plain strings under the documented keys."""
    result = service.get_material(document)

    assert set(result) == {"document_id", "title", "concepts"}
    assert result["document_id"] == document
    assert result["concepts"] == ["Kinetic energy is one half m v squared."]


def test_list_documents_shapes_counts_and_iso_timestamps(
    service: StudyService, document: int
) -> None:
    """Listing carries counts and an ISO-8601 created_at."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])
    service.save_quiz(
        document, [{"question": "q", "answer": "a", "question_type": "short_answer"}]
    )

    entries = service.list_documents()

    assert len(entries) == 1
    entry = entries[0]
    assert set(entry) == {
        "document_id",
        "title",
        "concept_count",
        "flashcard_count",
        "quiz_count",
        "created_at",
    }
    assert (entry["flashcard_count"], entry["quiz_count"]) == (1, 1)
    assert datetime.fromisoformat(entry["created_at"]).tzinfo is not None


def test_list_documents_is_empty_when_nothing_is_stored(service: StudyService) -> None:
    """An empty store lists nothing."""
    assert service.list_documents() == []


def test_save_flashcards_returns_stored_cards_with_ids(
    service: StudyService, document: int
) -> None:
    """Saved cards come back with assigned ids."""
    saved = service.save_flashcards(
        document, [{"front": "Force?", "back": "ma"}, {"front": "Work?", "back": "Fd"}]
    )

    assert saved == [
        {"id": 1, "front": "Force?", "back": "ma"},
        {"id": 2, "front": "Work?", "back": "Fd"},
    ]


def test_save_flashcards_rejects_a_card_missing_a_key(
    service: StudyService, document: int
) -> None:
    """A card without both sides is a KeyError, and nothing is stored."""
    with pytest.raises(KeyError):
        service.save_flashcards(document, [{"front": "only front"}])

    assert service.get_study_items(document)["flashcards"] == []


def test_save_quiz_returns_stored_questions_with_ids(
    service: StudyService, document: int
) -> None:
    """Saved questions come back with ids and string question types."""
    saved = service.save_quiz(
        document,
        [
            {
                "question": "Unit of force?",
                "answer": "newton",
                "question_type": "multiple_choice",
                "options": ["newton", "joule"],
            },
            {
                "question": "Define work",
                "answer": "F d",
                "question_type": "short_answer",
            },
        ],
    )

    assert saved[0] == {
        "id": 1,
        "question": "Unit of force?",
        "options": ["newton", "joule"],
        "answer": "newton",
        "question_type": "multiple_choice",
    }
    assert saved[1]["options"] == []
    assert saved[1]["question_type"] == "short_answer"


def test_save_quiz_rejects_an_invalid_question_type(
    service: StudyService, document: int
) -> None:
    """An unknown question type names the valid values."""
    with pytest.raises(
        ValueError, match="question_type must be one of: multiple_choice, short_answer"
    ):
        service.save_quiz(
            document, [{"question": "q", "answer": "a", "question_type": "essay"}]
        )


def test_save_quiz_rejects_option_rule_violations(
    service: StudyService, document: int
) -> None:
    """Model validation still guards the batch at this layer."""
    with pytest.raises(ValidationError):
        service.save_quiz(
            document,
            [
                {
                    "question": "q",
                    "answer": "z",
                    "question_type": "multiple_choice",
                    "options": ["a", "b"],
                }
            ],
        )

    assert service.get_study_items(document)["quiz_questions"] == []


def test_get_study_items_includes_answers(service: StudyService, document: int) -> None:
    """Study items deliberately expose the stored quiz answers."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])
    service.save_quiz(
        document, [{"question": "q", "answer": "a", "question_type": "short_answer"}]
    )

    result = service.get_study_items(document)

    assert set(result) == {"document_id", "title", "flashcards", "quiz_questions"}
    assert result["flashcards"] == [{"id": 1, "front": "f", "back": "b"}]
    assert result["quiz_questions"][0]["answer"] == "a"


def test_normalize_answer_collapses_case_and_whitespace() -> None:
    """Normalization lowercases, trims, and collapses whitespace runs."""
    assert normalize_answer("  The   Second\tLaw \n") == "the second law"


def test_quiz_grading_ignores_case_and_whitespace(
    service: StudyService, document: int
) -> None:
    """An answer differing only in case or spacing is correct."""
    service.save_quiz(
        document,
        [
            {
                "question": "Newton's 2nd?",
                "answer": "F = m a",
                "question_type": "short_answer",
            }
        ],
    )

    result = service.submit_response(document, "quiz", 1, "  f =   M A ")

    assert result["is_correct"] is True


def test_quiz_grading_marks_a_different_answer_incorrect(
    service: StudyService, document: int
) -> None:
    """A genuinely different answer is graded incorrect."""
    service.save_quiz(
        document,
        [{"question": "q", "answer": "newton", "question_type": "short_answer"}],
    )

    assert service.submit_response(document, "quiz", 1, "joule")["is_correct"] is False


def test_flashcard_self_report_is_accepted_case_insensitively(
    service: StudyService, document: int
) -> None:
    """ "Correct"/"incorrect" are accepted in any casing."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])

    assert service.submit_response(document, "flashcard", 1, " CORRECT ")["is_correct"]
    assert not service.submit_response(document, "flashcard", 1, "Incorrect")[
        "is_correct"
    ]


def test_invalid_flashcard_self_report_raises_and_records_nothing(
    service: StudyService, document: int
) -> None:
    """Free text is not a valid self-report."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])

    with pytest.raises(ValueError, match="must be one of: correct, incorrect"):
        service.submit_response(document, "flashcard", 1, "sort of")

    assert service.get_session_state(document)["remaining"] == 1


def test_submitting_for_an_unknown_item_raises_before_recording(
    service: StudyService, document: int
) -> None:
    """A flashcard must exist before its self-report is even parsed."""
    with pytest.raises(ItemNotFoundError):
        service.submit_response(document, "flashcard", 99, "correct")
    with pytest.raises(ItemNotFoundError):
        service.submit_response(document, "quiz", 99, "anything")


def test_invalid_item_type_lists_the_valid_values(
    service: StudyService, document: int
) -> None:
    """The item-type parser names what it accepts."""
    with pytest.raises(ValueError, match="item_type must be one of: flashcard, quiz"):
        service.submit_response(document, "card", 1, "correct")


def test_invalid_confidence_lists_the_valid_values(
    service: StudyService, document: int
) -> None:
    """The confidence parser names what it accepts."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])

    with pytest.raises(
        ValueError, match="confidence must be one of: guessed, unsure, confident"
    ):
        service.submit_response(document, "flashcard", 1, "correct", confidence="meh")


def test_submit_returns_progress_computed_after_the_new_response(
    service: StudyService, document: int
) -> None:
    """The returned progress includes the answer just submitted."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])

    first = service.submit_response(document, "flashcard", 1, "correct")
    assert first["progress"] == {
        "mastered": 0,
        "to_review": 0,
        "remaining": 0,
        "in_progress": 1,
        "total": 1,
        "confidence": {"guessed": 0, "unsure": 0, "confident": 0, "unreported": 1},
    }

    for _ in range(MASTERY_THRESHOLD - 1):
        latest = service.submit_response(
            document, "flashcard", 1, "correct", confidence="confident"
        )
    assert latest["progress"]["mastered"] == 1


def test_get_session_state_exposes_the_buckets_and_confidence(
    service: StudyService, document: int
) -> None:
    """Session state is the five counts plus the confidence breakdown."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])

    assert service.get_session_state(document) == {
        "mastered": 0,
        "to_review": 0,
        "remaining": 1,
        "in_progress": 0,
        "total": 1,
        "confidence": {"guessed": 0, "unsure": 0, "confident": 0, "unreported": 0},
    }


def test_confidence_counts_the_latest_report_per_item(
    service: StudyService, document: int
) -> None:
    """Each answered item is counted once, by its most recent answer."""
    service.save_flashcards(
        document, [{"front": "a", "back": "b"}, {"front": "c", "back": "d"}]
    )
    service.submit_response(document, "flashcard", 1, "correct", confidence="guessed")
    service.submit_response(document, "flashcard", 1, "correct", confidence="confident")
    service.submit_response(document, "flashcard", 2, "incorrect")

    state = service.get_session_state(document)

    assert state["confidence"] == {
        "guessed": 0,
        "unsure": 0,
        "confident": 1,
        "unreported": 1,
    }
    assert sum(state["confidence"].values()) == state["total"] - state["remaining"]


def test_submit_response_progress_carries_the_confidence_breakdown(
    service: StudyService, document: int
) -> None:
    """The breakdown propagates through submit_response with no extra call."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])

    result = service.submit_response(
        document, "flashcard", 1, "correct", confidence="unsure"
    )

    assert result["progress"]["confidence"]["unsure"] == 1


def test_due_items_carry_schedule_and_item_fields(
    service: StudyService, document: int
) -> None:
    """Never-reviewed items are due with null next_review."""
    service.save_flashcards(document, [{"front": "Force?", "back": "ma"}])
    service.save_quiz(
        document,
        [
            {
                "question": "Unit?",
                "answer": "newton",
                "question_type": "multiple_choice",
                "options": ["newton", "joule"],
            }
        ],
    )

    result = service.get_due_items(document)

    assert set(result) == {"document_id", "title", "due", "due_count"}
    assert result["due_count"] == 2
    card, question = result["due"]
    assert card == {
        "item_type": "flashcard",
        "item_id": 1,
        "repetitions": 0,
        "interval_days": 0,
        "next_review": None,
        "front": "Force?",
        "back": "ma",
    }
    assert question["item_type"] == "quiz"
    assert question["options"] == ["newton", "joule"]
    assert question["answer"] == "newton"
    assert question["question_type"] == "multiple_choice"


def test_answered_items_drop_out_of_the_due_list(
    service: StudyService, document: int
) -> None:
    """A correct answer schedules the item into the future."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])
    service.submit_response(document, "flashcard", 1, "correct")

    result = service.get_due_items(document)

    assert result["due"] == []
    assert result["due_count"] == 0


def test_overdue_items_carry_an_iso_next_review_and_come_first(
    service: StudyService, document: int, tmp_path: Path
) -> None:
    """Back-dated reviews resurface as overdue, ordered ahead of new items."""
    service.save_flashcards(
        document, [{"front": "overdue", "back": "b"}, {"front": "never", "back": "b"}]
    )
    service.submit_response(document, "flashcard", 1, "correct")

    repo = Repository(tmp_path / "data")
    stored = repo.get_document(document)
    stored.responses = [
        response.model_copy(
            update={"created_at": datetime.now(timezone.utc) - timedelta(days=30)}
        )
        for response in stored.responses
    ]
    (repo.documents_dir / f"{document}.json").write_text(
        stored.model_dump_json(indent=2), encoding="utf-8"
    )

    due = service.get_due_items(document)["due"]

    assert [entry["item_id"] for entry in due] == [1, 2]
    assert datetime.fromisoformat(due[0]["next_review"]).tzinfo is not None
    assert due[0]["repetitions"] == 1
    assert due[0]["interval_days"] == 1
    assert due[1]["next_review"] is None


def test_now_is_resolved_once_as_timezone_aware_utc() -> None:
    """The service is the only layer that reads the clock, and it reads UTC."""
    now = StudyService._now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_delete_document_returns_the_title_and_removes_it(
    service: StudyService, document: int
) -> None:
    """Deletion reports the title so the host can name what went."""
    result = service.delete_document(document)

    assert result == {"document_id": document, "title": "physics.pdf", "deleted": True}
    with pytest.raises(DocumentNotFoundError):
        service.get_material(document)


def test_reset_progress_reports_the_cleared_count_and_keeps_items(
    service: StudyService, document: int
) -> None:
    """Reset clears history only."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])
    service.submit_response(document, "flashcard", 1, "correct")

    result = service.reset_progress(document)

    assert result == {
        "document_id": document,
        "title": "physics.pdf",
        "responses_cleared": 1,
    }
    assert service.get_session_state(document)["remaining"] == 1
    assert service.get_study_items(document)["flashcards"] == [
        {"id": 1, "front": "f", "back": "b"}
    ]


def test_export_writes_to_the_default_path_and_reports_counts(
    service: StudyService, document: int, tmp_path: Path
) -> None:
    """The default export lands under the data directory."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])
    service.save_quiz(
        document, [{"question": "q", "answer": "a", "question_type": "short_answer"}]
    )

    result = service.export_document(document)

    expected = tmp_path / "data" / "exports" / f"document-{document}-anki.csv"
    assert result == {
        "document_id": document,
        "title": "physics.pdf",
        "path": str(expected),
        "flashcard_count": 1,
        "quiz_count": 1,
    }
    assert expected.is_file()
    assert expected.read_text().startswith("#separator:Comma")


def test_export_honours_an_explicit_path_and_creates_parents(
    service: StudyService, document: int, tmp_path: Path
) -> None:
    """A chosen path is expanded and its directories created."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])
    target = tmp_path / "nested" / "deeper" / "cards.csv"

    result = service.export_document(document, output_path=str(target))

    assert result["path"] == str(target)
    assert target.is_file()


def test_export_excluding_quiz_reports_zero_quiz_count(
    service: StudyService, document: int
) -> None:
    """Counts describe what was written, not what was stored."""
    service.save_flashcards(document, [{"front": "f", "back": "b"}])
    service.save_quiz(
        document, [{"question": "q", "answer": "a", "question_type": "short_answer"}]
    )

    result = service.export_document(document, include_quiz=False)

    assert result["quiz_count"] == 0
    assert result["flashcard_count"] == 1
    assert "q" not in Path(result["path"]).read_text()


def test_export_of_an_empty_document_writes_nothing(
    service: StudyService, document: int, tmp_path: Path
) -> None:
    """A failed export leaves no file behind."""
    target = tmp_path / "exports" / "empty.csv"

    with pytest.raises(ValueError, match="no items to export"):
        service.export_document(document, output_path=str(target))

    assert not target.exists()


def test_export_of_an_unknown_document_raises_the_lookup_error(
    service: StudyService,
) -> None:
    """Unknown ids fail before any rendering."""
    with pytest.raises(DocumentNotFoundError):
        service.export_document(404)


def test_unknown_document_id_raises_everywhere(service: StudyService) -> None:
    """Every document-scoped service call rejects unknown ids."""
    for call in (
        lambda: service.get_material(42),
        lambda: service.get_study_items(42),
        lambda: service.get_due_items(42),
        lambda: service.get_session_state(42),
        lambda: service.save_flashcards(42, []),
        lambda: service.save_quiz(42, []),
        lambda: service.delete_document(42),
        lambda: service.reset_progress(42),
        lambda: service.submit_response(42, "flashcard", 1, "correct"),
    ):
        with pytest.raises(DocumentNotFoundError):
            call()
