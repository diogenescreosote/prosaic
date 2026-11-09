---
name: build-envelope
description: Build a filing packet (28-line pleading PDF/DOCX, exhibits, cover forms) from a matter's markdown sources. Use when asked to build, rebuild, list, or check staleness of an envelope, or when a src/ edit needs to become a filing-ready PDF.
---

# Build a filing envelope

Run from the matter directory (it has `envelopes.yaml`); the `sc` CLI
drives the build (ADR-0039).

## The loop

1. `sc list` — the envelopes this matter defines, and their variants.
2. `sc build <envelope> --variant <public|sealed>` — build one. The
   build is manifest-aware: an output is rebuilt when its source,
   dependencies, or render options (`--final`, variant, signer, date)
   change (`--force` overrides). `sc build-doc src/<source>.md` builds
   exactly one envelope-owned source, with its configured DOCX.
3. **Read stderr.** The build warns rather than fails on things you
   must act on:
   - `front-matter key X is not read by anything` — misspelled or
     invented key; fix it or make it a YAML comment. Recognized keys:
     `<prosaic>/pleading/front_matter_keys.yaml`.
   - `spaced dash` — the em-dash rule was violated in a source
     (`text---text`, never `text --- text`).
   - `no --variant specified` — output landed in `out/<envelope>/`
     instead of a variant subdirectory.
4. Verify the output PDF: page count, caption, exhibit designators
   (letters, or numbers under `exhibit_numbering: numeric`; a paper
   answering lettered exhibits should number its own), the
   draft banner. An unfiled document must carry its `notreal:` banner
   on every page (ADR-0015, ADR-0017).

## Rules that bind you

- Output goes under `out/`; never hand-edit anything there. Sources
  are `src/*.md`; the renderer's language is defined in
  `<prosaic>/pleading/pleading_markdown_spec.md`.
- A form attachment is not a standalone pleading: it needs
  `no_caption: true` and its own two-line opener (the build fails
  without it — add the key, never remove `cover_sheet:` to silence
  it).
- **A form and its attachment are filed as ONE PDF**, form first
  (a request form + its Attachment 9, SUBP-010 + Attachment 3). Clerks reject the whole envelope when the attachment
  is uploaded as its own document. If they are separate sources, the
  attachment's envelopes.yaml entry says `attachment_of: <form
  source>`; `--final` refuses an envelope that leaves a checked
  attachment box or an "ATTACHMENT N TO" source unpaired. After
  signing, join the pair (`qpdf --empty --pages form.pdf att.pdf --
  joined.pdf`) and run **`sc filing-check <staging folder>`** before
  handing the folder over for upload; it must report no errors.
- Stale output is a hazard, not clutter: `<prosaic>/cli/sc clean .`
  reports files the config can no longer produce; only `--apply`
  deletes, and only a human decides.
- Rebuilding is a `build` commit, separate from the `draft` commit
  that changed the sources.

Signature areas and execution clauses have their own discipline:
[drafting-conventions](../drafting-conventions/SKILL.md).

References: `specs/pleading/generator.md`, `docs/forms.md`,
`pleading/pleading_markdown_spec.md`.
