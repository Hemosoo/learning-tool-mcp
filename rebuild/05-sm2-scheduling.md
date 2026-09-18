---
name: sm2-scheduling
description: >
  Pure SM-2 spaced-repetition scheduling: derive an item's review schedule by
  replaying its full response history. Exact constants, quality mapping, and
  update rules.
---

# 05 — SM-2 Scheduling

## Role

A pure module (`scheduling.sm2`): no I/O, no clock access. The evaluation
instant `now` is injected by the caller so tests are deterministic without
mocking. Nothing is persisted — an item's schedule is recomputed on demand
from its `Response` history (the compute-from-history pattern of spec 01).

## Output: the item schedule value object

An immutable (frozen) dataclass:

| Field | Type | Meaning |
|-------|------|--------|
| repetitions | int | consecutive successful reviews since the last lapse |
| ease | float | SM-2 ease factor, never below the floor |
| interval_days | int | days between the last review and the next (0 if never reviewed) |
| last_reviewed | datetime or null | timestamp of the most recent response, null if none |
| next_review | datetime or null | when the item is next due, null if never reviewed |
| is_due | bool | whether the item should be reviewed now |

## Constants (normative)

| Constant | Value |
|----------|-------|
| Initial ease | 2.5 |
| Minimum ease (floor) | 1.3 |
| First interval | 1 day |
| Second interval | 6 days |
| Lapse quality | 2 |
| Default correct quality (no confidence reported) | 4 |
| Passing quality threshold | 3 (quality below this is a lapse) |

## Quality grading of one response

SM-2 uses quality grades 0–5; this application's data yields only 2–5:

| Response | Quality |
|----------|--------|
| incorrect (regardless of confidence) | 2 (lapse) |
| correct + confidence `guessed` | 3 |
| correct + confidence `unsure` | 4 |
| correct + confidence `confident` | 5 |
| correct + no confidence reported | 4 |

## The replay algorithm

Input: the item's responses ordered oldest first (their storage order), and a
timezone-aware `now`.

1. IF `now` is timezone-naive, THEN THE system SHALL raise ValueError —
   comparing it against stored timezone-aware timestamps would be undefined.
2. WHEN the response list is empty, THE system SHALL return: repetitions 0,
   ease = initial ease, interval 0, last_reviewed null, next_review null,
   is_due **true** (a never-reviewed item is always due).
3. Otherwise THE system SHALL start from repetitions 0, ease = initial ease,
   interval 0, and fold each response in order:
   a. Compute the response's quality per the table above.
   b. IF quality is below the passing threshold (a lapse): reset repetitions
      to 0 and set the interval to the first interval (1 day) — the item is
      treated as newly learned.
   c. Otherwise (a pass): set the interval by repetition count — first pass
      (repetitions 0) → 1 day; second (repetitions 1) → 6 days; later →
      round(interval × ease) using the ease value from **before** this
      review's ease update (standard SM-2 pseudocode ordering). Then
      increment repetitions.
   d. On **every** review (pass or lapse), update ease by the standard SM-2
      formula: ease' = ease + (0.1 − (5 − q) × (0.08 + (5 − q) × 0.02))
      where q is the quality — quality 4 leaves ease unchanged, 5 raises it
      by 0.1, and lower grades reduce it — then clamp to the 1.3 floor.
4. After the fold: last_reviewed is the final response's timestamp;
   next_review is last_reviewed plus the final interval in days; is_due is
   true exactly when next_review is at or before `now`.

## Acceptance criteria

1. WHEN an item has never been reviewed, THE system SHALL report it due with
   null review timestamps and interval 0.
2. WHEN the first review is a pass, THE system SHALL schedule the next review
   1 day later; a second consecutive pass, 6 days after that; a third,
   round(6 × ease-before-update) days after that.
3. IF a review is incorrect, THEN THE system SHALL reset repetitions to 0 and
   the interval to 1 day, while still applying the ease penalty.
4. THE system SHALL never let ease fall below 1.3.
5. WHEN confidence is reported on a correct answer, THE system SHALL grade it
   3/4/5 for guessed/unsure/confident; absent confidence grades 4.
6. IF `now` is naive, THEN THE system SHALL raise ValueError.
7. THE system SHALL be deterministic: identical histories and `now` always
   produce identical schedules (no hidden clock reads).
