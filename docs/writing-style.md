# Legal writing & typography conventions

These rules govern every `.md` file under a matter's `src/` directory
(the pleading sources processed by `md_pleading.py`). They are enforced
expectations for AI agents editing pleading sources, not suggestions.
The PDF generator's typographic substitution layer enforces them
mechanically, which means violations usually produce subtly wrong
output in the rendered PDF rather than an error you can catch at build
time. Verify as you write.

## Em dashes: no spaces, ever

**Write `text---text` with no spaces on either side. Always.**

The generator converts `---` to an em dash character (—) but preserves
surrounding whitespace literally. `text --- text` renders as
`text — text`, with gaps on both sides — typographically wrong, and a
violation of American legal-writing style. There are no exceptions to
this rule.

```
# WRONG — will print with gaps in the PDF
the claim --- baseless as it is --- was filed
records --- including notes --- were withheld
theory --- not § 12345

# RIGHT
the claim---baseless as it is---was filed
records---including notes---were withheld
theory---not § 12345
```

Before finalizing any edit to a source file, verify zero matches:

```bash
rg -n ' --- ' path/to/file.md
```

(or `grep -n ' --- ' src/*.md` across a whole source tree). Any match
is a bug to fix before building.

## En dashes: also no spaces

`--` renders as an en dash (–). Use it for ranges only, with no
spaces — same rule as em dashes:

```
January 23--March 3, 2026
```

## Other typographic substitutions

- `"..."` — straight ASCII double quotes in source render as smart
  quotes. Do not type curly quotes yourself.
- `'` — straight apostrophes render as right single quotes. Do not
  type curly apostrophes yourself.
- `§` — type the Unicode section sign directly (Option+6 on macOS).
  Do not write "Section" when you mean the symbol.

## The pilcrow (¶) is narrower than it looks

**The only situation where using the pilcrow is conventional in
California legal pleadings is inside parenthetical citations at the end
of a sentence, to reference specific paragraphs in a supporting
document.** Type it directly (Option+7 on macOS) when that situation
arises.

```
# RIGHT — a parenthetical cite to another document's paragraphs
# (note `--` for the range, per the en-dash rule above)
The exchange schedule was fixed by stipulation. (Roe Decl., ¶¶ 4--6.)

# WRONG — running text is not a parenthetical citation
As set out in ¶ 4 of the stipulated order, ...
# write: As set out in paragraph 4 of the stipulated order, ...

# WRONG — "paragraph ¶" says paragraph twice
... and paragraph ¶ 4 of the stipulated order.
```

In body prose, write the word: "paragraph 4," "paragraphs 4 through 6."
Never pair the word and the symbol. This is the opposite of the rule for
`§`, which is conventional wherever a statute is cited, running text
included.

## Emphasis

- `*italic*` for case names, Latin phrases, and other conventionally
  italicized text: `*Doe v. Roe* (2024) 100 Cal.App.5th 123`,
  `*see* also`, `*inter alia*`.
- `**bold**` for emphasis — sparingly. In legal writing, bold in body
  prose reads as shouting; let sentence structure carry the weight.
- `***bold italic***` only when both are genuinely needed.

## Citation format

California style. **Italicize the case name only** — not the reporter,
the year, or the pin cite:

```md
*Doe v. Roe* (2024) 100 Cal.App.5th 123, 130.
```

**Statutes are not italicized at all:**

```md
45 C.F.R. § 164.524(d)
Health & Safety Code § 123110
Code of Civil Procedure § 2030.300, subdivision (c)
```

## Block quotes

Use `>` for extracted statutory language, or any quoted passage long
enough to stand on its own. Consecutive `>` lines merge into a single
block and are rewrapped, so source line breaks do not survive into the
PDF — break the source wherever is convenient. The block renders
indented 36 pt from the left margin, on consecutive grid lines, with no
bullet, no `>` glyph, and **no quotation marks added**. Do not type your
own quotation marks around it.

```md
Education Code § 49069.7(a) provides:

> Parents of currently enrolled or former pupils have an absolute right
> to access to any and all pupil records related to their children that
> are maintained by school districts or private schools.
```

For a short quotation that belongs inside a sentence, just use double
quotes inline — a block quote for a six-word phrase reads as padding:

```md
She stated that she was "not hired as court-appointed."
```

Never use a bullet list (`- `) to fake a block quote. Bullets are for
lists of items; they render with bullet characters and a different
indent, and the result does not read as quoted material.

## Line length

