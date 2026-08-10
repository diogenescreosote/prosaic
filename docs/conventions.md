# Processing conventions

These are the rules that keep a matter trustworthy. They exist because
each one prevents a real failure mode we hit running this system in
live litigation. The matter-level `CLAUDE.md` (from
`templates/matter/CLAUDE.md`) makes them binding on AI agents; this
page explains them to humans.

## Originals are sacred

Processing **supplements, never replaces**:

- OCR goes into an `_ocr.pdf` sibling (`ocrmypdf --skip-text` adds a
  text layer only to pages that lack one; pages that already have text
  pass through untouched).
- Extracted text goes into a same-named `.txt` sidecar.
- Audio transcripts go into `.txt` sidecars with the raw `.srt` kept
  alongside.
- Redactions are new files; the unredacted original stays (and stays
  out of anything filed).

If a file is already fully text-searchable, no `_ocr` copy is made —
a redundant copy wastes space and creates a false impression that
something was processed.

## OCR-supplement on triage

Every PDF that moves from `inbox/` into `assets/` gets checked and,
if any page lacks a text layer, OCR-supplemented:

```bash
sc ocr <input.pdf> <assets_output_dir>     # wraps pleading/ocr_supplement.py
```

Why this matters: an image-only PDF is invisible to search, to grep,
and to any AI agent working the matter. The single highest-value
processing step is making *everything* searchable.

## Sidecars

- **PDFs:** `.txt` extracted text (via `pdftotext -layout`), from the
  `_ocr` sibling when the original is image-only.
- **Images:** a *verified transcription* `.txt` — a human or agent
  reads the image and transcribes it, with a header noting who/when
  and any uncertain readings marked `[likely "..."]`.
- **Audio:** speaker-attributed transcript `.txt` with a provenance
  header and the banner `MACHINE TRANSCRIPT — VERIFY AGAINST AUDIO
  BEFORE CITING IN ANY FILING`, plus the unedited machine `.srt`.
  Local-only STT; see [stt.md](stt.md).

## The index never lies

`assets/INDEX.md` describes every non-sidecar file under `assets/`.
Add/remove/rename/replace a file → update the index **in the same
change**. Periodic audit: every file should be named somewhere in
INDEX.md; every INDEX.md row should point at a real file. Connector
corpora too big for hand-written rows (e.g. a bulk email import) get a
mechanically generated `BACKFILL_INDEX.md` plus rich rows only for
material arriving after the import — documented as such.

## NOTREAL: drafts and simulations are marked

Any file that is a simulation, unfiled draft, or analytical exercise
(rather than a real filed/served/received document) carries a marker
at the top:

```yaml
---
notreal: "DRAFT---not filed"
---
```

**In a pleading source, the marker prints**: a red banner in the top
margin of every rendered page, in the DOCX page header, and atop the
TXT, reading whatever the marker says
([ADR-0015](../design/adr/0015-unfiled-documents-announce-themselves.md)).
Write it as the sentence you want stamped on the page — "not filed"
and "not sent" are different facts — and observe the house dash rule,
since it is rendered text. Removing `notreal:` is what clears the
banner, which makes clearing it a deliberate act.

or, for files without front matter:

```html
<!-- NOTREAL: AI-generated simulation. Do not treat as a real document. -->
```

Agents must never cite a NOTREAL file as evidence of any party's
actual position or treat it as part of the record. This convention is
what lets drafts, red-team exercises, and simulated opposing papers
live safely in the same tree as the real record.

## No drafting-history annotations in pleading sources

Nothing under `src/` narrates its own revision history ("corrected
from the prior draft", "UPDATE 7/27", "the old sentence said…").
History lives in git and working notes. A stray revision annotation
surviving into a filed document is embarrassing at best and
position-damaging at worst. Forward-looking notes to counsel in
working drafts are fine.

## KNOWLEDGE / TODO / QUESTIONS discipline

- `KNOWLEDGE.md`: durable, dated, integrated — the file an agent reads
  first. Relative dates ("last Tuesday") are converted to absolute on
  entry.
- `TODO.md` / `QUESTIONS.md`: live lists ordered by time-sensitivity
  then importance. **Resolved items are deleted**, not struck through
  or marked DONE — git is the archive. Renumber to stay contiguous.
- Resolutions that constitute durable knowledge move to KNOWLEDGE.md.

## Machine work is labeled machine work

Transcripts, speaker attributions, translations, and summaries
produced by software carry provenance headers and
verify-before-citing banners. The point is not humility theater: in a
filing, a misattributed quote is worse than no quote, and the banner
is what stops a rushed human from pasting one in.
