# 0007 — Overflow spills to MC-025, never shrinks below legibility

**Status:** accepted (2026-08)

## Context
Text longer than a form box must go somewhere. Truncation changes
what the court reads; unbounded shrinking produces technically-present
but practically unreadable filings; both are worse than the JC's own
convention: "See Attachment N." + an MC-025 attachment page.

## Decision
Fields marked `fit: overflow_attachment` never shrink below default
size; when text doesn't fit, the engine substitutes "See Attachment
N.", appends a correctly captioned MC-025 carrying the full text, and
flips any linked attached/inline checkboxes to match reality.

## Consequences
Overflow output is what a careful practitioner would file; the
attached/inline state can't lie. MC-025 becomes core infrastructure
(its descriptor must stay verified); merged attachments' fields live
outside the root AcroForm tree, which inspection tooling must account
for (walk page widgets, not get_fields).
