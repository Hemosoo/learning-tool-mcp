---
name: continuous-integration
description: >
  Adopt mypy, ship a typed-package marker, and run the full quality gate on
  every change in GitHub Actions. Takes the "Packaging, CI, and LICENSE"
  roadmap entry from direction to design; PyPI publication stays out.
---

# Continuous Integration and Type Checking

## Goal

The project is public and may now receive contributions, so the checks that
have been run by hand all along must run on every change, on every supported
Python version, without anyone remembering to. Second, spec 02 has always
claimed the code is "fully type-hinted and mypy-clean if run ad hoc" — an
unverified claim. This makes it verified and keeps it that way.

Derived from `rebuild/future/deferred-roadmap.md`, "Packaging, CI, and
LICENSE". The LICENSE half shipped in 0.7.0. PyPI publication is explicitly
**not** in scope here; see Trade-offs.

## Design

### Type checking

| Item | Rule |
|------|------|
| Tool | mypy, added to the dev extra with a version bound like every other dependency |
| Package code | Checked in **strict** mode. It already passes; the point is that it continues to |
| Tests and tools | Checked in default mode. Strict mode there reports dozens of missing annotations on fixtures and helpers, which is noise, not signal |
| Configuration | In `pyproject.toml`, beside pytest and ruff — spec 02's single-config-file rule still holds |
| Typed marker | The package ships a `py.typed` marker file |

The marker is not cosmetic. Without it, anything importing the package —
including this project's own test suite — is told the package is untyped and
every import is skipped, so strict checking of the package proves nothing to
consumers. It is package data, so the same hatchling rule that carries the
widget HTML carries it.

### The quality gate

One workflow, triggered on pushes to the default branch and on pull requests
against it, running two jobs:

| Job | Runs | On |
|-----|------|-----|
| Test | ruff check, ruff format --check, mypy (both modes), pytest | Every supported Python version |
| Integration | The `tools/` checks that the suite cannot perform: the stdio driver and the widget wire tracer | The lowest supported version only |

The test job covers every version spec 02 supports, because the floor is the
version most likely to break (newer syntax slipping in unnoticed) and the
newest is the one most likely to break next. Anything that runs by hand runs
here, in the same order, so a green local run means a green remote one.

The integration job exists because of spec 10: the pytest suite cannot
establish that the widget works, and `tools/README.md` names the two checks
that can be automated. Both already exit non-zero on failure. The wire tracer
needs a JavaScript runtime, which is why this is a separate job rather than a
step in the matrix.

### One change to an existing tool

The stdio driver currently resolves the server binary inside the project's
virtual environment. A CI runner installs the package without one, so the
driver SHALL prefer the virtual environment when present and fall back to the
console script on the PATH, reporting clearly when neither is found.

## Trade-offs (decided)

- **Every supported version, not just the newest.** Five jobs on a public
  repository cost nothing, and a floor of 3.10 is only real if something
  checks it.
- **No tox or nox.** The matrix belongs to CI; a second local runner would
  duplicate it and drift.
- **PyPI publication deferred.** It needs account-side configuration nobody
  can do from inside the repository — a project registered on PyPI and a
  trusted publisher tied to this workflow. Landing a release workflow before
  that exists would add a job that can only fail. It stays a roadmap entry
  until the account side is ready; the wheel already builds correctly and
  carries the licence, widget, and typed marker.
- **mypy not in the pre-commit sense.** No hook is installed; the gate is CI
  plus the documented local commands. Contributors are not required to adopt
  tooling to contribute.

## Acceptance criteria

1. THE system SHALL pass mypy in strict mode over the package, and in
   default mode over tests and tools, with no errors.
2. THE system SHALL ship a `py.typed` marker inside the package, present in
   the built wheel, so consumers and the test suite see the package as typed.
3. THE system SHALL declare mypy in the dev extra with a version bound, and
   configure it in `pyproject.toml`.
4. WHEN a change is pushed to the default branch or proposed against it, THE
   system SHALL run ruff check, ruff format --check, mypy and pytest on every
   Python version the project supports.
5. THE system SHALL additionally run the stdio driver and the widget wire
   tracer in CI, both of which fail the build on a non-zero exit.
6. WHERE no project virtual environment exists, THE stdio driver SHALL find
   the installed console script on the PATH instead of failing.
7. THE system SHALL NOT attempt to publish to any package index.
