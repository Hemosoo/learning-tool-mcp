---
name: surface-confidence-in-stats
description: >
  IMPLEMENTED in v0.7.0 (this document is the design record): extend
  get_session_state with a breakdown of each answered item's latest
  self-reported confidence.
---

# Surface Confidence in Stats (shipped in 0.7.0)

## Goal

Make the confidence data users already submit visible: the session state
(specs 06/07) gains a `confidence` breakdown counting each answered item's
most recent response by confidence level. Confidence has fed the SM-2
quality grade since it was introduced, but nothing reports it back.

## Design

- Extend the session-state aggregate with a `confidence` mapping holding
  exactly four keys: guessed, unsure, confident, unreported. All keys are
  always present (zeroes included) so consumers never need to key-check.
- Semantics: for each **answered** item, tally the confidence of its
  **latest** response; a null confidence counts as unreported. Latest-per-
  item (not all responses) because the buckets describe current state, and
  stale confidence from three answers ago says nothing about it.
  Never-answered items are excluded — they are already the remaining bucket.
- Invariant (tested): the confidence counts sum to total minus remaining.
- Computed inside the existing session-state pass in the repository — the
  same compute-from-history pattern as everything else; no schema change,
  nothing persisted.
- The submit_response operation returns session state as its progress field,
  so the new breakdown propagates to it with no service change. The study
  widget ignores fields it does not render; displaying confidence there is a
  separate possible follow-up.

## Trade-offs (already decided)

- Latest response per item vs all responses: all-responses double-weights
  frequently answered items and mixes stale signal with current state.
- Flat mapping vs per-bucket breakdown: confidence-within-mastered is richer
  but quadruples the payload for a question nobody has asked yet.

## Acceptance criteria

1. WHEN get_session_state is called, THE system SHALL include a confidence
   mapping with exactly the keys guessed, unsure, confident, unreported.
2. THE system SHALL count each answered item once, by its most recent
   response's confidence, with null counted as unreported.
3. THE system SHALL satisfy: sum of confidence counts = total − remaining.
4. WHEN submit_response returns progress, THE system SHALL include the same
   confidence mapping.
5. WHEN a document has no responses, THE system SHALL return all-zero
   confidence counts rather than omit the field.
