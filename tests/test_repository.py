"""Tests for the file-backed repository (spec 06)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from learning_tool.storage.models import (
    Confidence,
    ItemType,
    QuestionType,
    Response,
)
from learning_tool.storage.repository import (
    CONFIDENCE_KEYS,
    MASTERY_THRESHOLD,
    DocumentNotFoundError,
    ItemNotFoundError,
    NewFlashcard,
    NewQuizQuestion,
    Repository,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_path: Path) -> Repository:
    """Return a repository rooted at the test's temporary directory."""
    return Repository(tmp_path / "data")


def short_answer(question: str, answer: str) -> NewQuizQuestion:
    """Build a short-answer question input.

    Args:
        question: The question text.
        answer: The expected answer.

    Returns:
        The creation input.
    """
    return NewQuizQuestion(
        question=question, answer=answer, question_type=QuestionType.SHORT_ANSWER
    )


def seed_history(repo: Repository, document_id: int, responses) -> None:
    """Write a back-dated answer history straight into the stored file.

    The repository stamps responses at construction, so history with past
    timestamps is seeded through the file the repository itself wrote.

    Args:
        repo: The repository under test.
        document_id: Which document to seed.
        responses: The responses to store, oldest first.
    """
    document = repo.get_document(document_id)
    document.responses = list(responses)
    (repo.documents_dir / f"{document_id}.json").write_text(
        document.model_dump_json(indent=2), encoding="utf-8"
    )


def test_construction_creates_no_directory(tmp_path: Path) -> None:
    """The documents directory is created lazily, on first write."""
    repo = Repository(tmp_path / "data")

    assert not repo.documents_dir.exists()
    assert repo.list_documents() == []
    assert not repo.documents_dir.exists()


def test_first_document_gets_id_one_and_its_own_file(repo: Repository) -> None:
    """Creating writes <id>.json under the documents directory."""
    document = repo.create_document("Physics", "/tmp/p.pdf", ["chunk one"])

    path = repo.documents_dir / "1.json"
    assert document.id == 1
    assert path.is_file()
    assert json.loads(path.read_text())["concepts"] == ["chunk one"]


def test_next_id_is_highest_existing_plus_one(repo: Repository) -> None:
    """Ids continue past the highest stored id, including after deletes."""
    repo.create_document("A", "a.pdf", [])
    second = repo.create_document("B", "b.pdf", [])
    repo.delete_document(second.id)

    assert repo.create_document("C", "c.pdf", []).id == 2

    (repo.documents_dir / "9.json").write_text(
        repo.get_document(1).model_copy(update={"id": 9}).model_dump_json()
    )
    assert repo.create_document("D", "d.pdf", []).id == 10


def test_saved_json_is_indented_for_human_inspection(repo: Repository) -> None:
    """Stored files are indented by two spaces."""
    repo.create_document("A", "a.pdf", [])

    assert '\n  "id": 1' in (repo.documents_dir / "1.json").read_text()


def test_failed_replace_leaves_original_intact_and_no_temp_file(
    repo: Repository, monkeypatch
) -> None:
    """An interrupted save never corrupts the store."""
    repo.create_document("Original", "a.pdf", ["keep me"])
    before = (repo.documents_dir / "1.json").read_text()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr("learning_tool.storage.repository.os.replace", boom)

    with pytest.raises(OSError, match="disk went away"):
        repo.add_flashcards(1, [NewFlashcard("f", "b")])

    assert (repo.documents_dir / "1.json").read_text() == before
    assert list(repo.documents_dir.glob("*.tmp")) == []
    assert [p.name for p in repo.documents_dir.iterdir()] == ["1.json"]


def test_listing_skips_stray_non_numeric_files(repo: Repository) -> None:
    """Stray files are invisible to listing and to id allocation."""
    repo.create_document("A", "a.pdf", [])
    (repo.documents_dir / "notes.json").write_text("{}")
    (repo.documents_dir / "1.json.tmp").write_text("garbage")

    assert [d.title for d in repo.list_documents()] == ["A"]
    assert repo.create_document("B", "b.pdf", []).id == 2


def test_listing_returns_documents_ascending_by_id(repo: Repository) -> None:
    """Documents come back in id order."""
    for title in ("A", "B", "C"):
        repo.create_document(title, f"{title}.pdf", [])

    assert [d.id for d in repo.list_documents()] == [1, 2, 3]


def test_corrupt_stored_document_fails_loudly_on_load(repo: Repository) -> None:
    """A file violating the model rules raises rather than partially loading."""
    repo.create_document("A", "a.pdf", [])
    stored = json.loads((repo.documents_dir / "1.json").read_text())
    stored["quiz_questions"] = [
        {
            "id": 1,
            "question": "Q",
            "answer": "not an option",
            "question_type": "multiple_choice",
            "options": ["a", "b"],
        }
    ]
    (repo.documents_dir / "1.json").write_text(json.dumps(stored))

    with pytest.raises(ValidationError):
        repo.get_document(1)


