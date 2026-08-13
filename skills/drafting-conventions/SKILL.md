---
name: drafting-conventions
description: Pagination and signature-block discipline for drafted instruments - what the renderer enforces, what the drafter must judge, and where local court rules turn preferences into requirements. Use when drafting or reviewing any document with signature areas, execution clauses, notarial certificates, or proposed orders, or when a build's pagination looks wrong around a signing area.
---

# Drafting conventions: signatures and pagination

Two kinds of rule live here. **Enforced** means the renderer does it;
never fight it, and report it if it fails. **Judgment** means you
apply it when composing sources.

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
