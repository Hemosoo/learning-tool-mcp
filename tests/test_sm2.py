"""Tests for the pure SM-2 scheduler (spec 05)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from learning_tool.scheduling.sm2 import (
    FIRST_INTERVAL_DAYS,
    INITIAL_EASE,
    MINIMUM_EASE,
    SECOND_INTERVAL_DAYS,
    compute_schedule,
    quality_for,
)
from learning_tool.storage.models import Confidence, ItemType, Response

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def review(
    *, correct: bool = True, day: int = 0, confidence: Confidence | None = None
) -> Response:
    """Build one response at ``day`` days after the start instant.

    Args:
        correct: Whether the answer was graded correct.
        day: Offset in days from the fixed start instant.
        confidence: Optional self-reported confidence.

    Returns:
        The response.
    """
    return Response(
        item_type=ItemType.FLASHCARD,
        item_id=1,
        answer="a",
        is_correct=correct,
        confidence=confidence,
        created_at=START + timedelta(days=day),
    )


def test_never_reviewed_item_is_due_with_null_timestamps() -> None:
    """An item with no history is always due."""
    schedule = compute_schedule([], START)

    assert schedule.repetitions == 0
    assert schedule.ease == INITIAL_EASE
    assert schedule.interval_days == 0
    assert schedule.last_reviewed is None
    assert schedule.next_review is None
    assert schedule.is_due is True


def test_first_pass_schedules_one_day_later() -> None:
    """A first successful review sets the 1-day interval."""
    schedule = compute_schedule([review()], START)

    assert schedule.repetitions == 1
    assert schedule.interval_days == FIRST_INTERVAL_DAYS
    assert schedule.next_review == START + timedelta(days=1)
    assert schedule.is_due is False


def test_second_consecutive_pass_schedules_six_days_later() -> None:
    """A second consecutive pass sets the 6-day interval."""
    schedule = compute_schedule([review(day=0), review(day=1)], START)

    assert schedule.repetitions == 2
    assert schedule.interval_days == SECOND_INTERVAL_DAYS
    assert schedule.next_review == START + timedelta(days=1 + 6)


def test_third_pass_multiplies_by_the_ease_from_before_the_update() -> None:
    """The third interval is round(6 x ease) using the pre-update ease."""
    history = [review(day=0), review(day=1), review(day=7)]

    schedule = compute_schedule(history, START)

    assert schedule.repetitions == 3
    assert schedule.interval_days == round(SECOND_INTERVAL_DAYS * INITIAL_EASE)
    assert schedule.interval_days == 15
    assert schedule.next_review == START + timedelta(days=7 + 15)


def test_incorrect_review_resets_repetitions_and_interval_but_penalizes_ease() -> None:
    """A lapse restarts learning while still lowering the ease."""
    history = [
        review(day=0),
        review(day=1),
        review(day=7),
        review(correct=False, day=8),
    ]

    schedule = compute_schedule(history, START)

    assert schedule.repetitions == 0
    assert schedule.interval_days == FIRST_INTERVAL_DAYS
    assert schedule.ease < INITIAL_EASE
    assert schedule.next_review == START + timedelta(days=9)


def test_ease_never_falls_below_the_floor() -> None:
    """Repeated lapses clamp the ease at 1.3."""
    history = [review(correct=False, day=day) for day in range(12)]

    schedule = compute_schedule(history, START)

    assert schedule.ease == MINIMUM_EASE


def test_quality_mapping_of_confidence_on_correct_answers() -> None:
    """Confidence maps to 3/4/5 and absence to 4; incorrect is always 2."""
    assert quality_for(review(confidence=Confidence.GUESSED)) == 3
    assert quality_for(review(confidence=Confidence.UNSURE)) == 4
    assert quality_for(review(confidence=Confidence.CONFIDENT)) == 5
    assert quality_for(review()) == 4
    assert quality_for(review(correct=False, confidence=Confidence.CONFIDENT)) == 2


def test_confident_answers_raise_ease_and_guessed_answers_lower_it() -> None:
    """Quality 5 adds 0.1, quality 4 is neutral, quality 3 subtracts."""
    confident = compute_schedule([review(confidence=Confidence.CONFIDENT)], START)
    unsure = compute_schedule([review(confidence=Confidence.UNSURE)], START)
    guessed = compute_schedule([review(confidence=Confidence.GUESSED)], START)

    assert confident.ease == pytest.approx(INITIAL_EASE + 0.1)
    assert unsure.ease == pytest.approx(INITIAL_EASE)
    assert guessed.ease == pytest.approx(INITIAL_EASE - 0.14)


def test_item_is_due_when_next_review_is_at_or_before_now() -> None:
    """Due-ness compares the next review against the injected instant."""
    history = [review()]
    next_review = START + timedelta(days=1)

    assert compute_schedule(history, next_review - timedelta(seconds=1)).is_due is False
    assert compute_schedule(history, next_review).is_due is True
    assert compute_schedule(history, next_review + timedelta(days=5)).is_due is True


def test_naive_now_raises_value_error() -> None:
    """A naive evaluation instant is rejected."""
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_schedule([review()], datetime(2026, 1, 2))


def test_replay_is_deterministic() -> None:
    """Identical history and instant always produce identical schedules."""
    history = [review(day=0), review(correct=False, day=1), review(day=2)]

    assert compute_schedule(history, START) == compute_schedule(history, START)