def test_unknown_document_id_raises_document_not_found(repo: Repository) -> None:
    """Every document-scoped operation rejects unknown ids."""
    for call in (
        lambda: repo.get_document(7),
        lambda: repo.delete_document(7),
        lambda: repo.reset_progress(7),
        lambda: repo.add_flashcards(7, []),
        lambda: repo.add_quiz_questions(7, []),
        lambda: repo.get_flashcard(7, 1),
        lambda: repo.get_session_state(7),
        lambda: repo.get_due_items(7, NOW),
    ):
        with pytest.raises(DocumentNotFoundError, match="7"):
            call()


def test_unknown_item_id_raises_item_not_found(repo: Repository) -> None:
    """Item lookups name the missing id and its document."""
    repo.create_document("A", "a.pdf", [])

    with pytest.raises(ItemNotFoundError, match="flashcard with id 4"):
        repo.get_flashcard(1, 4)
    with pytest.raises(ItemNotFoundError, match="quiz question with id 4"):
        repo.get_quiz_question(1, 4)


def test_delete_returns_the_removed_document_and_unlinks_the_file(
    repo: Repository,
) -> None:
    """Deleting reports what was removed so the host can name it."""
    repo.create_document("Physics", "a.pdf", [])

    removed = repo.delete_document(1)

    assert removed.title == "Physics"
    assert not (repo.documents_dir / "1.json").exists()
    with pytest.raises(DocumentNotFoundError):
        repo.get_document(1)


def test_item_ids_are_shared_and_never_reused_across_calls(repo: Repository) -> None:
    """One counter feeds both item lists and only ever moves forward."""
    repo.create_document("A", "a.pdf", [])

    first = repo.add_flashcards(1, [NewFlashcard("f1", "b1"), NewFlashcard("f2", "b2")])
    questions = repo.add_quiz_questions(1, [short_answer("q1", "a1")])
    second = repo.add_flashcards(1, [NewFlashcard("f3", "b3")])

    assert [c.id for c in first] == [1, 2]
    assert [q.id for q in questions] == [3]
    assert [c.id for c in second] == [4]
    assert repo.get_document(1).next_item_id == 5


def test_invalid_question_in_a_batch_persists_none_of_it(repo: Repository) -> None:
    """Validation happens before anything is written."""
    repo.create_document("A", "a.pdf", [])
    batch = [
        short_answer("good", "answer"),
        NewQuizQuestion(
            question="bad",
            answer="c",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=("a", "b"),
        ),
    ]

    with pytest.raises(ValidationError):
        repo.add_quiz_questions(1, batch)

    document = repo.get_document(1)
    assert document.quiz_questions == []
    assert document.next_item_id == 1


def test_reset_progress_clears_responses_and_preserves_items(repo: Repository) -> None:
    """Resetting keeps items and the id counter, and reports the count."""
    repo.create_document("A", "a.pdf", ["c"])
    repo.add_flashcards(1, [NewFlashcard("f", "b")])
    repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)
    repo.record_response(1, ItemType.FLASHCARD, 1, "incorrect", False)

    cleared = repo.reset_progress(1)

    document = repo.get_document(1)
    assert cleared == 2
    assert document.responses == []
    assert [c.id for c in document.flashcards] == [1]
    assert document.concepts == ["c"]
    assert document.next_item_id == 2
    assert repo.add_flashcards(1, [NewFlashcard("f2", "b2")])[0].id == 2


def test_recorded_responses_are_stamped_and_kept_in_order(repo: Repository) -> None:
    """History is append-only and chronological."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(1, [NewFlashcard("f", "b")])

    repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)
    repo.record_response(
        1, ItemType.FLASHCARD, 1, "incorrect", False, Confidence.GUESSED
    )

    responses = repo.get_document(1).responses
    assert [r.is_correct for r in responses] == [True, False]
    assert responses[1].confidence is Confidence.GUESSED
    assert responses[0].created_at.tzinfo is not None
    assert responses[0].created_at <= responses[1].created_at


def test_flashcard_and_quiz_ids_are_scoped_by_item_type(repo: Repository) -> None:
    """Responses address items by the (type, id) pair."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(1, [NewFlashcard("f", "b")])
    repo.add_quiz_questions(1, [short_answer("q", "a")])

    repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)
    repo.record_response(1, ItemType.QUIZ, 2, "a", True)

    state = repo.get_session_state(1)
    assert state.in_progress == 2
    assert state.remaining == 0


