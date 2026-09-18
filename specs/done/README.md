# Completed specs

The version 0.6.0 core — 11 MCP tools, one `ui://` resource, JSON-file
storage, SM-2 scheduling — is specified by `rebuild/01` through `rebuild/10`,
which remain the single source of truth for this application's behavior.
Those documents have since been amended to describe 0.7.0, with each change
naming the version that introduced it.

Feature specs move here from `specs/open/` once they ship.

| Spec | Shipped | What it added |
|------|---------|---------------|
| `anki-csv-export.md` | 0.7.0 | The `export_document` tool and the pure `export.anki` renderer, taking the catalog to 12 tools |
| `surface-confidence-in-stats.md` | 0.7.0 | The `confidence` breakdown on session state, and therefore on `submit_response` progress |
