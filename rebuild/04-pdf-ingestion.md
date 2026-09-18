---
name: pdf-ingestion
description: >
  PDF text extraction and paragraph chunking: the only content-processing the
  server performs.
---

# 04 — PDF Ingestion

## Role

A small pure module (`ingestion.pdf`) with two functions and one error type.
Chunking is intentionally simple (paragraph-based); semantic chunking is a
deferred feature (see `future/deferred-roadmap.md`). No LLM work happens here
or anywhere in the server.

## Error type

`PdfIngestionError`, subclassing `RuntimeError`. Raised when a PDF cannot be
found, parsed, or yields no text. It is the single error type callers see
from this module.

## Text extraction

Input: a filesystem path string. Output: the document's full text.

1. IF the path is not an existing file, THEN THE system SHALL raise
   PdfIngestionError naming the path ("PDF not found").
2. THE system SHALL parse the PDF with the pypdf reader and extract text from
   every page, treating a page that yields no text as the empty string.
3. IF the underlying parser raises any exception, THEN THE system SHALL wrap
   it in PdfIngestionError (chaining the cause) with a message naming the
   path — pypdf raises a variety of exception types on malformed input, so
   the catch must be broad and immediately re-raised as the domain error.
4. THE system SHALL join page texts with a blank line between pages, so page
   boundaries become paragraph boundaries for the chunker.
5. IF the joined text is empty or whitespace-only, THEN THE system SHALL
   raise PdfIngestionError explaining that the PDF has no extractable text
   and may be scanned images.

## Paragraph chunking

Input: extracted text. Output: a list of concept chunks.

1. THE system SHALL split the text at paragraph boundaries: one or more
   consecutive newline characters separated only by optional whitespace
   (i.e. blank lines, including lines of spaces).
2. THE system SHALL strip surrounding whitespace from each chunk.
3. THE system SHALL drop empty chunks; an input with no non-blank content
   yields an empty list (chunking itself never raises — the empty-text error
   belongs to extraction).

## Acceptance criteria

1. WHEN given a valid text PDF, THE system SHALL return its text with pages
   joined by blank lines.
2. IF the file is missing, unparseable, or textless, THEN THE system SHALL
   raise PdfIngestionError (three distinct tests).
3. WHEN chunking text with blank-line-separated paragraphs, THE system SHALL
   return one stripped chunk per paragraph, in order, with empties dropped.
