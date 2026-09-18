---
name: deferred-roadmap
description: >
  Direction-level descriptions of deferred features: acknowledged, roughly
  shaped, but not yet designed to spec quality.
---

# Future — Deferred Roadmap

These are deferred ideas, recorded so a rebuilder knows the intended
direction. Unlike the sibling specs in this folder, they are **not** designed
to implementation detail; each needs its own spec before being built. Listed
roughly by expected value.

## Semantic chunking

Replace paragraph-based chunking (spec 04) with meaning-aware concept
splitting. Constraint that makes this hard: the server must stay LLM-free
(spec 01), so semantic chunking must either use classical/statistical
techniques locally, or lean on the host (e.g. a tool flow where the host
proposes chunk boundaries for stored raw text). The ingestion module is the
only intended change surface; the chunk-list contract with storage stays.

## Packaging, CI, and LICENSE

The project intends to be genuinely open source: add a LICENSE file, publish
to PyPI, and add CI that runs pytest, ruff check, and ruff format --check on
every change. Adopt mypy in CI at the same time (the code is written to be
mypy-clean; spec 02 explains why it is not yet configured).

## Widget confidence display

Once surface-confidence-in-stats ships, the study widget's progress footer
could show the confidence breakdown. Keep the widget's constraints (spec
09): self-contained, no new tools, no destructive operations.

## Mind maps / visual knowledge structures

A visualization of a document's concepts and the user's mastery over them,
plausibly as a second MCP Apps resource. Blocked on a concept-relationship
model: today concepts are a flat ordered list with no edges.

## Knowledge graphs

Related to mind maps but data-first: extract entities/relations from
material into a queryable structure. Same LLM-free constraint applies —
likely a host-generates/server-persists pattern like items (the host
extracts, the server stores and serves the graph).

## Multi-user / auth

Explicitly out of scope for the current architecture (single-user is a
load-bearing simplification: no user ids anywhere, one data dir). Would
require revisiting storage layout, config, and every tool signature. Only
worth doing if the tool ever becomes a shared/hosted service — which would
also reopen transport (stdio → HTTP) and credential questions.

## Explicitly removed (do not resurrect)

Server-side LLM generation (the original v0.1.0 design with a Bedrock
backend and a pluggable LLM-provider abstraction) was **removed, not
deferred**. The host-generates/server-persists split is the defining
architecture decision; see spec 01.
