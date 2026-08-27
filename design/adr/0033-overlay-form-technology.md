# ADR-0033: Overlay form technology — draw, flatten, never trust AcroForm

**Status:** Accepted (August 21, 2026)

## Context

The form engine (ADR-0006 lineage) fills Judicial Council forms by
setting AcroForm field values, with countermeasures accreted for each
way that fails: `/NeedAppearances` for stale appearance streams,
XFA-stripping for LiveCycle blanks, explicit `/DA` sizes for auto-size
fields, and most recently a fix for inherited `/V` — writing a checkbox
value on a shared parent node made untouched sibling *text* fields
render the checkbox's on-state ("1") in some viewers, a defect that
reached a real filing draft before being caught, and that no amount of
value-level inspection detects, because the values are correct; only
the viewer's resolution of inheritance is not.

The accumulated lesson: **how an AcroForm fill renders is a property
of the viewer, not of the file.** Every countermeasure narrows the
variance; none eliminates it.

Separately, form adapters are increasingly AI-authored, and the
recurring authoring failure is geometric — a value drawn in the wrong
box — which value-level tests cannot see.

## Decision

1. **`technology: overlay`.** A descriptor may opt a form out of
   AcroForm filling entirely. Every field is drawn as ordinary page
   content at a rectangle — taken from the widget its `map:` names
   (the widget serves only as geometry), or from a hand-authored
   `rect:` where no widget exists. Checkboxes draw a centered bold X.
   The output is **flattened**: all widget annotations and the
   AcroForm dictionary are removed. What is filed is plain ink;
   every viewer renders it identically.

2. **Sizing rules favor fit with consistency.** Under overlay, a field
   with no explicit `fit:` defaults to `shrink`; and fields sharing a
   `size_group:` all render at the smallest size any member needed, so
   related boxes keep one type size instead of ransom-note variance.

3. **E-sign areas are first-class descriptor data.** A field may carry
   `esign: {type: ..., party: ...}`. Types come from a fixed taxonomy —
   `signature, initials, date, name, email, phone, text, checkbox` —
   chosen as the least common multiple of DocuSeal, DocuSign, and
   Dropbox Sign native field types, so the descriptor's e-sign map can
   drive any of them (see `sc docuseal`). Parties are abstract role
   names (`petitioner`, `attorney_for_petitioner`, `server`, …)
   declared in descriptor-level `esign_parties:`, in signing order.

4. **A geometry preview is part of the authoring loop.**
   `sc form preview <id> -o out.pdf` renders the blank with a
   translucent labeled box over every rect the descriptor can ink —
   text fields blue, checkboxes purple, e-sign areas colored by party
   (position in `esign_parties` → fixed palette) and labeled by TYPE —
   with a legend. Authoring a new adapter includes opening this view
   and looking, before any fill is trusted.

MC-040 is the pilot; existing acroform/xfa descriptors are unchanged
and migrate opportunistically.

> **Superseded August 26, 2026 by
> [ADR-0037](0037-no-acroform-filling.md).** Overlay is no longer
> opt-in and migration is no longer opportunistic: AcroForm filling
> is prohibited, a non-overlay descriptor outside a named legacy
> list is a hard error, and that list may only shrink. The reasoning
> above stands; only the disposition changed.

## Consequences

- Overlay outputs carry no live form fields: nothing downstream can
  read values back out of the PDF (the `.fields.json` sidecar pattern
  does not apply), and a recipient cannot type into the form. Both are
  acceptable for filing copies, which are print-equivalent artifacts.
- Hand-authored `rect:` entries (signature lines have no widgets) are
  a new drift surface; the geometry preview is the check.
- The e-sign taxonomy constrains descriptors to what common platforms
  can all express; platform-specific exotica (payment fields, stamps)
  are deliberately unavailable.
- `test_descriptor_matches_blank` retains its revision-drift alarm
  under overlay, since `map:` still names widgets in the blank.
