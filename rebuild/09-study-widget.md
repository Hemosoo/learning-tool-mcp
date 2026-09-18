---
name: study-widget
description: >
  The MCP Apps study widget: a single self-contained HTML file that renders
  an interactive study session in supporting hosts, speaking raw JSON-RPC
  over postMessage. Bridge protocol, state machine, and UI behavior.
---

# 09 — Study Widget (MCP Apps)

## Role and constraints

One HTML file in the package's `ui` subpackage, served at
`ui://learning-tool/study` (spec 08). It follows the MCP Apps extension
(`io.modelcontextprotocol/ui`, SEP-1865, protocol version **2026-01-26**).

Hard constraints:

- **Self-contained**: all CSS and JavaScript inline; no external references
  of any kind — the sandboxed iframe may have no network access. A test
  asserts the file contains no `http://` or `https://` substrings.
- **No SDK**: the host bridge is raw JSON-RPC 2.0 over the browser
  postMessage channel to the parent window. No build step, no dependencies.
- **No new business logic**: the widget only calls existing server tools.
  Destructive tools (delete_document, reset_progress) are deliberately
  excluded from the widget — they require host-mediated confirmation.

## Bridge protocol

Message plumbing:

- Outgoing requests carry incrementing numeric ids; a pending-request map
  resolves or rejects them when a response with a matching id arrives (an
  error member rejects with the error's message). Notifications carry no id.
- Incoming messages are ignored unless they declare JSON-RPC 2.0. Incoming
  notifications dispatch to per-method handlers.

Lifecycle:

1. On load, THE widget SHALL send a `ui/initialize` request whose params
   carry exactly these three fields, and no others:

   | Field | Value |
   |-------|-------|
   | `protocolVersion` | 2026-01-26 |
   | `appInfo` | The widget's own name and version |
   | `appCapabilities` | An object whose `availableDisplayModes` is the single entry `inline` |

   The field naming is a trap worth stating outright. The extension's
   `ui/initialize` is **not** base MCP's `initialize`: there is no
   `capabilities` field and no `clientInfo` field, and identification is
   carried by `appInfo`. Hosts validate these params against a schema, so a
   request carrying the base-MCP spellings is never answered — it is not
   rejected with an error, it is simply ignored, and the widget waits
   forever. This exact mistake cost a full debugging session; the params
   above are taken from the extension SDK's own connect implementation,
   which is the shape hosts actually validate.

2. WHEN the initialize result arrives, THE widget SHALL apply the host
   context it may carry, THEN send a `ui/notifications/initialized`
   notification, and start observing its own body size. The host clears its
   own loading state on that notification and on nothing else.
3. THE widget SHALL send **nothing at all** before the initialize result
   arrives. Traffic that precedes the handshake — a size notification
   emitted by a first render, for instance — is a protocol violation, and a
   host may disregard every message that follows it.
4. THE widget SHALL re-send the initialize request periodically until it is
   answered, up to a bounded number of attempts (the reference
   implementation uses 12 attempts at 400 ms). Neither the extension nor the
   core specification fixes any ordering between the host attaching its
   message listener and the app loading, so a single unanswered request is a
   race the widget must survive.
5. IF the attempts are exhausted with no answer at all, THEN THE widget
   SHALL render a message saying so. A silent host must produce visible
   text, never an unbounded wait.
6. IF initialization fails with an error, THEN THE widget SHALL render the
   failure message in its status area instead of dying silently.

Host context (theming): the host context carries its style variables at
`styles.variables` (not at the top level) and its theme at `theme`. THE
widget SHALL set each provided variable as a CSS custom property on the
document root, and SHALL apply the theme as a `data-theme` attribute on that
same root.

The stylesheet defines its own light/dark fallback values for every variable
it uses (background, secondary background, primary/secondary text, border,
success/danger backgrounds and text, font, radius), so it renders correctly
before or without host theming. Those fallbacks are declared in three
layers, and all three are required:

1. The complete light palette on the bare root.
2. The dark palette under a `prefers-color-scheme: dark` media query,
   qualified so that it does not apply when the host has asked for light.
3. The dark palette again, unconditionally, when the host has asked for dark.

Layers 2 and 3 are what make a host theme win over the operating system's
preference. Without them the attribute is inert, and a host that supplies
only *some* variables mixes its values with fallbacks from the opposite
palette — in practice a white background inherited from the host beside
near-white text inherited from the OS, which renders controls invisible
rather than merely ugly.

A `ui/notifications/host-context-changed` notification carries a partial host
context and re-applies the same handling.

Tool-call linkage (the widget is bound to get_due_items):

- `ui/notifications/tool-input`: carries the linked call's arguments; the
  widget captures the document id from them.
- `ui/notifications/tool-result`: carries the linked call's result — the
  get_due_items payload. IF the result is marked as an error, THEN THE
  widget SHALL show the error text in its status area; malformed payloads
  are caught and shown likewise — a bad result must never kill the widget
  silently.
- `ui/notifications/tool-cancelled`: the widget shows a cancelled status.
- Teardown: the host announces teardown with a
  `ui/notifications/request-teardown` notification, and older wording also
  describes a `ui/resource-teardown` request expecting an empty result. THE
  widget SHALL handle both, and SHALL answer any inbound request it
  recognizes rather than leaving the host waiting on a response.
- Tool result payload extraction: prefer the result's structured content;
  otherwise find the first text content part and parse it as JSON (FastMCP
  serializes dict returns as JSON text).

Outgoing tool calls: interactivity goes through `tools/call` requests — the
widget calls `submit_response` (grading) and `get_due_items` (refresh) only.

Sizing: after every render, and on any observed body resize, THE widget
SHALL send `ui/notifications/size-changed` with the body's scroll width and
height — deduplicated so unchanged dimensions send nothing.

## Widget state

A single state object drives rendering: document id and title; the due-item
queue (as served, most overdue first) and current index; whether the current
flashcard's back is revealed; the last progress dict from submit_response; a
one-shot flash message (ok/bad + text); a busy flag that disables inputs
during in-flight calls; and a status line used before data arrives
("Connecting to host…" → "Waiting for due items…" → error, cancelled, or
handshake-unanswered text). The handshake-unanswered state is terminal and
must be reachable: it is the only signal distinguishing a host that declined
to answer from a widget that failed to load at all.

## UI behavior

Rendering is full re-render from state into the app container; a heading
shows the document title, a muted line shows "Item N of M due" or a
no-items message.

Flashcards:
1. Front text first with a "Show answer" button.
2. WHEN revealed, THE widget SHALL show the back plus "I got it" /
   "I missed it" buttons and the confidence picker; the two buttons submit
   the self-reports "correct" / "incorrect" respectively.

Quiz questions:
- Multiple choice: one button per option; clicking submits that option's
  exact text (plus picked confidence).
- Short answer: a text input (Enter submits) and a Submit button; blank
  input does not submit.

Confidence picker: a select offering an unset placeholder plus guessed /
unsure / confident; unset sends no confidence argument at all.

Submission flow:
1. WHILE a call is in flight, THE widget SHALL ignore further submissions
   and disable action buttons.
2. WHEN submit_response succeeds, THE widget SHALL store the returned
   progress, flash "Correct!" on success — on failure, flash the correct
   answer for quiz items ("Incorrect — answer: …") or "Marked for review."
   for flashcards — then advance to the next queued item with the reveal
   state reset.
3. IF the call fails, THEN THE widget SHALL flash the error and stay on the
   item.
4. WHEN the queue is exhausted, THE widget SHALL show an all-caught-up card
   with a "Refresh due items" button that re-calls get_due_items and reloads
   the queue.

Progress footer: whenever a progress dict exists, show mastered /
in progress / to review / remaining counts.

## Acceptance criteria

1. THE widget SHALL contain no external URL references (self-containment
   test at the server level).
2. THE widget SHALL complete the initialize handshake before rendering
   interactive content, sending `appInfo` and `appCapabilities` (never
   `clientInfo` or `capabilities`), sending nothing before the result
   arrives, retrying while unanswered, and rendering visible text on both an
   error and an exhausted retry budget.
3. WHEN the linked tool result arrives, THE widget SHALL load the due queue
   from it, handling error results and malformed payloads by showing status
   text.
4. THE widget SHALL call only submit_response and get_due_items via
   tools/call — never the destructive tools.
5. THE widget SHALL notify size changes (deduplicated) after renders and
   body resizes.
6. THE widget SHALL apply host-provided theme variables from
   `styles.variables` and let an explicit host theme override the operating
   system's preference in both directions, with working light/dark fallbacks
   otherwise.
7. THE widget SHALL answer host teardown messages in both their notification
   and request forms.

## A note on verifying this spec

Specs 02 and 10 fix the test tooling to pytest and ruff, which means the
widget's own tests can only assert against its source text. Those assertions
cannot catch a wrong protocol field name, a wrong message order, or a theme
rule that never matches: every defect listed in this document's history
passed a full green suite. Verifying a change to this widget therefore means
driving it from a host implementation, not just running the suite. Two
approaches both proved decisive, in ascending order of fidelity: a scripted
DOM stub that captures what the widget puts on the wire, and a real browser
page that loads the widget in a sandboxed iframe and answers the bridge.

When a host renders nothing and the cause is unclear, the fastest discriminator
is to register a known-good reference example server alongside this one. If the
reference renders and this widget does not, the difference is in this server's
registration or this widget's messages, and comparing the two servers' metadata
and wire traces will find it. If neither renders, the host is the problem and no
change here will help.
