---
name: testing-standards
description: >
  How the rebuilt application must be tested: real-implementation policy,
  fixtures, the minimal-PDF helper, per-module test files, and the invariant
  tests that lock critical behavior.
---

# 10 — Testing Standards

## Policy

- **No mocking of internal logic.** Tests exercise real implementations end
  to end within the process. Mock/monkeypatch only true external boundaries:
  the filesystem when simulating failures, and nothing else — the clock
  needs no mocking because `now` is injected by design (spec 05/07).
- **Real file storage** rooted at pytest's per-test temporary directory.
  Repository and service tests read and write actual JSON files.
- **Real PDF bytes.** A shared test helper hand-builds a minimal valid
  single-page PDF: a catalog, page tree, one page, a content stream drawing
  the given ASCII text, a standard font reference, and a correctly computed
  cross-reference table (byte offsets must be real so the PDF parser accepts
  it). Ingestion tests write these bytes to a temp file — the PDF library is
  never mocked.
- One test file per source module, named after it (config, pdf, sm2,
  repository, service, server). Each test validates exactly one behavior;
  multiple assertions verifying that one behavior are fine.
- Every error path in the specs has at least one test that triggers it.
- **The widget is the exception to "the suite is the definition of done."**
  These constraints leave no JavaScript runtime in the dev extra (spec 02),
  so every widget test asserts against the HTML source as text. Such
  assertions detect changes to the source; they cannot detect a wrong
  protocol field name, a wrong message order, or a CSS rule that never
  matches. In the reference implementation five such defects passed a fully
  green suite and left the widget unable to render at all. Widget tests are
  therefore necessary and not sufficient, and this is a known, accepted
  limit of the tooling constraint rather than a gap to be closed by writing
  more of the same tests.
- Consequently, a change to the widget SHALL additionally be exercised
  against a host implementation before it is considered done. Neither
  approach needs a new package dependency: a scripted DOM stub that records
  what the widget puts on the wire, or — with higher fidelity — a local
  browser page that loads the widget in a sandboxed iframe and answers the
  bridge. See `09-study-widget.md` for when to reach for each, and for using
  a reference example server to separate a local defect from a host defect.
  The reference implementation keeps all three under `tools/` (see
  `tools/README.md`); they are verification tools, not application code, and
  are not packaged.

## Required high-value tests (beyond per-spec acceptance criteria)

| Area | Test |
|------|------|
| Atomic writes | Force the atomic-replace operation to fail mid-save (monkeypatch it to raise); assert the original document file survives unchanged **and** no temp file is left in the directory |
| Corrupt store | A document file containing JSON that violates the model rules fails loudly on load (validation error), never yields a partial object |
| Stray files | Non-numeric-stem files in the documents directory are invisible to listing and id allocation |
| Id stability | Adding items across multiple calls never reuses an id; reset-progress preserves the counter |
| SM-2 | Deterministic replay cases: never-reviewed due; 1 → 6 → round(6×ease) progression; lapse resets; ease floor 1.3; confidence→quality mapping; naive `now` raises |
| Bucket precedence | Mastered-then-incorrect stays mastered; buckets sum to total |
| Grading | Quiz case/whitespace-insensitive equality; flashcard self-report validation; invalid enum strings raise ValueError listing valid values |
| Server contract | Exactly 11 tools with the expected names; the UI resource is registered at its URI with the mcp-app MIME type; get_due_items carries the resource-URI tool metadata |
| Description locks | delete_document and reset_progress descriptions contain "DESTRUCTIVE" and a confirm-with-user instruction; get_material's contains the only-source grounding instruction |
| Widget self-containment | The served widget HTML contains no `http://` or `https://` substrings |
| Widget protocol contract | The handshake params are `protocolVersion`, `appInfo` and `appCapabilities`, and neither `clientInfo` nor `capabilities` appears anywhere in the widget source |
| Widget message ordering | Size notifications are suppressed until the handshake completes |
| Widget theming | The two dark-palette blocks declare identical variable sets, and no variable is defined only inside a conditional block |
| UI tool metadata | `get_due_items` carries the resource URI under both the nested `ui` object and the flat `ui/resourceUri` key, and no other tool carries either |
| CSV quoting | Exported fields containing commas, quotes or newlines round-trip through a CSV reader |
| Empty export | A document with no exportable items raises and writes no file |
| Confidence breakdown | All four keys are always present; each answered item is counted once by its latest response; the counts sum to total minus remaining |

## Conventions

- Import shared constants (e.g. the data-dir environment variable name, the
  mastery threshold) from the source modules — never duplicate the values in
  tests, so they cannot drift.
- Service tests build the service over a temp directory; server tests build
  the FastMCP instance through the same factory used in production.
- Keep the suite runnable with plain `pytest` from the repo root (pytest
  config in pyproject provides paths).

## Acceptance criteria

1. THE test suite SHALL pass with no network access and no external
   services.
2. THE test suite SHALL cover every EARS requirement in specs 02–09 with at
   least one test.
3. THE test suite SHALL include all rows of the required-tests table above.
4. THE widget SHALL additionally be verified against a host implementation,
   because criteria 1-3 cannot establish that it works.
