---
name: service-layer
description: >
  The StudyService: orchestration over the repository and ingestion, grading
  rules, string-to-enum parsing, clock resolution, and the exact output shape
  of every operation.
---

# 07 — Service Layer

## Role

One class, the study service, constructed over a data directory (it builds
its own repository from that path). The MCP adapter (spec 08) is a thin
pass-through to these methods, so **the dict shapes defined here are the
wire format the MCP host sees**. All keys and shapes below are normative.

The service owns three responsibilities the layers below refuse: resolving
the clock (timezone-aware UTC, resolved here and passed down), converting
untrusted strings into enums with helpful errors, and shaping outputs as
plain dicts/lists of JSON-safe values (datetimes become ISO-8601 strings).

## Parsing and grading rules

- **Enum parsing**: item type, question type, and confidence arrive as
  strings. Each has a parser that raises ValueError listing the valid values
  (e.g. "item_type must be one of: flashcard, quiz") on anything else.
  A null confidence stays null.
- **Answer normalization**: lowercase, trim, and collapse all internal
  whitespace runs to single spaces.
- **Quiz grading**: auto-graded — the submitted answer is correct exactly
  when its normalized form equals the stored answer's normalized form.
- **Flashcard grading**: self-reported, because free-text matching against a
  card back is unreliable. The answer must be the word "correct" or
  "incorrect" (case-insensitive, trimmed); anything else raises ValueError
  naming the two accepted values.

## Operations and output shapes

| Operation | Inputs | Output (dict keys) | Errors |
|-----------|--------|--------------------|--------|
| ingest material | pdf_path, optional title | document_id, title, concept_count | ingestion errors from spec 04 |
| get material | document_id | document_id, title, concepts (list of strings) | unknown document |
| list documents | — | list of {document_id, title, concept_count, flashcard_count, quiz_count, created_at as ISO-8601}, ascending by id; empty list if none | — |
| get study items | document_id | document_id, title, flashcards (each: id, front, back), quiz_questions (each: id, question, options, answer, question_type as string) | unknown document |
| get due items | document_id | document_id, title, due (see below), due_count | unknown document |
| save flashcards | document_id, iterable of {front, back} | list of {id, front, back} | unknown document; missing key |
| save quiz | document_id, iterable of {question, answer, question_type, optional options} | list of {id, question, options, answer, question_type} | unknown document; missing key; invalid question_type (ValueError); option-rule violations (model validation) |
| submit response | document_id, item_type, item_id, answer, optional confidence | is_correct, progress (the session-state dict) | unknown document/item; invalid item_type/confidence/self-report (ValueError) |
| get session state | document_id | mastered, to_review, remaining, in_progress, total, confidence (mapping; see spec 06) | unknown document |
| delete document | document_id | document_id, title, deleted (always true) | unknown document |
| reset progress | document_id | document_id, title, responses_cleared (count) | unknown document |
| export document | document_id, optional output_path, include_quiz (default true) | document_id, title, path, flashcard_count, quiz_count | unknown document; no exportable items (ValueError) |

Details and rationale:

- **ingest material**: extract text, chunk (spec 04), store; the title
  defaults to the PDF's file name when not provided. Generation is deferred
  to the host — ingestion persists raw material only.
- **get study items** includes quiz answers deliberately: it is the user's
  own local data, reviewing needs the answers, and submit_response remains
  the canonical grader.
- **get due items**: `now` is resolved here. Each due entry carries
  item_type (string), item_id, repetitions, interval_days, next_review
  (ISO-8601 or null for never-reviewed) — plus the item's own fields:
  front/back for flashcards; question, options, answer, question_type for
  quiz questions. Order comes from the repository (overdue first).
- **submit response** sequence: parse enums; for quiz, fetch the question
  and auto-grade; for flashcard, verify the card exists **before** recording
  a self-reported result, then parse the self-report; record the response;
  recompute session state; return `is_correct` plus the fresh progress dict.
- **delete document** returns the title so the host can tell the user what
  was removed; **reset progress** reads the document first (unknown id fails
  before any clearing).
- **export document** (0.7.0, `future/anki-csv-export.md`) renders the CSV
  in full before writing, so a document with nothing to export leaves no
  file behind. The write lives here rather than in the repository: the
  repository is the boundary for the document store, and an export file is
  not part of the store. The default path is
  `<data_dir>/exports/document-<id>-anki.csv`, parents created; an explicit
  path has `~` expanded. `quiz_count` reports what was written, so it is
  zero when include_quiz is false.

## Acceptance criteria

1. THE system SHALL emit exactly the dict keys listed per operation, with
   datetimes as ISO-8601 strings and enums as their string values.
2. WHEN a quiz answer differs only in case or whitespace from the stored
   answer, THE system SHALL grade it correct.
3. IF a flashcard self-report is neither "correct" nor "incorrect", THEN THE
   system SHALL raise ValueError and record nothing.
4. IF item_type, question_type, or confidence is an invalid string, THEN THE
   system SHALL raise ValueError listing the valid values.
5. WHEN submit_response succeeds, THE system SHALL return the updated
   session state computed after the new response was recorded.
6. WHEN ingesting without a title, THE system SHALL use the PDF file name.
7. THE system SHALL resolve `now` once per get_due_items call, as
   timezone-aware UTC, at this layer only.
