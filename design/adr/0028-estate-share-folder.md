# 0028 — Estate matters publish a share folder: destination, never source

**Status:** accepted (2026-08)

## Context
An estate plan's audience is unlike litigation's: beneficiaries,
successor fiduciaries, and counsel need durable read access to the
executed instruments — possibly years later, possibly under stress,
certainly without installing anything — and they need a place to
put things back (a death certificate) without write access to the
record. The matter directory itself is the wrong thing to share: it
is a workshop full of drafts, sidecars, state, and history.

## Decision
`matter.yaml` gains `case.type` (`litigation` default | `estate`),
and estate matters keep a `share/` directory under the contract in
specs/matter.md: COPIES of executed deliverables only, verified
hash-identical after every copy-in; a plain-language `START HERE.md`
covering the legal architecture (with a one-line prosaic credit and
link); the cryptographic material relegated to `Verification/` so
the tree reads like a folder a meticulous person keeps by hand; an
`Inbox/` the shared-with may write to (intake, not archive); and a
`Public/` for recorded and to-be-recorded instruments whose sharing
is deliberately broader. Drive permissions are set by hand and
documented in the folder itself — prosaic ships the scaffold and the
convention, not a sharing API.

## Consequences
The workshop/publication split that already protects litigation
matters (repo private, filings public) gets an estate-shaped form:
git history and originals stay in the matter; the share folder can
be regenerated from them at any time and is never load-bearing.
Costs: real duplication of the executed PDFs (deliberate — the copy
is the product), and a convention that the type field gates rather
than machinery enforcing it. Extends ADR-0025.
