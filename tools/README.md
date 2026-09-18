# tools

Verification tools that need no new package dependency. They exist because
of spec 10: the pytest suite can only assert against the widget's source
text, so it cannot establish that the widget actually works. These can.

None of them is part of the application. Nothing in `src/` imports them, and
the wheel does not ship them.

| Tool | Runtime | Answers |
|------|---------|---------|
| `stdio_check.py` | the project venv | Does the installed server behave correctly over real stdio? |
| `wire_trace.js` | node | What does the widget put on the wire, and in what order? |
| `widget_harness.py` + `widget_host.html` | the project venv + a browser | Does the widget actually render and respond in a sandboxed iframe? |

## stdio_check.py

Launches the installed console script against a throwaway data directory and
drives it as a host would: tool catalog, UI metadata under both keys, the
resource and its MIME type, widget self-containment, and the handshake field
names. Catches packaging and registration regressions without a real host.

```bash
.venv/bin/python tools/stdio_check.py
.venv/bin/python tools/stdio_check.py --pdf ~/study-pdfs/sample-cell-biology.pdf
```

Exits non-zero on any failed check, so it works in a pre-release check.

## wire_trace.js

Runs the widget's bridge under a DOM stub and prints every outgoing message,
then asserts the parts that source-text tests cannot see: that `ui/initialize`
is the *first* message, that it carries `appInfo` and `appCapabilities` and
not base MCP's `clientInfo`/`capabilities`, and that the size notification
follows the handshake rather than preceding it.

```bash
node tools/wire_trace.js
```

Every one of those checks corresponds to a defect that shipped past a green
pytest suite. Run it after any change to the widget's script.

## widget_harness.py

Serves `widget_host.html` — a host stub implementing the host half of the
bridge — plus the **live** widget and a **live** due-items payload, so a
browser reload always tests current source rather than a stale copy.

```bash
.venv/bin/python tools/widget_harness.py                      # document 1 in ~/.learning-tool
.venv/bin/python tools/widget_harness.py --document 2 --port 8910
```

The page logs both directions of the bridge, flags protocol errors in the
widget's own requests, offers a light/dark toggle (which exercises
`host-context-changed` and the theme-override rules), and has a
silent-host mode for checking that an unanswered handshake ends in visible
text rather than an endless wait.

Highest fidelity short of a real host: real browser, real sandboxed iframe,
real `postMessage`.

## When a real host renders nothing

Register a known-good reference example server alongside this one and call
its tool. If the reference renders and this widget does not, the fault is
local — compare the two servers' tool metadata and resource registrations.
If neither renders, the fault is the host's and no change here will help.
This is what finally isolated the 0.6.0 widget defects; see `HANDOFF.md`.
