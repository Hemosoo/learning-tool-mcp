---
name: storage-repository
description: >
  The file-backed repository: the single boundary between application logic
  and storage. File layout, atomic writes, id allocation, all data-access
  operations, and the session-state bucketing rules.
---

# 06 — Storage Repository

## Role

The repository is the **only** module that knows storage is files. The
service depends on its interface alone, so a future move to a database is a
change to this one class. It composes the domain models (spec 03) and the
SM-2 scheduler (spec 05).

## File layout

| Item | Rule |
|------|------|
| Location | `<data_dir>/documents/<document_id>.json`, one file per document |
| Unit of consistency | The document: every mutation rewrites exactly one file, atomically |
| Directory creation | Lazy: the `documents/` directory is created on first write, never at construction or load time |
| File content | The Document model serialized as JSON, indented 2 (human-inspectable) |

## Atomic write protocol

Every save follows the same protocol so an interrupted write can never leave
a partially written or corrupt file — readers see either the old file or the
fully written new one:

1. Serialize the document to JSON text first.
2. Create a uniquely named temporary file **in the documents directory
   itself** (same directory ⇒ same filesystem ⇒ the final rename is atomic).
   Give it a distinguishable suffix (e.g. `.tmp`) so stray leftovers are
   identifiable and — because they are not `.json` — invisible to id
   discovery.
3. Write the payload and close the handle.
4. Atomically replace the target file with the temp file (the OS-level
   atomic-rename operation that overwrites the destination).
5. IF anything fails before the replace completes, THEN THE system SHALL
   delete the temp file (tolerating it already being gone) and re-raise —
   catching even non-Exception interrupts for the cleanup, since the point
   is crash-safety.

## Id discovery and allocation

- Document ids are discovered by enumerating `*.json` files in the documents
  directory and parsing each filename stem as an integer; non-numeric stems
  are skipped silently (stray files cannot break the store). This
  enumeration is the single source of truth, used by both listing and id
  allocation.
- Next document id = highest existing id + 1, or 1 when the store is empty.
- Item ids come from the document's own `next_item_id` counter (spec 03):
  each added flashcard or quiz question takes the current value and
  increments it. Ids are never reused, even after items are added in
  different calls.

## Error types

Two dedicated lookup errors, both subclassing the standard lookup error type:
one for a missing document id, one for a missing item (flashcard or quiz
question) within a document. Messages name the offending id (and document).

## Input value objects

Creation inputs are id-less immutable dataclasses (the repository assigns
ids): a new-flashcard input (front, back) and a new-quiz-question input
(question, answer, question_type, options).

## Operations

All read operations parse the file through the domain model, so corrupt or
tampered files fail validation loudly.

| Operation | Contract |
|-----------|----------|
| create document | Takes title, source path, concept texts. Assigns the next document id, persists, returns the document. |
| get document | Returns the parsed document; unknown id raises the document lookup error. |
| list documents | Loads every stored document, ascending by id; empty list when none. Skips non-numeric stems. |
| delete document | Loads the document **first** (so an unknown id fails loudly and the caller receives the deleted content for feedback, e.g. its title), then removes the file. Irreversible. |
| reset progress | Clears only the responses list and saves atomically. Concepts, items, and `next_item_id` are preserved — item ids stay stable. Returns the number of responses cleared. |
| add flashcards | Loads the document, assigns sequential item ids, appends, saves once. Returns the created items. |
| add quiz questions | Constructs (and thereby validates) **all** questions before saving anything, so one invalid question persists nothing from the call. Otherwise as flashcards. |
| get flashcard / get quiz question | Linear search within the document's list; missing item raises the item lookup error. |
| record response | Appends a Response (timestamped at construction) to the document and saves. Does not itself validate the item exists — that is the service's job before grading. |
| get due items | See below. |
| get session state | See below. |

### Grouping responses

A shared helper groups a document's responses by `(item_type, item_id)`.
Because responses are stored in insertion order, each group is chronological
and its last entry is the item's most recent answer. Both derived-state
operations below use it.

### Due items

Input: document id and a timezone-aware `now`. For every item (flashcards
then quiz questions), compute its schedule by replaying its response group
through SM-2 (empty group for never-answered items). Keep only items whose
schedule says due. Return them as pairs of item + schedule, ordered:

1. Previously reviewed items first, ascending by next-review time — most
   overdue first.
2. Never-reviewed items after them, in document order — they are due but not
   "overdue", having no review date to be past.

### Session state

Returns an immutable aggregate with five integer fields — mastered,
to_review, remaining, in_progress, total — and, since 0.7.0
(`future/surface-confidence-in-stats.md`), a `confidence` mapping. The
mastery threshold is a named constant: **2 total correct answers** (not
necessarily consecutive).

Bucketing precedence per item — evaluated in this order, mutually exclusive:

1. **remaining** — never answered.
2. **mastered** — correct answers ≥ the threshold. (Precedence means an item
   that reached the threshold stays mastered even if its latest answer was
   wrong — the threshold rule wins.)
3. **to_review** — last answer was incorrect.
4. **in_progress** — answered, not mastered, last answer correct.

The four buckets always sum to the total item count (flashcards + quiz
questions).

The confidence breakdown is computed in the same pass, from the same grouped
history: for every item with at least one response, the confidence of its
last response is tallied, a null counting as unreported. Latest-per-item
rather than every response, because the buckets describe current state and
stale confidence from three answers ago says nothing about it. Nothing is
persisted — this is the compute-from-history pattern like everything else.

## Acceptance criteria

1. WHEN a document is created, THE system SHALL write `<id>.json` under the
   documents directory with id = max existing + 1 (1 for the first).
2. IF a save is interrupted at the replace step, THEN THE system SHALL leave
   the previous file intact and no temp file behind (tested by forcing the
   replace operation to fail).
3. WHEN listing with stray non-numeric files present, THE system SHALL skip
   them and return only real documents.
4. IF any queried id (document or item) does not exist, THEN THE system
   SHALL raise the corresponding dedicated lookup error and mutate nothing.
5. IF one quiz question in a batch is invalid, THEN THE system SHALL persist
   none of the batch.
6. WHEN progress is reset, THE system SHALL preserve items and the item-id
   counter, clear responses, and report the cleared count.
7. THE system SHALL order due items overdue-first (ascending next review)
   followed by never-reviewed items in document order.
8. THE system SHALL bucket session state per the precedence rules, with
   buckets summing to total; an item with 2 correct answers then an
   incorrect one still counts mastered.
9. THE system SHALL report a confidence mapping carrying exactly the keys
   guessed, unsure, confident and unreported — always all four, zeroes
   included — counting each **answered** item once by its **latest**
   response's confidence, with a null confidence counted as unreported.
   Never-answered items are excluded, so the counts sum to total minus
   remaining.
