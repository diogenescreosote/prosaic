# 0015 — An unfiled document says so on every page

**Status:** accepted (2026-08)

## Context
The `notreal:` convention marks drafts, unsent correspondence, and
simulations. It marked the *source*: a YAML key or an HTML comment
that an agent or a person reading the Markdown would see. The rendered
output carried no trace of it.

The output is the dangerous artifact. A draft declaration and a filed
one are the same object — same caption, same 28-line grid, same
signature block — and nothing about the PDF distinguishes them. That
file gets attached to an email, printed, put in a stack, handed across
a table. The `notreal:` marker was invisible at exactly the moment it
mattered, and the failure it guards against is not hypothetical: it is
sending opposing counsel a document that was never meant to leave, or
filing a version that was still being argued over.

## Decision
Any document whose source carries `notreal:` renders that marker as a
red banner in the top margin of **every** page, in the PDF, in the
DOCX page header, and as a delimited first line in the TXT. The banner
is the marker's own words, upper-cased and normalized to the house
dash rule — so it says *why* the document is not real ("not filed" and
"not sent" are different facts, and a simulation is a third thing)
rather than a generic "DRAFT". It sits in margin the 28-line grid does
not use, so it cannot repaginate the document. Clearing it means
removing `notreal:` from the source and rebuilding.

## Consequences
The marker is now visible to everyone who touches the artifact, not
only to whoever opens the Markdown — including the recipient of a
mistaken send, who can say so before acting on it. Clearing it becomes
a deliberate act by someone who knows the document is going out, which
is the right ceremony for that transition.

Because the banner lives in the margin and the DOCX page header, it
neither shifts the line grid nor sits in the body text a lawyer is
editing: a draft and its filed version break pages identically, so
page-and-line citations taken against the draft hold, and there is no
banner paragraph in the DOCX to delete by accident or leave in by
accident.

Costs: every existing `notreal:` marker is now rendered text, so
markers written casually read oddly in caps, and the dash-rule
normalization exists precisely because they were written before anyone
expected them to print. Test fixtures and the demo matter now carry
banners — correct, but it changed their rendered output. And the
protection is only as good as the marker: a draft whose source never
got `notreal:` gets no banner, which is why the convention docs put
the marker on the source at creation rather than before sending.
Alternatives: a diagonal watermark across the page (rejected — it
obscures text and photocopies badly, and a document that cannot be
read cannot be reviewed); a separate `draft: true` key (rejected —
a second marker to keep in step with `notreal:`); banner only on the
first page (rejected — pages get separated, and the loose one is the
one that gets misread).
