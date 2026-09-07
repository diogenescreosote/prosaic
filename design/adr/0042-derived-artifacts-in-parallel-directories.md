# ADR-0042: Derived artifacts live in parallel directories, not beside originals

**Status:** Accepted (September 6, 2026)

## Context

Every derived artifact the system produced for a document was placed
beside it: `<stem>_ocr.pdf`, `<stem>.txt`, `<stem>.srt`, `<stem>.ocr.txt`.
ADR-0041's coverage pass made the cost visible at scale. On the largest
live matter it wrote 1,067 files into evidence directories in one run,
and 58 OCR'd copies of court-filed documents landed in `pleadings/`,
which the workspace contract reserves for the court's copy and nothing
else --- precisely because a derived PDF is indistinguishable from a
filed one in a listing. Sidecars also complicate every directory
operation: an INDEX row per "non-sidecar file", `.gitignore` patterns
that must name each sidecar kind, triage prompts that must explain what
to skip, and a doubled file count in every folder a human browses.

`out/` (build products) and `.state/` (connector state) already follow
the other pattern: a parallel tree, one place, regenerable.

## Decision

1. **Derived artifacts live under `derived/<kind>/`, mirroring the
   matter's own layout.** For a document at `assets/gmail/x.pdf`:
   `derived/text/assets/gmail/x.pdf.txt` holds the page-marked text;
   `derived/ocr/assets/gmail/x.pdf` holds the OCR'd copy. The full
   filename is kept and a suffix appended, so `x.pdf` and `x.png` never
   collide. Future kinds follow the same rule: `derived/extract/` for
   structured per-document extraction, `derived/handwriting/` for
   review crops.
2. **Source directories hold received material and human-authored
   files only.** `assets/`, `pleadings/`, `discovery/`,
   `processed_files/` and the rest contain originals, INDEX and
   MANIFEST files, and human notes. Nothing a tool regenerates goes
   there.
3. **Tracked or ignored by kind.** `derived/text/` is tracked: small,
   and it is what the record is searched through. `derived/ocr/` is
   ignored: large and regenerable by `sc text ensure`. The matter
   template's `.gitignore` says so; `sc text migrate` adds the line to
   an existing matter.
4. **Legacy siblings are recognized, read, and never silently
   abandoned.** The audit finds a `_ocr.pdf` or `.txt` beside an
   original, uses it, and notes the legacy location. `sc text migrate`
   moves what the tool wrote (its header marks them, and its `ocr:`
   line says whether it made the OCR copy) into `derived/`, with `git
   mv` for tracked files. A `.txt` beside an original with no header is
   a human transcription: searched, reported as unverified, left in
   place.
5. **Human transcriptions may also go under `derived/text/`.** The
   default for new work is the parallel tree regardless of author; the
   header, or its absence, says who wrote it.
6. **`sc find` cites the original.** A hit inside `derived/text/...`
   is reported as the original document's path and page, with the text
   file named second, so a hit reads as a cite rather than as a path
   into a cache.

## Consequences

- `pleadings/` is again the court's copy and nothing else; the 58
  derived copies move out under migration.
- Evidence directories stop doubling in size; a browser of `assets/`
  sees documents, not documents and their shadows.
- One `.gitignore` line covers every OCR copy; one directory holds
  every text file; the coverage audit has one place to look before
  falling back to legacy locations.
- The INDEX, layout docs, triage prompt and workspace contract lose the
  sidecar vocabulary. INDEX rows describe documents; the derived tree
  needs no rows.
- Matters created before this ADR carry legacy siblings until
  migrated; `sc text audit` names them and migration is one command.
  Agent-made `_ocr.pdf` siblings that predate the tool move only with
  `--include-legacy-ocr`, because INDEX rows may name them.
- Deletion of an original leaves an orphan under `derived/`; `sc clean`
  should learn to report derived files whose original is gone (not
  done here).
