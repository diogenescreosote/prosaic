# 0018 — A form attachment is not a pleading, and the build enforces it

**Status:** accepted (2026-08)

## Context
An "Attachment 3 to Deposition Subpoena for Production of Business
Records" continues SUBP-010 item 3, which literally reads "described
in Attachment 3." The form carried the attorney block, the court name
and the two-column party caption one page earlier. The attachment
reprinting them presents it as a separate paper that was separately
filed; it was not, and has no independent existence.

The generator was producing captioned attachments. This was pointed
out on many occasions, corrected by hand, and reintroduced on the next
rebuild.

The assumed cause — an agent not following documentation — was wrong,
and the real one is the whole reason this ADR exists. The sources said
`plain: true`. **Nothing in the renderer ever read that key.** The
working key was `no_caption:`, which appeared nowhere in the spec. So
the instruction was in the file, the file looked correct to anyone who
opened it, and every build reprinted the caption. prosaic's own
scenario fixture — the shipped example of a subpoena attachment — had
the same defect, which is how the pattern spread by copying. And the
DOCX renderer ignored `no_caption:` outright, so a source could
produce a correct PDF and a captioned DOCX from the same front matter.

## Decision
A source is a **form attachment** if its `paper_title` begins
`ATTACHMENT`, or if it declares a subpoena cover sheet (`subp010`,
`subp025`), whose accompanying prose is always a continuation of a
numbered form item. A form attachment that does not suppress the
caption **fails the build**, with an error naming the key to add.

`no_caption:` is documented in the spec for the first time. `plain:`
is honored as a deprecated spelling and warns, so the six sources
across two matters that already said it become correct without a
migration anyone has to remember. The DOCX renderer honors it too.

The rule is deliberately narrow: a declaration attached to a CIV-110
is **not** caught. That is a distinct document the request
incorporates, and California practice captions it normally.
Over-broad enforcement here would be its own bug.

## Consequences
The error arrives at build time, in the terminal, naming the fix —
rather than in a rendered PDF that someone has to notice. It caught
prosaic's own fixture the first time it ran, which is a fair
measure of how far the pattern had spread.

The deeper lesson is about silence, not about captions. A front-matter
key that nothing reads is indistinguishable, to every reader of the
source, from one that works — and it will be copied into new files as
a demonstrated-correct example. The generator has no schema for front
matter and warns on nothing unknown, so any misspelled or invented key
fails exactly this way. Fixing that generally is real work: the keys
are spread across four renderers and the form descriptors, and a
half-complete allowlist would produce false warnings on legitimate
matter-specific keys. It is left open, and it is the more valuable
follow-up.

Costs: two spellings for one key until `plain:` is removed, and a hard
failure where a warning would be gentler — accepted, because a warning
is what the previous arrangement effectively was, and it did not work.
Alternatives: document it harder (rejected — it was documented, and
the documentation was not the broken part); make `plain:` an error
(rejected — it breaks sources in matters not visible from here, for no
benefit over honoring it); infer "attachment" from the cover sheet
alone (rejected — it wrongly catches the CIV-110 declaration, which
this very check flagged on its first run).
