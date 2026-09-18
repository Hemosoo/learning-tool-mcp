---
name: domain-model
description: >
  The pydantic domain models and enums, their fields, validation rules, and
  the on-disk JSON shape they define.
---

# 03 — Domain Model

## Role

Domain models are pydantic models (not ORM classes, not plain dataclasses).
Pydantic does double duty: it is the on-disk serialization format (model →
JSON text, JSON text → validated model) and the validator of untrusted file
content on load. A whole document and everything stored against it nest into
one object, mirroring the one-file-per-document storage layout (spec 06).

All enums are string-valued (they serialize as their string values in JSON
and accept those strings on parse).

## Enums

| Enum | Values | Meaning |
|------|--------|--------|
| ItemType | `flashcard`, `quiz` | The kind of study item a response refers to |
| QuestionType | `multiple_choice`, `short_answer` | Supported quiz formats |
| Confidence | `guessed`, `unsure`, `confident` | Optional self-reported confidence attached to a response |

## Models

### Flashcard
| Field | Type | Constraints |
|-------|------|-------------|
| id | int | assigned by the repository |
| front | str | minimum length 1 |
| back | str | minimum length 1 |

### QuizQuestion
| Field | Type | Constraints |
|-------|------|-------------|
| id | int | assigned by the repository |
| question | str | minimum length 1 |
| answer | str | minimum length 1 |
| question_type | QuestionType | required |
| options | list of str | defaults to empty list |

A model-level validator (running after field validation) enforces the option
rules, so an invalid question can never be constructed — and therefore never
persisted — by any code path:

1. IF question_type is multiple_choice AND options has fewer than 2 entries,
   THEN THE system SHALL reject the question ("needs at least 2 options").
2. IF question_type is multiple_choice AND answer is not exactly one of
   options, THEN THE system SHALL reject the question.
3. IF question_type is short_answer AND options is non-empty, THEN THE system
   SHALL reject the question.

### Response
One user answer to a single study item. `item_id` is scoped by `item_type`:
a flashcard and a quiz question in the same document may share a numeric id,
so the pair identifies the item.

| Field | Type | Constraints |
|-------|------|-------------|
| item_type | ItemType | required |
| item_id | int | required |
| answer | str | the raw submitted text (or self-report) |
| is_correct | bool | graded result |
| confidence | Confidence or null | defaults to null |
| created_at | datetime | defaults to the current **timezone-aware UTC** time at construction |

### Document
The aggregate root; the whole object is one JSON file on disk.

| Field | Type | Constraints |
|-------|------|-------------|
| id | int | assigned by the repository |
| title | str | human-readable |
| source_path | str | the path the material was ingested from |
| concepts | list of str | extracted text chunks; defaults empty |
| flashcards | list of Flashcard | defaults empty |
| quiz_questions | list of QuizQuestion | defaults empty |
| responses | list of Response | insertion order = chronological; defaults empty |
| next_item_id | int | defaults to 1; a **single** per-document counter that assigns ids to flashcards and quiz questions alike |
| created_at | datetime | defaults to current timezone-aware UTC |

The shared `next_item_id` counter means item ids are unique across both item
lists within a document, which keeps `(item_type, item_id)` unambiguous while
allowing the simple pair addressing above.

## Acceptance criteria

1. THE system SHALL round-trip every model through JSON serialization and
   validation without data loss (including timezone-aware timestamps).
2. IF stored JSON violates any constraint above, THEN THE system SHALL raise
   a validation error on load rather than yield a partially valid object.
3. THE system SHALL enforce the three multiple-choice/short-answer rules at
   model construction time.
4. WHEN a Response is created without an explicit timestamp, THE system SHALL
   stamp it with timezone-aware UTC now.