No hard limit in the source — the generator handles word wrapping.
Write naturally and do not hand-break lines mid-paragraph; a manual
break inside a paragraph is invisible in the source but changes nothing
in the output, so it only misleads the next editor about where the
rendered lines fall.

## Exhibit and attachment references: symbolic macros only

Use `\exhibit{shortname}` or `\attachment{shortname}`. Never hardcode
exhibit letters ("Exhibit A", "Attachment B", etc.) in body text: the
letter changes whenever the exhibit order changes; the symbolic macro
does not.

In letters (`doctype: letter`), `\attachment{}` is preferred; in
pleadings (`doctype: pleading`, the default), `\exhibit{}` is
preferred. Both macros are accepted in either context and resolve to
the doctype-appropriate label at render time.

**The macro's expansion already includes the label word ("Exhibit A" /
"Attachment A") — never precede it with a literal "Exhibit" or
"Exhibits."** This is a recurring bug: writing `Exhibit \exhibit{note}`
or `Exhibits \exhibit{a} through \exhibit{b}` renders as
`Exhibit Exhibit A` or `Exhibits Exhibit A through Exhibit B`. Write
the macro alone; if the sentence needs a plural, put it on the
surrounding verb, not on a literal word before the macro.

```
# WRONG — renders "Exhibit Exhibit J through Exhibit U"
Sealing Exhibits \exhibit{note_first} through \exhibit{note_last} ...

# RIGHT — renders "Sealing Exhibit J through Exhibit U"
Sealing \exhibit{note_first} through \exhibit{note_last} ...

# WRONG — renders "attached as Exhibit Exhibit F"
A true and correct copy is attached as Exhibit \exhibit{vendor_invoice}.

# RIGHT
A true and correct copy is attached as \exhibit{vendor_invoice}.
```

Before finalizing any source file that references exhibits, check the
rendered output for doubled labels:

```bash
pdftotext -layout out/<envelope>/<file>.pdf - \
  | grep -n "Exhibit Exhibit\|Attachment Attachment"
```

Zero matches is the required result.

## Headings: never hand-number them

**Every `#` heading is auto-numbered in legal-outline style (I., II.,
III., ...) at render time, with no exceptions and no opt-out.** Typing
a Roman numeral into the heading text yourself does not disable this —
it runs *in addition to* the automatic numbering, so the numbering
doubles up. This is a recurring bug that has shipped in real filings.

```
# WRONG — source has a manual numeral
# I. The Court Has Never Entered the Stipulation

# renders as:
II. I. The Court Has Never Entered the Stipulation
    ^^  ^^ — the generator's own "II." stacks on top of your "I."

# RIGHT — let the generator number it
# The Court Has Never Entered the Stipulation

# renders as:
I. The Court Has Never Entered the Stipulation
```

The mislabeling compounds silently: every `#` heading in the file
counts toward the outline, including a leading "Introduction" or
trailing "Conclusion," so a hand-numbered "I." on the *second* heading
renders as "II. I." — the generator assigned it position II, and your
own "I." is still sitting there as plain text. There is no per-file
setting to turn auto-numbering off. The fix is always to delete the
hand-typed numeral, never to adjust it to "match."

**Lead-in and closing prose:** memoranda in this convention do not put
"Introduction" or "Conclusion" under a heading at all. That prose sits
unheaded — directly under the YAML front matter, or at the end of the
file — so it never consumes an outline position. Only the substantive
point headings (the ones that should read "I.", "II.", "III.", ...)
get a `#`.

Before finalizing any source file with more than one heading, check
the rendered output for stacked numerals:

```bash
pdftotext -layout out/<envelope>/<file>.pdf - \
  | grep -nE "^\s*[IVXLC]+\.\s+[IVXLC]+\."
```

Zero matches is the required result. Any match means a heading carries
both the generator's numeral and a leftover hand-typed one.

## Em dash use: be sparing

Em dashes are for genuine parenthetical interruptions. Before using
one, ask whether a colon, semicolon, parentheses, or a new sentence
would be clearer. A paragraph with multiple em dashes reads as
breathless.

## Pre-finalize checklist

Run before building or handing off any pleading source:

```bash
# 1. No spaced em dashes in the source
rg -n ' --- ' src/*.md

# 2. No doubled exhibit/attachment labels in the rendered PDF
pdftotext -layout out/<envelope>/<file>.pdf - \
  | grep -n "Exhibit Exhibit\|Attachment Attachment"

# 3. No stacked heading numerals in the rendered PDF
pdftotext -layout out/<envelope>/<file>.pdf - \
  | grep -nE "^\s*[IVXLC]+\.\s+[IVXLC]+\."
```

All three must return zero matches.
