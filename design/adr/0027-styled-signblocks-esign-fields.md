# 0027 — Styled signature blocks; instruments carry their e-sign fields

**Status:** accepted (2026-08)

## Context
Three signature macros had accreted (\signblock, \declsignblock,
\judgesignblock, \lettersignblock), and none fit a testamentary
execution clause: the will recited its date ("...on this ___ day of
___, 20__...") and the bare \signblock printed a second "Dated:"
line beneath it — a duplicate date on the instrument most likely to
be scrutinized. Separately, sending a built PDF to DocuSeal left
field placement to the signer: the renderer knows exactly where
every signature, date, and location blank sits, and was throwing
that knowledge away.

## Decision
1. **One macro, five styles**: \signblock{dated|decl|judge|letter|
   whereof}{...}. The whereof style owns the execution clause AND the
   signature area as one block — date recited once, location blank
   for the ceremony. Legacy spellings still build, mapped to styles
   with a stderr deprecation warning: a live matter mid-filing never
   breaks on a taxonomy change. Every reachable matter and fixture
   was migrated mechanically.
2. **Instruments carry their e-sign fields.** Signature blocks and
   witness grids draw DocuSeal text tags ({{...;role=...;type=...}},
   docuseal.com/docs/api) in white 6 pt in the inter-line gap:
   invisible in print, machine-readable in the text layer, stripped
   from executed documents by DocuSeal's default remove_tags. Roles
   number in document order, the order `sc docuseal send --to` assigns.
   Overlapping tags stagger vertically, and tags sit below their
   blanks so text extraction keeps printed lines whole (the
   typography suite enforces both).
3. **The official integration surface.** docuseal-client/client.py now speaks
   through DocuSeal's published Python SDK (pypi: docuseal) instead
   of a hand-rolled HTTP client — create_submission_from_pdf is
   exactly the one-off flow. DOCUSEAL_SERVER (the official CLI's
   variable) is honored alongside DOCUSEAL_URL. DocuSeal's official
   agent skills are REFERENCED, not vendored: they briefly lived here
   as a git submodule, which charged for its version pinning at every
   clone, in CI configuration, and in two tool breakages (the gitlink
   crashed the leak guard's readers; ruff reformatted vendored files)
   -- all for reference documentation nothing in the build executes.
   The docuseal skill points at their supported channel
   (npx skills add docusealco/docuseal-agent-skills); the API
   contract prosaic actually depends on is pinned by the SDK version
   in the lockfile.

## Consequences
A built instrument is e-sign-ready the moment it renders: `sc docuseal
send --to` in signing order and DocuSeal places every field. The
mock tests now pin prosaic's payloads THROUGH the SDK (the mock had
to learn HTTP/1.1 manners the real API has). Costs: a hidden text
layer in every unsigned instrument — accepted deliberately
(remove_tags strips it from executed documents, and wet-ink
ceremonies print it invisibly); and the taxonomy's deprecation
warnings will nag old sources until they are migrated, which is the
point. Amends ADR-0023 (the transport) and the signature-block
section of the markdown spec.
