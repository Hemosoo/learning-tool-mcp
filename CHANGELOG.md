# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](./CHANGELOG.md), and this project adheres to semantic
versioning.

## [0.7.1] - 2026-09-22

### Added

- Continuous integration: every push and pull request runs ruff, mypy and
  the test suite on Python 3.10 through 3.14, plus the `tools/` server and
  widget contract checks and a wheel-contents check.
- mypy adopted: strict over the package, default over tests and tools, and
  configured in `pyproject.toml`. Spec 02 had claimed the code was
  mypy-clean since 0.1.0; that claim is now enforced rather than asserted.
- `py.typed` marker, so consumers (and this project's own test suite) see
  the package as typed instead of skipping every import.

### Changed

- `tools/stdio_check.py` falls back to the console script on the PATH when
  there is no project virtual environment, so it runs on a CI runner.

## [0.7.0] - 2026-09-16

### Added

- MIT licence, declared in the project metadata and packaged in the wheel.

- `export_document` tool: writes a document's flashcards and quiz questions
  to an Anki-importable CSV file and returns its path. Multiple-choice
  options are appended to the front field as lettered lines, the document
  title becomes the Anki tag, and `include_quiz` can narrow the export to
  flashcards. Defaults to `<data_dir>/exports/document-<id>-anki.csv`.
  Rendering is a pure module (`export.anki`); only the service touches the
  filesystem. Brings the tool catalog to 12.
- `get_session_state` now reports a `confidence` breakdown counting each
  answered item's latest self-reported confidence under the keys guessed,
  unsure, confident and unreported — always all four. The counts sum to
  total minus remaining. It reaches `submit_response`'s `progress` field for
  free, since that returns session state.

## [0.6.0] - 2026-09-15

### Fixed

- Study widget now renders in MCP Apps hosts. The `ui/initialize` handshake
  sends `appInfo` and `appCapabilities` as the extension requires, rather
  than base MCP's `clientInfo` and `capabilities`, which hosts silently
  never answer.
- `get_due_items` publishes its UI metadata under both the nested `ui` object
  and the flat `ui/resourceUri` key; hosts read the flat one, and without it
  the widget is fetched but never rendered.
- The widget sends nothing before the handshake completes, retries an
  unanswered handshake, and reports host silence instead of waiting forever.
- An explicit host theme now overrides the operating system's preference, so
  host-supplied colors can no longer mix with fallbacks from the opposite
  palette and render controls invisible.
- The widget answers host teardown in both its notification and request forms.

### Added

- PDF ingestion: `ingest_material` extracts text with pypdf and stores
  paragraph chunks as study material; `get_material` returns them with the
  grounding instruction that steers generation.
- Host-generated study items: `save_flashcards` and `save_quiz` persist what
  the host writes, with multiple-choice option rules enforced on the model
  itself, and `get_study_items` reads them back.
- Grading and progress: `submit_response` auto-grades quiz answers
  (case- and whitespace-insensitive) and records flashcard self-reports, with
  optional confidence; `get_session_state` buckets items into mastered,
  to_review, in_progress, and remaining.
- SM-2 scheduling: `get_due_items` replays each item's answer history to
  derive its schedule and returns what is due, most overdue first.
- Document management: `list_documents`, plus the destructive
  `delete_document` and `reset_progress`, which ask the host to confirm with
  the user rather than taking a confirmation flag.
- MCP Apps study widget at `ui://learning-tool/study`, linked from
  `get_due_items` and shipped inside the wheel.
- JSON file storage with atomic writes, one file per document, under
  `LEARNING_TOOL_DATA_DIR` (default `~/.learning-tool`).
