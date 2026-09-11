# 0047 — Case names are italicized, or the build fails

**Status:** accepted (2026-09)

## Context
California style, like every American citation style, sets the name
of a cited case in italics (underline on a typewriter) and nothing
else about the cite: `*Doe v. Roe* (2024) 100 Cal.App.5th 123`. A
roman "Doe v. Roe" in a brief or a letter to counsel is a drafting
error that every legal reader notices and reads as carelessness.

The rule was documented (docs/writing-style.md, the markdown spec) and
it kept coming back: a long memorandum of points and authorities went
to a human for review on September 11, 2026 with every one of its six
case names roman. The pattern is the one ADR-0018 describes for
captioned attachments. A style rule whose only enforcement is that
somebody will notice is enforced on the drafts somebody happens to
read closely, and not on the rest.

## Decision
A case name in running text that is not inside an italic or
underlined span **fails the build** in every renderer (PDF, DOCX,
TXT), with an error that lists every offending line and states the
fix. A warning would be read past on a long build; a hard error is
read because it is the only thing on the screen.

What is a case name is what a citation style recognizes as one in
running text: ` v. ` between two words, `In re`, `ex rel.`, and the
California family-law and probate title forms `Marriage of`, `Estate
of`, `Guardianship of`, `Conservatorship of`, `Adoption of`, each
followed by a capitalized word. `vs.` is not a signal: it is ordinary
prose far more often than a case name and no style writes a case that
way. Italic is whatever the renderer's inline parser flags italic, so
`*...*`, `***...***` and `<u>...</u>` all satisfy the rule and a name
whose parties were italicized separately (`*Doe* v. *Roe*`) does not,
because its connective is roman.

Exempt, because they are not running text: front matter and its YAML
comments; HTML comments; verbatim spans and blocks (`\fixedwidth`,
backticks, `\filelink`); and a line that is nothing but a case title
with an optional case number, which is how a Judicial Council form
attachment opens (`Smith v. Roe, 24CV00000`) and how a caption
fragment reads. A title line is capitalized words with a title's
connectives; a sentence that happens to start with a case name has
lowercase running text after it and is checked.

## Consequences
- A matter source with a roman case name stops building until the
  name is italicized. This is the intended cost; the fix is one pair
  of asterisks per name and the error says where.
- Quoted matter is not exempt. A case name inside a quotation is
  still italicized in the quoting document, which is the convention.
- The detector is a regular expression over parsed spans, not a
  citator. It will not recognize a case cited by a short form that
  carries no signal (`*Pettus*, supra`), and it does not check that
  reporters and years are roman. Both are left to the author.
- No escape hatch beyond `\fixedwidth{...}`. A real need for a roman
  case name in running text has not appeared; if one does, add a
  documented marker rather than weakening the rule.