def test_due_items_put_most_overdue_first_then_never_reviewed(
    repo: Repository,
) -> None:
    """Ordering is ascending next review, then document order."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(
        1, [NewFlashcard("reviewed-1", "b"), NewFlashcard("never", "b")]
    )
    repo.add_quiz_questions(1, [short_answer("reviewed-2", "a")])
    seed_history(
        repo,
        1,
        [
            Response(
                item_type=ItemType.FLASHCARD,
                item_id=1,
                answer="correct",
                is_correct=True,
                created_at=NOW - timedelta(days=10),
            ),
            Response(
                item_type=ItemType.QUIZ,
                item_id=3,
                answer="a",
                is_correct=True,
                created_at=NOW - timedelta(days=30),
            ),
        ],
    )

    due = repo.get_due_items(1, NOW)

    assert [item.id for item, _ in due] == [3, 1, 2]
    assert due[-1][1].next_review is None

    first, second = due[0][1].next_review, due[1][1].next_review
    assert first is not None and second is not None
    assert first < second


def test_items_not_yet_due_are_excluded(repo: Repository) -> None:
    """An item reviewed correctly today is not due today."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(1, [NewFlashcard("f", "b")])
    repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)

    assert repo.get_due_items(1, datetime.now(timezone.utc)) == []


def test_session_state_buckets_follow_the_precedence_rules(repo: Repository) -> None:
    """Each item lands in exactly one bucket and the buckets sum to total."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(
        1,
        [
            NewFlashcard("mastered", "b"),
            NewFlashcard("to-review", "b"),
            NewFlashcard("in-progress", "b"),
            NewFlashcard("remaining", "b"),
        ],
    )
    for _ in range(MASTERY_THRESHOLD):
        repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)
    repo.record_response(1, ItemType.FLASHCARD, 2, "incorrect", False)
    repo.record_response(1, ItemType.FLASHCARD, 3, "correct", True)

    state = repo.get_session_state(1)

    assert (state.mastered, state.to_review, state.in_progress, state.remaining) == (
        1,
        1,
        1,
        1,
    )
    assert state.total == 4
    assert state.mastered + state.to_review + state.in_progress + state.remaining == (
        state.total
    )


def test_mastered_item_stays_mastered_after_a_wrong_answer(repo: Repository) -> None:
    """The threshold rule wins over the last-answer rule."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(1, [NewFlashcard("f", "b")])
    for _ in range(MASTERY_THRESHOLD):
        repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)
    repo.record_response(1, ItemType.FLASHCARD, 1, "incorrect", False)

    state = repo.get_session_state(1)

    assert state.mastered == 1
    assert state.to_review == 0


def test_correct_answers_need_not_be_consecutive_to_master(repo: Repository) -> None:
    """Mastery counts total correct answers, not a streak."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(1, [NewFlashcard("f", "b")])
    repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)
    repo.record_response(1, ItemType.FLASHCARD, 1, "incorrect", False)
    repo.record_response(1, ItemType.FLASHCARD, 1, "correct", True)

    assert repo.get_session_state(1).mastered == 1


def test_confidence_keys_are_always_present_even_with_no_responses(
    repo: Repository,
) -> None:
    """Consumers never have to key-check the breakdown."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(1, [NewFlashcard("f", "b")])

    confidence = repo.get_session_state(1).confidence

    assert set(confidence) == set(CONFIDENCE_KEYS)
    assert CONFIDENCE_KEYS == ("guessed", "unsure", "confident", "unreported")
    assert set(confidence.values()) == {0}


def test_confidence_tallies_the_latest_response_of_each_answered_item(
    repo: Repository,
) -> None:
    """Stale confidence from an earlier answer is not counted."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(
        1,
        [
            NewFlashcard("one", "b"),
            NewFlashcard("two", "b"),
            NewFlashcard("never", "b"),
        ],
    )
    repo.record_response(1, ItemType.FLASHCARD, 1, "x", True, Confidence.GUESSED)
    repo.record_response(1, ItemType.FLASHCARD, 1, "x", True, Confidence.CONFIDENT)
    repo.record_response(1, ItemType.FLASHCARD, 2, "x", False)

    state = repo.get_session_state(1)

    assert state.confidence == {
        "guessed": 0,
        "unsure": 0,
        "confident": 1,
        "unreported": 1,
    }


def test_confidence_counts_sum_to_total_minus_remaining(repo: Repository) -> None:
    """The documented invariant, across a mixed history."""
    repo.create_document("A", "a.pdf", [])
    repo.add_flashcards(1, [NewFlashcard(f"card {n}", "b") for n in range(5)])
    repo.record_response(1, ItemType.FLASHCARD, 1, "x", True, Confidence.UNSURE)
    repo.record_response(1, ItemType.FLASHCARD, 2, "x", False, Confidence.GUESSED)
    repo.record_response(1, ItemType.FLASHCARD, 3, "x", True)

    state = repo.get_session_state(1)

    assert sum(state.confidence.values()) == state.total - state.remaining == 3


def test_empty_document_session_state_is_all_zeros(repo: Repository) -> None:
    """A document with no items has a zeroed session state."""
    repo.create_document("A", "a.pdf", [])

    state = repo.get_session_state(1)

    assert (state.mastered, state.to_review, state.in_progress, state.remaining) == (
        0,
        0,
        0,
        0,
    )
    assert state.total == 0
