# ADR-0041: Searchability is audited and repaired, never assumed

**Status:** Accepted (September 6, 2026)

## Context

The record search added under ADR-0040 (`sc find`) greps text files.
A PDF is searchable only through a text sidecar, and the first version
counted a PDF as searched when an `_ocr.pdf` sibling existed --- which
ripgrep cannot read. Measured on the largest live matter: 1,039 PDFs,
97 with a `.txt` sidecar, 31 with an `_ocr` sibling and no sidecar,
911 with neither. A search over that record could see under a tenth of
it and still say "not found".

The triage conventions asked the agent to write sidecars and to OCR
scans. A convention an agent must remember is not a guarantee; the
sync log shows connector failures logged as `ok` for weeks for the
same reason (a pipe masking an exit status). Nothing checked coverage,
so nothing noticed.

## Decision

1. **Coverage is a computed property of the matter, not a convention.**
   `sc text audit` classifies every PDF, image, DOCX and audio file
   under the matter (outside `out/`, `.state/`, `.git/`, `.flow/`) as
   `searchable`, `unverified-sidecar`, `needs-sidecar`, `stale-sidecar`,
   `needs-ocr`, `transcript-needed`, `unsupported`, `unreadable`, or
   `untriaged` (inbox). A PDF is `searchable` only when a current
   sidecar written by the tool covers every page; an `_ocr` sibling by
   itself proves nothing.
2. **Repair is mechanical.** `sc text ensure` OCR-supplements PDFs whose
   pages lack a usable text layer (`ocrmypdf --skip-text`, or
   `--force-ocr --pages` for pages whose text is useless: image-bodied,
   garbled), then writes a `.txt` sidecar from the best source with a
   provenance header and `[[[ page k of N ]]]` markers so a hit carries
   a page cite. Images get `<stem>.ocr.txt` through tesseract; DOCX
   gets `<stem>.txt` through pandoc. Audio is reported only; the local
   transcription pipeline is a separate, human-supervised step.
3. **Originals and human sidecars are never touched.** Everything the
   tool writes is a sibling. A `.txt` without the tool's header is
   someone's transcription: it is searched, reported as unverified, and
   never overwritten. The tool rewrites only its own sidecars, and only
   when the document or its `_ocr` sibling is newer.
4. **Search refuses to hide a gap.** `sc find` takes its UNSEARCHED
   list from the audit, prints the coverage line, and exits 2 whenever
   anything triaged is not searchable --- with or without hits. `--ensure`
   runs the repair first. The `/find` command uses `--ensure`.
5. **The sync runs ensure.** After the connectors and before the agent,
   `matter_sync.sh` runs `sc text ensure`, so a document that arrives is
   searchable before anyone reads it. The same change makes the
   connector loop test node's exit status rather than sed's.
6. **The brief carries the coverage line.** Every session starts by
   seeing how much of the record is searchable.
7. **Classification is cached** in `.state/text_coverage.json` keyed by
   path, size and mtime (of the document, its `_ocr` sibling and its
   sidecar), so an audit of a thousand documents is fast and a changed
   file is always re-surveyed.

## Consequences

- Machine sidecars double the file count beside born-digital PDFs
  (every gmail export gains a `.txt`). That is the price of a record
  ripgrep can search in full; the header makes machine text
  distinguishable from a human transcription at a glance.
- "Not in the record" acquires a checkable meaning: the coverage line
  says how much was searchable and the UNSEARCHED list names the rest.
- The first `ensure` on a live matter is a long batch (hundreds of text
  dumps, OCR for the scans); later runs touch only new or changed
  files.
- Handwriting remains a gap tesseract fills poorly. A review interface
  for correcting handwritten regions, whose corrections become
  human-verified sidecar text, is the planned next step (W4b in the
  v2 proposal).
- The triage prompt no longer asks the agent to write or skip sidecars;
  it tells the agent they exist and to check the audit.
