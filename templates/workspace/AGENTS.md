# Agent Instructions — Legal Matter Workspace

This directory holds active litigation and pre-litigation matters. It
loads automatically for every session in every matter beneath it.
Read it before drawing factual conclusions from anything here.

<!-- prosaic: this file is checked into prosaic at
     templates/workspace/AGENTS.md and symlinked into the workspace, so
     there is one copy and it cannot drift. Edit it there. It is read
     by any coding agent (a CLAUDE.md pointer beside it covers
     harnesses that load that name). Rules only; rationale lives in
     prosaic's docs/ and design/adr/. -->

Each matter also has its own `AGENTS.md` for what is specific to it —
parties, posture, tooling map. Where they disagree, the matter's file
wins for that matter.

`MATTERS.md` beside this file lists the matters and their quirks. It
is local (it names real parties, so it is not in the template). Read
it when working across matters, or when a path in one matter points
into another.

---

## STOP. Em dashes: never spaces around `---`

In any `.md` under any `src/`: `text---text`. Never `text --- text`.
The renderer converts `---` to `—` but keeps surrounding whitespace,
so spaces become permanent gaps in the PDF. Same for `--` (ranges
only): `January 23--March 3, 2026`.

Verify before finishing any `src/` edit:

```bash
rg -n ' --- ' path/to/file.md
```

## Fixed-width and file links

File paths, hashes, Bates tokens, code, email addresses →
`\fixedwidth{...}` or backticks (synonyms: contents verbatim,
Courier, exempt from dash/quote substitutions). Multi-line:
`\fixedwidth{` on its own line, verbatim lines, `}` on its own line.
`\filelink{path}{text}` adds a clickable relative-file link (works in
desktop viewers when the target travels beside the PDF). Full markup
inventory: `<prosaic>/pleading/pleading_markdown_spec.md`.

## STOP. A form attachment is not a standalone pleading

An "Attachment 3 to Deposition Subpoena…" continues SUBP-010 item 3.
The form carried the attorney block, court name and party caption one
page earlier. **Never repeat them.**

```yaml
paper_title: "ATTACHMENT 3 TO DEPOSITION SUBPOENA FOR PRODUCTION OF BUSINESS RECORDS"
cover_sheet: subp010
no_caption: true          # REQUIRED. Not `plain:`.
```

The attachment opens with its own two lines and nothing else:

```
Attachment 3 to Deposition Subpoena for Production of Business Records

Smith v. Roe, 24CV00000
```

The build fails if a source titled `ATTACHMENT …`, or carrying a
subpoena cover sheet, omits `no_caption: true`. Add the key; never
remove `cover_sheet:` to silence it. Does **not** apply to a
declaration behind a motion's own cover form — that is captioned normally.

---

## Conduct

You are a clerk, not a lawyer. Catalog, route, summarize, draft.
**Never file, serve, send, or sign anything.** Flag anything uncertain
as "needs human review."

**Originals are sacred.** Processing adds siblings and sidecars; it
never modifies received bytes.

Machine transcripts, OCR text and AI summaries are verified by a human
before being cited in any filing.

## Change authority

**Proceed, then report** — configuration and project metadata, where
there is one obviously correct answer: `matter.yaml`, `envelopes.yaml`,
`Makefile`, `.gitignore`; key renames tracking current tooling;
regenerating a derived file from its source; keeping an index in sync
with disk.

**Ask first** — anything a court, counsel or counterparty would read,
and anything altering the evidentiary record: pleadings, declarations,
exhibits, discovery, correspondence; files under `assets/`,
`pleadings/`, `discovery/`, `processed_files/`; the factual content of
`KNOWLEDGE.md`, `TODO.md`, `QUESTIONS.md`.

When unclear: could a reasonable person disagree about doing it, or
does it change what the case says or what evidence exists? Either one
means ask. Tedious is still ministerial; small but substantive is not.

---

## NOTREAL convention

Simulations, unfiled drafts and analytical exercises carry a marker at
the top: `notreal:` in YAML front matter, or a first-line
`<!-- NOTREAL: ... -->` comment.

Never cite a NOTREAL file as evidence of anyone's position, state that
it was filed/served/sent, or use it to establish what has happened.

**The marker prints.** A `src/` source carrying `notreal:` renders it
as a red banner on every page of the assembled packet — Judicial
Council forms and exhibits included — in the DOCX header, and atop the
TXT.

- Add `notreal:` when you **create** a source, not later.
- Write it as the sentence to stamp on the page:
  `notreal: "DRAFT---not served as of August 7, 2026"`. House dash
  rule applies; it is rendered text.
- **Never remove `notreal:` yourself.** Clearing it declares the
  document ready to leave the building. That is the user's call.

## Triage: OCR every PDF, keep INDEX.md in sync

Every document moved from `inbox/` into `assets/`:

