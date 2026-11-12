# Example Foundation

Start with **`START HERE.md`**: what this folder is, how it is
organized, and where the entity stands.

prosaic entity matter (ADR-0051). Layout:

```
START HERE.md     Front page for any reader; current state, with sources
JOURNAL.md        Journal of acts: every official act, numbered and dated, append-only
assets/           The record book, in numbered sections; assets/INDEX.md lists every document
inbox/            Drop zone for new material, unprocessed by definition
processed_files/  Canonical raw bytes of triaged inbox material
derived/          Text layers and OCR copies of the record (regenerable)
src/              Markdown drafts: bylaws, resolutions, minutes, consents
out/              Build output (generated)
memos/            Analysis memos
staging/          Signed sets on their way out (YYYY-MM-DD_topic/ + README.md)
knowledge/        Notes vault; KNOWLEDGE.md is its index
TODO.md           Open tasks and the compliance calendar
QUESTIONS.md      Open questions for the people who run the entity
matter.yaml       Matter configuration
envelopes.yaml    Document sets built together
```

Build: `sc list`, `sc build <envelope>`, `sc build-doc src/<source>.md`.
