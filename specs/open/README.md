# Open specs

Nothing is open.

The remaining ideas live in `rebuild/future/deferred-roadmap.md`: semantic
chunking, PyPI publication, a widget confidence display, mind maps,
knowledge graphs, and multi-user. They are direction, not design — each needs
its own spec here before it is built.

Two notes on what is left there:

- **PyPI publication** is the only part of the roadmap's "Packaging, CI, and
  LICENSE" entry still outstanding. It is blocked on account-side setup
  nobody can do from inside the repository: a registered project and a
  trusted publisher tied to this repository's release workflow. See
  `specs/done/continuous-integration.md` for why no release workflow was
  landed in advance.
- **Server-side LLM generation** was removed, not deferred. The
  host-generates/server-persists split is the defining architectural
  decision; see `rebuild/01`.
