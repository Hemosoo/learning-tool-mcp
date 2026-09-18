---
name: mcp-server-and-tools
description: >
  The FastMCP adapter: server identity, the complete 11-tool catalog with
  description requirements, the MCP Apps resource registration, and startup.
---

# 08 — MCP Server and Tools

## Role

A thin adapter over the service (spec 07) using the FastMCP API from the
`mcp` package (v1.x). It contains **no business logic**: every tool body is a
one-line delegation to the corresponding service method. Server name:
`learning-tool`. Transport: stdio.

Startup: a builder function loads config (spec 02) and constructs the
service; a factory function takes the service and returns the configured
FastMCP instance (separated this way so tests can build a server over a
temporary directory); the console-script entry point composes the two and
runs the server.

## Descriptions are part of the product

Tool descriptions are the only mechanism steering the host model — grounding
and destructive-action confirmation are enforced by instruction, not code
(spec 01). The description requirements below are therefore normative, and
tests lock the critical wording.

## Tool catalog (exactly these 12)

| Tool | Parameters | Returns | Description must convey |
|------|------------|---------|-------------------------|
| ingest_material | pdf_path (str), title (str, optional) | dict | Ingests a PDF and stores its text as study material; returns document_id, title, concept_count; directs the host to call get_material next before generating items |
| get_material | document_id (int) | dict | Returns stored concepts; instructs the host to use this material as the ONLY source when generating items — no outside facts (the grounding instruction) |
| list_documents | — | list of dicts | Enumerates stored documents with ids/titles/counts; for discovering ids at session start |
| get_study_items | document_id (int) | dict | Returns saved flashcards and quiz questions (get_material returns raw source concepts instead) |
| get_due_items | document_id (int) | dict | Items due now, most overdue first, SM-2; never-reviewed items included after overdue ones; use it to pick what to study next; notes that MCP Apps hosts render the study widget on this call. **Carries tool metadata linking the UI resource (see below).** |
| save_flashcards | document_id (int), cards (list of dicts) | list of dicts | Each card must have front and back; returns stored cards with assigned ids |
| save_quiz | document_id (int), questions (list of dicts) | list of dicts | Each question needs question, answer, question_type (multiple_choice or short_answer); multiple choice also needs options (≥ 2) with the answer exactly one of them |
| submit_response | document_id (int), item_type (str), item_id (int), answer (str), confidence (str, optional) | dict | Records an answer; quiz auto-graded, flashcard self-reported ("correct"/"incorrect"); optional confidence guessed/unsure/confident; returns is_correct + progress |
| get_session_state | document_id (int) | dict | Returns mastered / to_review / in_progress / remaining / total, plus the confidence breakdown and its four keys (0.7.0) |
| delete_document | document_id (int) | dict | States it is DESTRUCTIVE and irreversible, removes material, items, and progress, and instructs the host to confirm with the user (naming the document's title) before calling |
| reset_progress | document_id (int) | dict | States it is DESTRUCTIVE and irreversible, erases answer history (mastery and schedules) while keeping items, and instructs the host to confirm with the user before calling |
| export_document | document_id (int), output_path (str, optional), include_quiz (bool, default true) | dict | Writes an Anki-importable CSV **file** and returns its path — it does not return CSV text; names the default location and the include_quiz switch. Added in 0.7.0; not exposed in the study widget |

Destructive-tool policy: there is deliberately **no** `confirm` boolean
parameter — a host-set flag is theater. Confirmation is requested via the
description (the same guidance-via-description pattern as grounding), and a
server test asserts both destructive descriptions contain the word
"DESTRUCTIVE" and an instruction to confirm with the user.

## MCP Apps resource

One resource, serving the study widget (spec 09):

| Property | Value |
|----------|-------|
| URI | `ui://learning-tool/study` |
| Name | `study_widget` |
| Description | Interactive study-session widget (flashcards, quizzes, progress) |
| MIME type | `text/html;profile=mcp-app` |
| Resource metadata | a `ui` object with `prefersBorder` true |
| Content | The widget HTML, read from the file bundled inside the installed package's `ui` subpackage via the standard importlib resources mechanism (works from a wheel, not just a checkout) |

The `get_due_items` tool carries tool metadata naming the resource, under
**two keys carrying the same URI**:

| Key | Value |
|-----|-------|
| `ui` | An object whose `resourceUri` is the URI above |
| `ui/resourceUri` | The URI above, as a flat string |

Both are required. The nested object is what the extension documents; the
flat alias is what shipping hosts read, and the reference example server
publishes both. A server that emits only the nested form is accepted,
prefetched, and then never rendered — the failure is silent, so it is easy
to mistake for a host defect. Verified against Claude Desktop: with the flat
key absent the widget never renders; with it present it does.

Supporting hosts prefetch the resource and render it in a sandboxed iframe
when the tool is called; hosts without the extension ignore both the metadata
and the resource — graceful degradation is built into the extension's design
and costs nothing here.

## Acceptance criteria

1. THE system SHALL register exactly 12 tools with the names above (a test
   asserts the count and the name set). The catalog was 11 through 0.6.0;
   `export_document` is the twelfth.
2. THE system SHALL register exactly one resource at `ui://learning-tool/study`
   with MIME type `text/html;profile=mcp-app`, serving non-empty HTML.
3. THE system SHALL attach the resource URI as UI tool-metadata on
   get_due_items and on no other tool, under **both** the nested `ui` object
   and the flat `ui/resourceUri` key.
4. THE system SHALL include "DESTRUCTIVE" and a confirm-with-the-user
   instruction in the delete_document and reset_progress descriptions.
5. THE system SHALL include the only-source grounding instruction in the
   get_material description.
6. WHEN the console script runs, THE system SHALL serve over stdio using the
   environment-configured data directory.
