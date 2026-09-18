# Rebuild Specification Suite

This directory is a complete, code-free specification of the Learning Tool MCP
server. An AI model (or a human) should be able to recreate the entire
application from these documents alone, without ever seeing the original
source code.

## Ground rules for the implementer

1. **No document here contains code**, and none should be added. Behavior is
   specified in prose, field tables, mathematical formulas, and EARS
   requirements (`WHEN / THE system SHALL ...`). Every EARS requirement maps
   to at least one test.
2. **Build in the order listed below.** Each spec depends only on specs
   before it. The layering is strict: inner layers never import outer ones.
3. **The acceptance criteria are the definition of done** for each spec.
   Implement them as automated tests (see `10-testing-standards.md`).
4. Specs in `future/` describe features that were designed but not yet
   implemented in the reference application. Build the core (01-10, which
   yields version 0.6.0) first; the future specs then take the project to
   0.7.0 and beyond.

## Build order

| # | Spec | Layer | Depends on |
|---|------|-------|-----------|
| 01 | overview-and-architecture | — (read first) | — |
| 02 | configuration-and-packaging | project scaffold | 01 |
| 03 | domain-model | innermost | 01 |
| 04 | pdf-ingestion | pure module | 01 |
| 05 | sm2-scheduling | pure module | 03 |
| 06 | storage-repository | storage boundary | 03, 05 |
| 07 | service-layer | orchestration | 04, 06 |
| 08 | mcp-server-and-tools | adapter | 07 |
| 09 | study-widget | MCP Apps UI | 08 |
| 10 | testing-standards | cross-cutting | all |
| future/anki-csv-export | new tool | 07, 08 |
| future/surface-confidence-in-stats | field extension | 06, 07 |
| future/deferred-roadmap | direction only | — |

Both `future/` feature specs are **built** as of version 0.7.0; only
`deferred-roadmap` remains unbuilt, and by design — each of its entries needs
its own spec first.

## Fidelity notes

These specs describe version 0.7.0 of the reference implementation exactly:
12 MCP tools, one `ui://` resource, JSON-file storage, SM-2 scheduling.
Where a number appears (tool counts, thresholds, version bounds), it is
normative, not illustrative.

Specs 01 and 04 through 10 originally described 0.6.0 — 11 tools, session
state without a confidence breakdown. Building the two `future/` specs
changed numbers those documents called normative, so they were amended in
place and each change names the version that introduced it. Read `future/`
for the design rationale behind those two features; read the core specs for
what the system does now.

Specs 08, 09 and 10 were amended after the rebuilt widget was driven from a
real MCP Apps host. The earlier wording was accurate about intent but
underspecified the wire contract, and an implementation faithful to it was
accepted by the host and then silently never rendered. The amended sections
state the handshake params, the dual-key tool metadata, the message
ordering, and the theme layering exactly, and spec 10 records why a green
test suite cannot establish that the widget works.
