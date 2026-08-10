# 0017 — The draft banner stamps the whole packet, in a reclaimed band

**Status:** accepted (2026-08)
**Amends:** [ADR 0015](0015-unfiled-documents-announce-themselves.md) —
the banner covered pages the generator drew; it now covers every page
of the assembled document.

## Context
ADR-0015 stamped `notreal:` on every page the pleading generator drew,
and the roadmap recorded the gap it left: a filled Judicial Council
cover sheet and merged exhibit pages carried nothing. On a real draft
subpoena that meant pages 3–6 marked and pages 1–2 clean — and page 1,
the SUBP-010, is the page that looks most like a document ready to
serve. A partially marked packet is worse than an unmarked one,
because the clean pages read as a deliberate statement that the form
is final.

That gap was left open on purpose: stamping a mandatory Judicial
Council form is a decision with consequences, and it was not one to
take unilaterally. It has now been taken.

The obvious implementation does not work. A pleading page has an inch
of unused top margin; a JC form has none — its own header begins about
a quarter inch from the paper edge. An overlaid banner lands squarely
on "ATTORNEY OR PARTY WITHOUT ATTORNEY" and makes both it and the
banner unreadable, which is exactly what the first attempt produced.

## Decision
The banner is applied once, over the finished PDF, after the cover
sheet is prepended and the exhibits merged — not by each page-drawing
class. Consumer notices, which are separately served documents, each
get their own stamp.

The band it occupies is **reclaimed, not overlaid**: every page's
content is scaled down by a few percent, anchored at the bottom and
centred horizontally, and the banner goes in the strip that frees up.
That cannot collide with anything on any page, whatever the page
holds — form, exhibit, or generated text. Annotation rectangles are
transformed with the content, so links, form widgets and redaction
labels stay where they belong.

## Consequences
Every page of a draft packet says it is a draft, including the form
someone would otherwise mistake for final. Pagination is untouched,
because the scaling happens after rendering: nothing reflows, and a
page-and-line citation taken against the draft still finds the same
words on the same line of the same page. Removing `notreal:` removes
the banner and the scaling together, so the filed document is the
unmodified original.

The costs are real and worth stating. Draft pages are ~3% smaller than
final ones, so a draft and its filed version are not pixel-identical —
acceptable, since the whole purpose is that they not be mistaken for
each other. Mandatory JC forms are visually altered in draft output;
that is the decision this ADR records, and it is bounded by the fact
that a stamped form is by definition not the one being filed. Exhibit
copies inside a draft packet carry the banner too, which is true of
that copy and not of the underlying document.

One trap found on the way: rebuilding the PDF with a fresh writer
drops the document-level `/AcroForm`, which blanks every field on a
filled consumer notice. Cloning the reader preserves it. A stamp that
silently gutted the document it was labelling would have been a
considerably worse bug than the one being fixed.
Alternatives: overlay in the existing top margin (rejected — collides
with the JC form header, verified by rasterizing); a white knockout
box behind the banner (rejected — it erases form content to make room
for a label about the form); a rotated banner in the left margin
(rejected — unmistakable but strange, and it still competes with the
line-number column); stamping only generated pages (rejected — that is
the status quo this replaces).