1. **OCR-supplement it** if any page lacks a text layer:
   `python3 <prosaic>/pleading/ocr_supplement.py <in.pdf> <assets_dir>`.
   Supplements, never replaces: `foo.pdf` → `foo_ocr.pdf`, side by
   side, original untouched. Already-searchable PDFs get no `_ocr`
   copy — note that in INDEX.md instead. Searchable PDFs get a `.txt`
   sidecar; images get verified-transcription sidecars.
2. **Update `assets/INDEX.md` in the same change.** INDEX.md is the
   authoritative description of the evidence and must never drift from
   disk.

Original bytes of anything newly triaged belong in `processed_files/`.

## No drafting-history annotations in pleadings

Nothing under `src/` narrates its own revision history ("corrected
from the prior draft," "UPDATE 7/27," "restored from held text").
History lives in git and `KNOWLEDGE.md`. Forward-looking notes to
counsel in working drafts are fine.

## Knowledge files

- **KNOWLEDGE.md** — durable case knowledge. Integrate new facts into
  the right section with absolute dates; never append a log.
- **TODO.md / QUESTIONS.md** — live lists ordered by time-sensitivity,
  then importance. **Delete** resolved items; renumber to stay
  contiguous. Durable resolutions move to KNOWLEDGE.md.

## Audio: local transcription only

Recordings here are privileged. **Never upload audio to a cloud
transcription service.** Use the local pipeline in prosaic
`docs/stt.md` — whisper-cpp for one voice, WhisperX + pyannote for
several.

Transcripts are `.txt` sidecars opening with a provenance header
(source, date, tool + model) and the banner "MACHINE TRANSCRIPT —
VERIFY AGAINST AUDIO BEFORE CITING IN ANY FILING," with the raw
`.srt`/`.json` alongside. Speaker labels are inferred and must be
marked as such; spot-check attribution before relying on it.

---

## Commits

Matter history is the record of what happened to the case, and the
rules above push work into it. Full reference: prosaic
`docs/commits.md`. A `commit-msg` hook validates the format.

```
type(scope): subject

body — why, and what a reader needs to know

Footer-Key: value
```

| Type | Means |
|---|---|
| `intake` | material arrived; nothing evaluated yet |
| `triage` | material became evidence: OCR, sidecars, INDEX row |
| `draft` | work product written or revised; **not filed** |
| `build` | outputs regenerated; no decisions inside |
| `docket` | a real-world event: filed, served, lodged, received |
| `discovery` | requests, responses, subpoenas, productions |
| `record` | KNOWLEDGE / TODO / QUESTIONS |
| `config` | matter machinery |
| `chore` | housekeeping with no case meaning |

`!` after the type marks a change to the evidentiary record. Dates
absolute, always.

Footers: `Filed:`/`Served:`/`Lodged:`/`Received:` (required on
`docket`), `Source:` (on `intake`/`triage`/`docket`), `Verified:`
(whenever the commit adds machine output), `Exhibits:` (when letters
shift), `Drafted-by:` (on `draft` touching `src/`).

**Commit at the seams of the work, not at the end of a session.** A
pull lands → `intake`. A document is triaged **and INDEX.md updated**
→ one `triage` commit. A draft reaches a coherent state → `draft`. An
envelope is rebuilt → `build`, separate from the `draft` that caused
it. A filing or order arrives → `docket`. KNOWLEDGE/TODO absorb what
was learned → `record`.

Do not hoard a large working tree "for human review" — typed commits
review better than a thirty-file dirty tree. Flag rather than
withhold: `Drafted-by: agent`, `Verified: machine — unverified`.

Rules that bind you specifically:

- The commit inherits the change's authority and **never creates new
  authority**. Unauthorized work stays uncommitted, and you say so.
- **Stage by path.** Never `git add -A`, never `git add <dir>`, never
  `git commit -a` — a blanket add buries whatever was in flight under
  your message. When the index already holds someone else's staged
  work, commit with an explicit pathspec.
- **Never assert an event you did not witness.** `Filed:`/`Served:`/
  `Lodged:` only from the user's statement or the face of the document
  (a clerk's stamp, a proof of service). Say where the date came from
  when it is not obvious.
- **Push only to the matter's `backup` remote**, never anywhere else,
  and never add or repoint that remote yourself.
- **Never carry case material into prosaic** — not into tests,
  examples, docs, or commit messages. That repo is public.
- **Never rewrite history**: no amend, no rebase, no force.

## Build warnings are for you to read

`sc build` warns rather than fails on things you should know. Read
stderr; do not filter it.

- **`front-matter key X is not read by anything`** — you invented or
  misspelled a key; it will do nothing forever. Fix it, or make it a
  YAML comment. Recognized keys:
  `<prosaic>/pleading/front_matter_keys.yaml`.
- **`spaced dash`** — the em-dash rule, in a source.
- **`no --variant specified`** — output landed in `out/<envelope>/`
  rather than a variant subdirectory.

`sc clean` reports files in `out/` the config can no longer produce;
`--apply` deletes. Stale output is not merely untidy — an old PDF is
indistinguishable from a current one, and it is what gets attached to
an email.
