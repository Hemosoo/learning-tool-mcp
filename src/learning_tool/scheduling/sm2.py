"""Pure SM-2 spaced-repetition scheduling derived from response history."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from learning_tool.storage.models import Confidence, Response

INITIAL_EASE = 2.5
"""Ease factor an item starts with."""

MINIMUM_EASE = 1.3
"""Floor below which the ease factor is never allowed to fall."""

FIRST_INTERVAL_DAYS = 1
"""Interval after the first successful review."""

SECOND_INTERVAL_DAYS = 6
"""Interval after the second consecutive successful review."""

LAPSE_QUALITY = 2
"""Quality grade assigned to an incorrect answer."""

DEFAULT_CORRECT_QUALITY = 4
"""Quality grade for a correct answer with no confidence reported."""

PASSING_QUALITY = 3
"""Lowest quality grade that counts as a pass."""

_CONFIDENCE_QUALITY = {
    Confidence.GUESSED: 3,
    Confidence.UNSURE: 4,
    Confidence.CONFIDENT: 5,
}
"""Quality grade per self-reported confidence level on a correct answer."""


@dataclass(frozen=True)
class ItemSchedule:
    """An item's review schedule, recomputed from its response history.

    Attributes:
        repetitions: Consecutive successful reviews since the last lapse.
        ease: SM-2 ease factor, never below the floor.
        interval_days: Days between the last review and the next one.
        last_reviewed: Timestamp of the most recent response, if any.
        next_review: When the item is next due, if ever reviewed.
        is_due: Whether the item should be reviewed now.
    """

    repetitions: int
    ease: float
    interval_days: int
    last_reviewed: datetime | None
    next_review: datetime | None
    is_due: bool


def quality_for(response: Response) -> int:
    """Grade a single response on the SM-2 0-5 quality scale.

    Args:
        response: The response to grade.

    Returns:
        2 for an incorrect answer; 3/4/5 for a correct answer reported as
        guessed/unsure/confident; 4 for a correct answer with no confidence.
    """
    if not response.is_correct:
        return LAPSE_QUALITY
    if response.confidence is None:
        return DEFAULT_CORRECT_QUALITY
    return _CONFIDENCE_QUALITY[response.confidence]


def _updated_ease(ease: float, quality: int) -> float:
    """Apply the standard SM-2 ease update and clamp to the floor.

    Args:
        ease: The ease factor before this review.
        quality: The review's quality grade.

    Returns:
        The updated ease factor, never below the minimum.
    """
    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return max(MINIMUM_EASE, ease + delta)


def compute_schedule(responses: Sequence[Response], now: datetime) -> ItemSchedule:
    """Replay an item's responses to derive its current schedule.

    Args:
        responses: The item's responses, oldest first.
        now: Timezone-aware evaluation instant, injected by the caller.

    Returns:
        The item's schedule as of ``now``.

    Raises:
        ValueError: If ``now`` is timezone-naive.
    """
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now must be timezone-aware")

    if not responses:
        return ItemSchedule(
            repetitions=0,
            ease=INITIAL_EASE,
            interval_days=0,
            last_reviewed=None,
            next_review=None,
            is_due=True,
        )

    repetitions = 0
    ease = INITIAL_EASE
    interval = 0
    for response in responses:
        quality = quality_for(response)
        if quality < PASSING_QUALITY:
            repetitions = 0
            interval = FIRST_INTERVAL_DAYS
        else:
            if repetitions == 0:
                interval = FIRST_INTERVAL_DAYS
            elif repetitions == 1:
                interval = SECOND_INTERVAL_DAYS
            else:
                interval = round(interval * ease)
            repetitions += 1
        ease = _updated_ease(ease, quality)

    last_reviewed = responses[-1].created_at
    next_review = last_reviewed + timedelta(days=interval)
    return ItemSchedule(
        repetitions=repetitions,
        ease=ease,
        interval_days=interval,
        last_reviewed=last_reviewed,
        next_review=next_review,
        is_due=next_review <= now,
    )
