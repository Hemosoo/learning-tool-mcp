# Handoff

State of the build as of 2026-09-22 (version 0.7.1), written for whoever (or
whatever) picks this up next. It is not part of the specified repository layout in
`rebuild/01-overview-and-architecture.md`; delete it once it stops being true.

**`rebuild/` remains the single source of truth.** This document never
overrides it. Where the two disagree, the spec wins and this file is stale.

## Where the build stands

Specs 01–10 are implemented, tested, and green. That is version **0.6.0**: 11
MCP tools, one `ui://` resource, JSON-file storage, SM-2 scheduling — exactly
the fidelity note at the bottom of `rebuild/README.md`.

The three specs in `rebuild/future/` are **not** implemented. That was
deliberate and is the one open decision; see [Open decision](#open-decision).

| Spec | Module(s) | Tests |
|------|-----------|-------|
| 02 configuration-and-packaging | `config.py`, `pyproject.toml` | `test_config.py` (7), `test_packaging.py` (8) |
| 03 domain-model | `storage/models.py` | `test_models.py` (9) |
| 04 pdf-ingestion | `ingestion/pdf.py` | `test_pdf.py` (8) |
| 05 sm2-scheduling | `scheduling/sm2.py` | `test_sm2.py` (11) |
| 06 storage-repository | `storage/repository.py` | `test_repository.py` (22) |
| 07 service-layer | `service.py` | `test_service.py` (29) |
| 08 mcp-server-and-tools | `server.py` | `test_server.py` (18) |
| 09 study-widget | `ui/study.html` | `test_widget.py` (29) |
| 01 layering (cross-cutting) | — | `test_layering.py` (3) |
| future/anki-csv-export | `export/anki.py`, `service.py`, `server.py` | `test_anki.py` (10), plus 5 in `test_service.py` |
| future/surface-confidence-in-stats | `storage/repository.py`, `service.py` | 3 in `test_repository.py`, 2 in `test_service.py` |

173 tests total, running in about a second.

## Verification status

Proven, in this session, by running it:

- `pytest` — 173 passed, no network, no external services.
- `ruff check .` and `ruff format --check .` — clean.
- `python -m build --wheel` — the wheel contains `learning_tool/ui/study.html`
  and the `learning-tool-mcp` console script. (`dist/` was deleted afterwards;
  rebuild it if you want to re-check.)
- Real stdio: the installed console script completed an MCP handshake, listed
  11 tools and 1 resource, and ran ingest → save_quiz → submit_response →
  get_due_items against real files on disk, including an error case.
- Clean-environment start: the binary works under `env -i` with only `HOME`
  set, which is how Claude Desktop launches it (no shell, no PATH).

**Proven since:** the widget renders and works in Claude Desktop, confirmed
by the user on 2026-09-16. Getting there took five defects' worth of fixes
(see the widget section below). Claude Code is **not** an MCP Apps host, in
the terminal or on the web; Claude Desktop is.

## The widget episode, and what it means for testing

The widget passed a fully green suite while being unable to render at all.
Five real defects were fixed before it worked in Claude Desktop:

| Defect | Why the suite missed it |
|--------|-------------------------|
| `ui/initialize` sent `clientInfo`/`capabilities` instead of `appInfo`/`appCapabilities` | Substring assertions confirmed the source said what the author intended; they cannot know the protocol |
| UI tool metadata omitted the flat `ui/resourceUri` key | The spec documented only the nested form |
| A size notification was emitted before the handshake | Ordering is invisible to substring assertions |
| An explicit host theme never overrode the OS preference | Requires a browser with a dark-mode OS to observe |
| An unanswered handshake waited forever | Requires a silent host to observe |

Two lessons for whoever comes next:

1. **The prose specs were not sufficient to build a correct widget, and
   neither were documentation summaries of the extension.** The field names
   that finally worked were read out of the extension SDK's own bundled
   `connect` implementation — the code hosts validate against. Specs 08 and
   09 have since been amended with the corrected contract, and spec 09
   carries a verification note.
2. **`test_widget.py` cannot establish widget correctness**, by construction:
   spec 02 fixes the dev extra to pytest and ruff, so no JavaScript runtime
   is available to the suite. Treat those tests as a change-detector for the
   source, not as evidence the widget works. Verify widget changes by driving
   them from a host — a browser page with a sandboxed iframe answering the
   bridge is the highest-fidelity option that needs no new dependency, and a
   known-good reference example server registered alongside this one is the
   fastest way to tell a local defect from a host defect.

## Decisions taken during the build

These are judgment calls the specs did not settle. Each is a place where a
future implementer might otherwise "fix" something that is deliberate.

**Four test files beyond the six spec 10 names.** Spec 10 lists test files for
config, pdf, sm2, repository, service, and server, but spec 10's own
acceptance criterion 2 demands coverage of every EARS requirement in specs
02–09. `test_models.py`, `test_widget.py`, `test_packaging.py`, and
`test_layering.py` close that gap (specs 03, 09, 02, and 01 respectively).

**The widget is tested by static assertions on its source.** Spec 02 fixes the
dev extra to pytest and ruff, so a JavaScript runtime or DOM harness would
violate the dependency constraint. `test_widget.py` therefore asserts against
exact substrings of the shipped HTML. *Consequence:* editing `ui/study.html`
will break those tests by design. Update them together, and treat a failure
there as "the contract moved," not as noise.

**Exactly two monkeypatches exist, both at true external boundaries.**
`os.replace` in the atomic-write test — spec 10 mandates it. `FastMCP.run` in
the entry-point test — otherwise the test blocks forever on stdio. No internal
logic is mocked anywhere, per spec 10's policy.

**The minimal-PDF helper builds multiple pages.** It takes one sequence of
lines per page and computes real cross-reference offsets. An earlier version
monkeypatched `PdfReader` to test the page-join rule; that violated spec 10's
"the PDF library is never mocked," so the helper grew multi-page support and
the monkeypatch went away. An empty page list produces a page with no
extractable text, which is how the textless-PDF error path is tested.

**`DEFAULT_DATA_DIR` is stored unexpanded** as the string `~/.learning-tool`
and expanded inside the loader, so tests that control `HOME` see the right
answer. Do not hoist `Path.home()` to import time.

**`StudyService._now()` is the only clock read in the system.** Storage and
scheduling take `now` as an argument. This is what makes the SM-2 tests
deterministic without mocking; keep it that way.

**Specs 08, 09 and 10 and `rebuild/README.md` were amended after host
verification.** The amendments are marked in each document and record the
wire contract the original prose underspecified. `rebuild/` is still the
single source of truth; these documents now match what actually works.

**`specs/open/` holds copies of the two actionable future specs;
`specs/done/` holds a pointer, not copies.** Duplicating all ten core specs
into `specs/done/` would create a second source of truth competing with
`rebuild/`. The layout table in spec 01 requires both directories to exist,
so both exist.

**No `_meta.ui.csp` on the widget resource, and that is correct.** In the MCP
Apps specification, `csp` declares which external origins an app may load
from. The widget loads none by design (spec 09 forbids external references and
a test enforces it), so there is nothing to declare. Spec 08 specifies only
`prefersBorder`. Do not add `csp` reflexively if a host fails to render.

**`get_due_items` metadata carries the same URI twice**, nested and flat,
in the `WIDGET_TOOL_META` constant. This is required, not redundant; the
constant's docstring says why.

**The widget source contains literal `…` and `—` characters**, not `\u`
escapes; `test_widget.py` asserts the literal characters. Either convention
works, but the two must agree.

## Things that are deliberate and easy to mistake for bugs

- `get_study_items` returns quiz **answers**. Spec 07 says so explicitly: it
  is the user's own local data, and `submit_response` remains the grader.
- The destructive tools take **no** `confirm` parameter. Spec 08 calls a
  host-set flag "theater"; confirmation is requested through the description,
  and `test_server.py` asserts both the wording and the absence of the
  parameter.
- Mastery beats recency. An item with 2 correct answers stays `mastered` even
  after a wrong answer. Spec 06's bucket precedence is ordered, and a test
  pins it.
- Schedules and mastery are **never persisted**. Both are replayed from
  `Response` history on every read. Adding a cached field would contradict
  spec 01's compute-from-history pattern.
- `next_item_id` is one counter shared by flashcards and quiz questions, so
  ids are unique across both lists within a document. `(item_type, item_id)`
  is the addressing pair.
- Ingestion of a textless PDF is an **error**, not an empty document. Spec 01:
  never substitute defaults for missing required data.

## Environment

- Virtualenv at `.venv/` (Python 3.14.4), package installed editable with the
  `dev` extra. Resolved dependency versions: `mcp` 1.30.0, `pypdf` 5.9.0,
  `pydantic` 2.13.5 — all inside spec 02's bounds.
- The code targets **Python 3.10**, the floor spec 02 sets, even though the
  venv is newer. `timezone.utc` is used rather than `datetime.UTC` (3.11+),
  and `test_packaging.py` skips itself when `tomllib` is unavailable (3.10).
- The project is its own git repository, published to GitHub under the MIT
  licence. Earlier in its history the enclosing repository was the user's
  home directory with nothing here tracked; that is no longer the case, but
  it is worth a `git rev-parse --show-toplevel` before any bulk `git add`.
- Claude Desktop is configured with this server at
  `~/Library/Application Support/Claude/claude_desktop_config.json`, pointing
  at the venv binary by absolute path, with one timestamped backup of the
  pre-existing config beside it. `allowDevTools: true` was added to
  `developer_settings.json` (a file that did not exist before) and left on
  deliberately; delete that file to undo it. The reference example server
  used as a control has been removed again.
- The verification tools used to debug the widget now live in `tools/`
  (spec 01's layout table and spec 10 were amended to cover them):
  `stdio_check.py` drives the installed server over real stdio,
  `wire_trace.js` prints and checks the widget's outgoing messages under a
  DOM stub, and `widget_harness.py` serves the live widget to a browser host
  stub. Run the first two before calling any widget change done; they exit
  non-zero on failure. See `tools/README.md`.

## Verifying you have not broken anything

```bash
cd <repo>
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
```

Both must be clean before any change is considered done, and since 0.7.1 so
must type checking:

```bash
.venv/bin/python -m mypy --strict src/learning_tool   # the package
.venv/bin/python -m mypy                              # tests and tools
```

All of this now runs in CI on every push and pull request, across Python 3.10
to 3.14, so a red badge means one of these commands fails locally too. For a
change that touches `ui/study.html`, these are necessary but not sufficient —
add:

```bash
.venv/bin/python tools/stdio_check.py     # registration and metadata
node tools/wire_trace.js                  # handshake shape and message order
.venv/bin/python tools/widget_harness.py  # render and interact in a browser
``` Spec 10's
required-tests table is the floor, not the ceiling: every EARS requirement in
specs 02–09 has at least one test, and `test_layering.py` enforces spec 01's
import rules mechanically, so a layering violation fails the suite rather than
passing review.

## What is left

**Nothing is blocked, and no decision is pending.** The two 0.7.0 features
are built and their specs have moved to `specs/done/`. What remains:

1. **`rebuild/future/deferred-roadmap.md`** — semantic chunking, PyPI
   publication, a widget confidence display, mind maps, knowledge graphs,
   multi-user. Direction only. Each needs a spec written to the quality of
   the others in `rebuild/` before any of it is built, and the roadmap says
   so itself. Do not build from the roadmap directly.
2. **PyPI publication** is the only part of "Packaging, CI, and LICENSE" left,
   and it is blocked outside the repository: it needs a registered project
   and a trusted publisher tied to this repository's release workflow. No
   release workflow was landed in advance, deliberately — it could only fail.
   Ask the user to do the account-side setup before writing one.
3. **Widget confidence display** — the cheapest remaining feature, because the
   data already reaches the widget: `submit_response` returns session state as
   its progress field, so the confidence mapping is in the widget's hands
   untouched. The progress footer renders four counts and ignores the rest.
   It is a roadmap entry, so it needs a spec first; the plumbing does not.

One note on the roadmap's "Explicitly removed" section: server-side LLM
generation was removed, not deferred. If a future request sounds like "have
the server generate the flashcards," that contradicts spec 01's defining
decision — raise it rather than implementing it.
