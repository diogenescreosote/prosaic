---
name: drafting-conventions
description: Pagination and signature-block discipline for drafted instruments - what the renderer enforces, what the drafter must judge, and where local court rules turn preferences into requirements. Use when drafting or reviewing any document with signature areas, execution clauses, notarial certificates, or proposed orders, or when a build's pagination looks wrong around a signing area.
---

# Drafting conventions: signatures and pagination

Two kinds of rule live here. **Enforced** means the renderer does it;
never fight it, and report it if it fails. **Judgment** means you
apply it when composing sources.

## Inline markup (enforced — and one standing trap)

The pleading dialect is not full Markdown. Inline constructs:
`***bold italic***`, `**bold**`, `*italic*`, `<u>underline</u>`,
`\highlight{...}`, `\fixedwidth{...}`, `[^footnote]`. Full inventory:
`pleading/pleading_markdown_spec.md` ("Inline body markup").

**Fixed-width text is `\fixedwidth{...}` or backticks (synonyms).**
Both render contents verbatim in Courier, exempt from the
em-dash/en-dash/smart-quote substitutions — the construct for file
paths, hashes, Bates tokens, code, and email addresses. A block form
(`\fixedwidth{` on its own line, verbatim lines, `}` on its own
line) handles multi-line material. `\filelink{path}{text}` renders
the display text the same way, underlined, with a relative-file link
annotation; relative links resolve only in desktop viewers with the
target beside the PDF, so say that in the document when it matters.

## Atomicity classes (enforced by the renderer)

| Object | Rule |
|---|---|
| Any signature block (`\signblock{...}`, all styles) | never split internally |
| `whereof` execution clause + signature | ONE block; the clause recites the date, so nothing near it may print another date |
| Witness signature grid | atomic per witness |
| Notarial certificates (acknowledgment, jurat, proof of execution) | absolutely indivisible; whole certificate moves to the next page |
| Heading before a signature block | kept with the block (keep-groups) |
| Any heading | never stranded: moves unless ≥2 lines of its content fit beneath it |

When a unit doesn't fit, it MOVES WHOLE to the next page — never
pull orphan lines forward to justify a heading.

## Judgment rules (yours when composing)

- **One signature per signer per document.** A clause that recites
  the execution date owns its signature (`whereof`); never pair a
  prose execution clause with a separate dated block — that prints
  the date twice.
- **Perjury certifications travel with their signatures** (`decl`
  does this): the sentence "I declare under penalty of perjury..."
  separated from its signature line invites the question of what was
  above the signature at execution.
- **Don't end a filing with a signature-only page.** Prefer the last
  2+ lines of substantive text on the signature page. (Genre
  exception: contracts and long instruments legitimately use
  dedicated, labeled signature pages; a four-page declaration does
  not.)
- **Proposed orders are the hard case**: some courts REQUIRE order
  text on the judge's signature page (e.g., Orange County: ≥2 lines;
  San Francisco: no signature-only last page). Before submitting a
  proposed order, check the local rules and compose so the
  `\signblock{judge}` block shares its page with operative text.
  Never give a judge a bare signature page. Do NOT generalize this
  to party/attorney signatures — it is a judicial-signature rule.
- **Proofs of service are independent instruments**: starting one on
  a fresh page is intentional structure, not an orphan.
- **A notarial certificate on its own sheet is lawful and normal**
  (Civ. Code § 1188 contemplates attachment) — but a detached sheet
  should be hard to mis-mate: identify the document, date, and
  signer near (never inside) the statutory wording.

## Say what the instrument does; never banner what it doesn't

Good legal writing goes directly to the point. Just as good code does
not rely on comments, good legal writing does not depend on
qualifications: if a request needs a disclaimer to be read correctly,
rewrite the request.

**Never open an instrument with a paragraph disclaiming what is NOT
sought, NOT asserted, or NOT intended.** A disclaimer banner defines
the document by its negative space, and the other side gets to
interpret the negative. The canonical failure: a records subpoena
headed "NO CLINICAL CONTENT IS SOUGHT" whose first request was audit
trails *of clinical charts* — arguably all of it was clinical content,
and the custodian's objection was drafted for them, in the demand's own
words, covering everything.

When a carve-out is legally necessary — a third party's privilege, a
statutory exclusion — it is **one operative sentence**, phrased as a
command or a scope line, placed where it operates:

```
# WRONG — a thematic banner above the requests
NO CLINICAL CONTENT IS SOUGHT. No request below seeks the content
of any psychotherapy note, progress note, or other record of the
substance of any therapy session. If a responsive record...

# RIGHT — a command inside the instructions
If a responsive record contains the substance of a therapy session
in which [third party] participated, redact that substance and
produce the remainder, including all dates, headers, senders,
recipients, and system information.

# RIGHT — a scope line
Records of sessions in which [third party] participated are outside
the scope of this subpoena.
```

The same instinct governs letters and declarations: cut "to be clear,
I am not..." framings unless the negative statement is itself the
point (a non-reconsideration sentence heading off a CCP § 1008
objection is the point; a reflexive hedge is not). Each disclaimer
kept must earn its place by doing legal work a well-drafted
affirmative sentence cannot.

## Release discipline (enforced)

Every build is DRAFT-bannered by default; `--final`
is the explicit act of releasing, per invocation,
never persisted in a source. `sc docuseal send` refuses draft-stamped
PDFs without `--allow-draft`. `notreal:` remains for hypotheticals
and simulations whose banner should say what they are. Never build
`--final` on your own initiative — releasing is the human's act.

## Filename carries status, once a document leaves `out/`

A build in `out/` is unsigned by definition --- it is what the source
renders to, and it is regenerated on every build. The moment a human
signs one, the signed artifact is a different thing from its build and
must never be confusable with it.

**Signed but not yet filed: suffix `_SIGNED_UNFILED`.**

```
out/<envelope>/notice_of_motion.pdf          the build. unsigned, regenerable
staging/.../notice_of_motion_SIGNED_UNFILED.pdf   signed. not yet filed
pleadings/2026-08-26_notice_of_motion.pdf    filed. the suffix is gone
```

**Filing drops the suffix.** A document in `pleadings/` is the court's
copy by definition, so `_SIGNED_UNFILED` on a file there is a
contradiction; the rename is part of docketing it, alongside its
MANIFEST row. Serving does not drop the suffix --- served-and-unfiled
is still unfiled.

The reason is the same one behind the DRAFT banner and `notreal:`: a
PDF carries no reliable sign of its own status, three versions of one
document look identical in a file listing, and the one that gets
attached to an email is whichever the human grabbed. The suffix makes
the wrong grab visible.

Corollary for `_AS_SERVED` and similar markers: they describe
provenance, not release state, and stack after the status suffix when
both apply.

## Source ranking, when conventions conflict

Statutes / Rules of Court / local rules (validity — enforceable)
> Judicial Council forms (California document grammar)
> Butterick, *Typography for Lawyers* (pagination mechanics)
> Garner, *The Redbook* (style) > Adams (contract execution
structure). Don't use style guides to answer validity questions or
statutes to answer typography questions.

This skill is deliberately small; jurisdiction profiles and heavier
paralegal automation bolt on here as they're built. Estate-specific
execution discipline: [estate-plan](../estate-plan/SKILL.md).
References: `pleading/pleading_markdown_spec.md` (signature blocks,
notarial certificates), ADR-0027.
