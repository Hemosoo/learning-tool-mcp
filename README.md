# Learning Tool MCP

[![CI](https://github.com/Hemosoo/learning-tool-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Hemosoo/learning-tool-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

An MCP server that turns your own PDFs into flashcards and quizzes, grades your
answers, and schedules reviews with the SM-2 spaced-repetition algorithm.

Single user, fully local, no accounts, no network calls, no database: your
study material lives in a directory of JSON files on your machine.

## How it works

The server contains no LLM and calls none. The MCP host you are already
talking to is the language model, so it writes the study items; the server does
the parts a model is bad at: durable storage, exact grading, counting, and
scheduling.

```
   your PDF
      |
      | ingest_material        parse + chunk
      v
 +----------------+  get_material   +---------------+
 |  Learning Tool | --------------> |   MCP host    |
 |     server     |                 | (the model)   |
 |                | <-------------- |               |
 | JSON files     |  save_flashcards / save_quiz
 | on your disk   |
 |                | <-------------- your answers via submit_response
 |  SM-2 replay   | --------------> get_due_items / get_session_state
 +----------------+
```

Generation is grounded by instruction: `get_material` tells the host to build
items from that document's material only.

## Tools

| Tool | What it does |
|------|--------------|
| `ingest_material` | Parse a PDF and store its text as study material |
| `get_material` | Return the stored material (the only source for generation) |
| `list_documents` | List stored documents with ids, titles, and counts |
| `get_study_items` | Return the saved flashcards and quiz questions |
| `get_due_items` | Return what is due now, most overdue first (renders the widget) |
| `save_flashcards` | Store host-generated flashcards |
| `save_quiz` | Store host-generated quiz questions |
| `submit_response` | Grade and record one answer, return updated progress |
| `get_session_state` | Return mastered / to_review / in_progress / remaining / total, plus a confidence breakdown |
| `export_document` | Write a document's items to an Anki-importable CSV file |
| `delete_document` | Destructive: delete a document and everything stored against it |
| `reset_progress` | Destructive: erase answer history, keep the items |

## Setup

Requires Python 3.10 or newer.

```bash
pip install learning-tool-mcp
```

From a checkout:

```bash
pip install -e ".[dev]"
```

Register the server with your MCP client (Claude Desktop, Kiro, and others use
this shape):

```json
{
  "mcpServers": {
    "learning-tool": {
      "command": "learning-tool-mcp",
      "env": {
        "LEARNING_TOOL_DATA_DIR": "~/.learning-tool"
      }
    }
  }
}
```

`LEARNING_TOOL_DATA_DIR` is the one setting there is; leave it out and the
server stores everything under `~/.learning-tool`. The directory is created on
first write.

## Example session

> **You:** Ingest `~/papers/photosynthesis.pdf` and make me 5 flashcards.
>
> The host calls `ingest_material`, then `get_material` to read the stored
> chunks, writes 5 cards from that material, and calls `save_flashcards`.
>
> **You:** Quiz me.
>
> The host calls `get_due_items`, asks you the first question, and calls
> `submit_response` with your answer. Quiz answers are graded automatically;
> flashcards are self-reported as `correct` or `incorrect`, optionally with a
> confidence of `guessed`, `unsure`, or `confident`.
>
> **You:** How am I doing?
>
> `get_session_state` reports how many items are mastered, in progress, to
> review, and untouched. An item counts as mastered after 2 correct answers.
> It also breaks your answered items down by the confidence you last reported
> on each, so you can see how much of your progress you were sure about.
>
> **You:** Export these to Anki.
>
> `export_document` writes an Anki-importable CSV next to your data and tells
> you the path. Import it in Anki with File → Import.

Scheduling is never stored: every schedule is replayed from your answer
history, so what you see always matches what you actually answered.

## Study widget

In hosts that support the MCP Apps extension, calling `get_due_items` also
renders an interactive study widget: flip cards, answer multiple-choice and
short-answer questions, report confidence, and watch progress update as you go.
The widget is a single self-contained HTML file shipped inside the package. It
talks to the host over postMessage and calls only `submit_response` and
`get_due_items` — the destructive tools are deliberately out of its reach.

Hosts without the extension ignore the widget and work exactly as before.

## Development

```bash
pytest                            # the full suite, no network needed
ruff check . && ruff format --check .
mypy --strict src/learning_tool   # the package
mypy                              # tests and tools
```

CI runs all of the above on Python 3.10 through 3.14 for every push and pull
request, so a green local run means a green remote one.

Changes to the study widget need more than the suite, which can only assert
against the widget's source text. `tools/` holds the verification tools —
a stdio driver, a wire tracer, and a browser host stub; see `tools/README.md`.

Specifications live in `rebuild/` (the complete, code-free specification of
this application) and `specs/open/` (designed but unbuilt features).
