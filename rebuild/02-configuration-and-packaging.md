---
name: configuration-and-packaging
description: >
  Environment-based configuration, project metadata, dependencies with version
  bounds, entry point, and lint/format/test tooling configuration.
---

# 02 — Configuration and Packaging

## Configuration module

The server needs exactly one piece of configuration: where to store data.

| Item | Value |
|------|-------|
| Environment variable | `LEARNING_TOOL_DATA_DIR` |
| Default when unset/blank | `~/.learning-tool` (hidden folder in the user's home) |
| Config object | An immutable (frozen) dataclass with a single field `data_dir` of path type |

Behavioral contract of the config loader:

- It accepts an optional environment mapping parameter; when omitted it reads
  the live process environment. The parameter exists purely so tests can
  inject an environment without monkeypatching.
- The raw value is stripped of whitespace; an empty or whitespace-only value
  is treated as unset.
- A set value has `~` expanded to the user's home directory.
- The loader does **not** create the directory — the storage layer creates it
  lazily on first write. Loading config must have no side effects.
- The environment variable name is defined once as a module-level constant
  and referenced by tests (single source of truth).

## Project metadata (pyproject)

| Field | Value |
|-------|-------|
| Distribution name | `learning-tool-mcp` |
| Package name | `learning_tool` (src layout: `src/learning_tool`) |
| Version | Starts at 0.6.0 for a rebuild of the core specs; also duplicated as the package's `__version__` attribute in its init module. Bump both together. |
| Description | An MCP server that turns PDFs into flashcards and quizzes, with session tracking |
| Python requirement | `>=3.10` |
| Build backend | hatchling, wheel packages `src/learning_tool`. Hatchling includes non-Python package files (the widget HTML) in the wheel automatically — no extra package-data configuration is needed or wanted. |
| Console script | `learning-tool-mcp` → the server module's `main` function |
| Licence | MIT, declared as an SPDX expression with the `LICENSE` file listed as a licence file so the wheel carries it. Added in 0.7.0 when the project was first published; `future/deferred-roadmap.md` lists the rest of that work (PyPI, CI, mypy) as still unbuilt. |

## Dependencies (bounds are normative)

| Dependency | Bound | Why the bound |
|------------|-------|---------------|
| `mcp` | `>=1.12,<2` | Server targets the v1.x FastMCP API; v2 is a breaking rewrite. The `meta=` parameter on tool and resource decorators (used by the MCP Apps widget) is verified working on 1.28. |
| `pypdf` | `>=4,<6` | PDF text extraction. |
| `pydantic` | `>=2,<3` | Domain models double as the JSON (de)serializer and as validators of untrusted file content on load. |

Dev extra (`[dev]`): `pytest>=8,<9`, `ruff>=0.15,<1`.

Deliberately absent: any LLM SDK, any database driver, any HTTP client, any
MCP-Apps/widget SDK. Adding one violates spec 01's constraints.

## Tooling configuration (in pyproject)

- **pytest**: test paths `tests`, `pythonpath` includes `src` (so tests import
  the package without installing it).
- **ruff**: line length 88; lint select pycodestyle errors and warnings,
  pyflakes, import sorting, and pyupgrade (E, W, F, I, UP); ignore E501
  because the formatter owns line length and E501 only nags about strings and
  comments the formatter cannot wrap. `ruff format` is the formatter.
- mypy is intentionally **not** configured, but all code must be fully
  type-hinted and mypy-clean if run ad hoc.

## Acceptance criteria

1. WHEN `LEARNING_TOOL_DATA_DIR` is unset or blank, THE system SHALL use
   `~/.learning-tool` as the data directory.
2. WHEN `LEARNING_TOOL_DATA_DIR` is set, THE system SHALL use its value with
   `~` expanded.
3. WHEN configuration is loaded, THE system SHALL NOT create any directory.
4. THE system SHALL install a console script named `learning-tool-mcp` that
   starts the stdio server.
5. THE system SHALL build a wheel that contains the study-widget HTML file so
   the installed package can serve it without a repo checkout, and the
   `LICENSE` file alongside it.
6. THE system SHALL pass `ruff check` and `ruff format --check` with the
   configuration above.
