---
name: overview-and-architecture
description: >
  What the Learning Tool MCP server is, the architectural stance that defines
  it, its layering, and the decisions an implementer must not accidentally
  reverse.
---

# 01 — Overview and Architecture

## What this application is

An open-source, single-user, fully local MCP (Model Context Protocol) server
that turns the user's own study material (PDFs) into a persistent study
system: it stores extracted material, flashcards, quiz questions, and answer
history as local JSON files; grades answers; tracks mastery; and schedules
reviews with the SM-2 spaced-repetition algorithm. In hosts that support the
MCP Apps extension, it also renders an interactive study widget.

It is driven entirely through an MCP client (Kiro, Claude Desktop, etc.) over
stdio. There is no standalone UI, no accounts, no credentials, no network
service.

## The defining architectural stance: host generates, server persists

The server deliberately contains **no LLM and calls no LLM**. The MCP host
that connects to it is already a language model, so content generation
(writing flashcards and quiz questions from the material) is the host's job.
The server's job is everything the host is bad at: durable storage, exact
grading, counting, and scheduling.

The canonical interaction loop:

1. `ingest_material` — server parses a PDF and stores its text chunks.
2. `get_material` — host reads the stored chunks.
3. `save_flashcards` / `save_quiz` — host writes back the items it generated.
4. `submit_response` — server grades and records each answer.
5. `get_session_state` / `get_due_items` — server reports progress and what
   to study next.

Grounding ("generate only from this document's material") is enforced by
instruction, not code: tool descriptions tell the host model how to behave.
This is the standard MCP pattern; an earlier version of this application
embedded a Bedrock LLM in the server and it was removed as redundant and
fragile.

## Constraints (all normative)

- Single user. There is no user id anywhere in the system.
- Fully local. No network calls of any kind at runtime.
- No database. Storage is a directory of JSON files.
- Python >= 3.10, fully type-hinted, modern syntax (`str | None`,
  `list[str]`, `from __future__ import annotations` in every module).
- Every public function, method, class, and module has a docstring
  (one-line summary; Args / Returns / Raises where applicable).

## Layering

Outer layers depend on inner ones, never the reverse. Package name:
`learning_tool`, under a `src/` layout.

| Layer | Module(s) | Responsibility | May import |
|-------|-----------|----------------|------------|
| MCP adapter | `server` | Register tools/resources on FastMCP, wire config, run stdio. Zero business logic. | `config`, `service` |
| Configuration | `config` | Read environment, produce immutable config. | stdlib only |
| Application service | `service` | Orchestration, grading, string→enum parsing, output shaping, export file writing. | `ingestion`, `storage`, `export` |
| Ingestion | `ingestion.pdf` | PDF text extraction + paragraph chunking. Pure w.r.t. app state. | `pypdf`, stdlib |
| Scheduling | `scheduling.sm2` | Pure SM-2 replay. No I/O, no clock access. | `storage.models` |
| Export | `export.anki` | Pure rendering of a document's items as Anki CSV text. No I/O; the service writes the file. | `storage.models` |
| Storage | `storage.models`, `storage.repository` | Domain models (pydantic) and the single file-storage boundary. | `scheduling` (repository only), `pydantic` |
| UI asset | `ui` package | One self-contained HTML file, shipped in the wheel. | — (data, not code) |

Two cross-cutting patterns:

- **Compute-from-history**: mastery buckets and SM-2 schedules are never
  persisted. Both are derived on demand by replaying the stored `Response`
  history. This keeps the schema minimal and the derived state always
  consistent with what was actually answered.
- **Clock injection**: `now` is resolved exactly once, at the service
  boundary, as timezone-aware UTC, and passed downward. Storage and
  scheduling never read the clock, so they are deterministic under test.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/learning_tool/` | The package (modules per the layering table; `ingestion/`, `scheduling/`, `storage/`, `ui/` are subpackages with init markers) |
| `tests/` | Pytest suite, one test file per source module (see spec 10) |
| `tools/` | Verification tools that are not part of the application and are not packaged: a stdio driver for the installed server, and a wire tracer and browser host stub for the widget. They exist because spec 10's suite cannot establish that the widget works. Nothing in `src/` imports them. |
| `specs/open/`, `specs/done/` | Living feature specs (workflow artifact, not application code) |
| `pyproject.toml` | Single config file: build, deps, entry point, pytest, ruff (see spec 02) |
| `README.md` | User-facing: how it works diagram, tool table, setup, example session, widget section |
| `CHANGELOG.md` | Keep-a-Changelog style, newest first |
| `.env.example` | Documents the one environment variable |
| `LICENSE` | MIT (0.7.0) |
| `.github/workflows/` | The CI quality gate: lint, format, type-check and test on every supported Python version, plus the `tools/` contract checks and a wheel-contents check (0.7.1) |

## Error philosophy

- Fail loudly and specifically. Unknown ids raise dedicated lookup errors;
  invalid enum strings raise `ValueError` with a message that lists the valid
  values; a naive datetime where an aware one is required raises `ValueError`.
- Never substitute defaults for missing required data. Empty PDF text is an
  error, not an empty document.
- Validation lives at the lowest layer that can enforce it (e.g. the
  multiple-choice option rules live on the domain model itself, so an invalid
  question can never be persisted by any code path).

## Acceptance criteria

1. THE system SHALL run as an MCP stdio server exposing exactly the 12 tools
   and 1 resource defined in spec 08. (11 through version 0.6.0; the twelfth,
   `export_document`, arrived in 0.7.0 with `future/anki-csv-export.md`.)
2. THE system SHALL make no network requests and load no LLM at runtime.
3. THE system SHALL persist all state as JSON files under a configurable
   local directory (specs 02, 06).
4. WHEN any inner-layer module is imported, THE system SHALL NOT transitively
   import an outer-layer module (no import cycles across the layering table).
