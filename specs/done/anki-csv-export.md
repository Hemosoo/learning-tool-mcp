---
name: anki-csv-export
description: >
  FUTURE FEATURE (designed, not yet implemented — targets v0.7.0): an
  export_document tool that writes a document's items to an Anki-importable
  CSV file.
---

# Future — Anki CSV Export

## Goal

Let the user take their study items out of the local store and into Anki (or
any CSV consumer): a new `export_document` MCP tool writes one
Anki-importable CSV file per document. Builds on specs 03, 06, 07, 08.

## Design

**New pure module** in an `export` subpackage: a rendering function taking a
document (and an include-quiz flag) and returning the complete CSV text.
No I/O — the same pure-module pattern as SM-2 (spec 05).

Output format (Anki's text-import format, stable since Anki 2.1.54):

- Leading directive lines, each starting with `#`: separator declaration
  (comma), HTML off, and a tags-column declaration pointing at column 3.
- Then standard CSV rows, three columns: front, back, tags. Fields
  containing separators, quotes, or newlines are double-quoted with embedded
  quotes doubled (use the standard library's CSV writer; never hand-roll
  quoting).
- Flashcards map front/back as stored.
- Quiz questions map: front = question text with multiple-choice options
  appended as lettered lines (A., B., …); back = the stored answer.
- Tags column: the document title lowercased with every non-alphanumeric run
  collapsed to a single hyphen (Anki tags cannot contain spaces).
- IF the document has no exportable items, THEN THE system SHALL raise
  ValueError and write nothing — an empty export is silent failure.

**Service method** export_document(document_id, optional output_path,
include_quiz defaulting true): loads the document, renders, writes the file
(user-path expansion, parent directories created), returns a dict with
document_id, title, path, and per-type counts. Default output path:
`<data_dir>/exports/document-<id>-anki.csv`. The file write lives in the
service, not the repository — the repository is the boundary for the
document store, and an export file is not part of the store.

**Server**: register the tool (bringing the catalog to 12; update the
tool-count test). Description states that it writes a file and where.
Not exposed in the study widget.

## Trade-offs (already decided)

- Write a file rather than return CSV text: the server is local, direct
  writes are lossless; relaying a large blob through the host is not.
- CSV rather than the native Anki package format: the package format needs a
  new dependency and a SQLite schema; CSV import is first-class in Anki.
- Per-document exports match every other tool's granularity.

## Acceptance criteria

1. WHEN export_document is called for a document with items, THE system
   SHALL write a CSV file whose directives and rows import cleanly into
   Anki, and return the path plus per-type counts.
2. THE system SHALL quote fields containing commas, quotes, or newlines per
   CSV rules (round-trip verified with a CSV reader in tests).
3. WHEN a multiple-choice question is exported, THE system SHALL include its
   lettered options in the front field and the stored answer in the back.
4. WHERE include_quiz is false, THE system SHALL export only flashcards.
5. IF the document does not exist, THEN THE system SHALL raise the document
   lookup error.
6. IF the document has no exportable items, THEN THE system SHALL raise
   ValueError and write nothing.
7. WHERE output_path is omitted, THE system SHALL write to
   `<data_dir>/exports/document-<id>-anki.csv`, creating parents.
