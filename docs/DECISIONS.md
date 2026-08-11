# Decisions

Each entry: the decision, the alternatives, why, and what it costs.

Most of what this file used to hold described a typed case model, a
deadline engine, an IMAP ingestion layer and an LLM operator that were
removed in ADR-0019. Those entries went with them; only the two decisions
that outlived the code are kept, renumbered. The architectural decisions
that govern the system as it stands are the ADRs under
[../design/adr/](../design/adr/).

## 1. Fill official AcroForms; generate pleading paper from scratch

**Decision.** Where the Judicial Council publishes a fillable form, prosaic
fills the official blank, shipped unmodified in `pleading/forms/`. Pleading paper,
which has no official fillable artifact, is generated from scratch per
CRC 2.100–2.119.

**Alternatives.** Recreate the forms' appearance ourselves; or overlay text
on flattened scans.

**Why.** Clerks and opposing counsel receive the exact artifact they
expect, revision date and all, and a form revision is handled by swapping
the blank and re-verifying the mapping rather than re-typesetting. The
cost of the alternative is visible in this repo's own field-mapping notes:
the official files contain misspelled field names and stale tooltips —
recreating their layout pixel-perfectly would be strictly harder than
mapping them.

**Cost.** Dependence on the forms' internal field names, which are
unversioned implementation details; AES-encrypted blanks pull in a crypto
dependency; and the blanks add ~800KB to the repository.

## 2. The wordmark animates by default

**Decision.** The README shows the animated wordmark — a terminal cursor
blinking at 1.06s with a hard opacity step (SMIL `calcMode="discrete"`) —
with static variants committed alongside.

**Alternatives.** Static by default; or CSS animation.

**Why.** The blink is the identity: a prompt waiting for input, which is
what the tool is. SMIL is used because GitHub's markdown pipeline strips
embedded stylesheets but renders SMIL inside `<img>`. SMIL cannot honor
`prefers-reduced-motion`, which is a real accessibility trade: the honest
mitigations are keeping the mark small (~330px, one line of motion) and
shipping `wordmark-static*.svg` for any context that wants stillness. A
`<picture>` element can't switch on reduced-motion for the README, so the
default had to be chosen, and the animated mark was chosen knowingly.

**Cost.** Users with vestibular sensitivity see a blinking element on the
README. The glyphs are outlined paths, so the mark is also ~10KB instead
of a 300-byte `<text>` element (font fallback on systems without Courier
New would misplace the cursor otherwise).
