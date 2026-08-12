---
name: build-envelope
description: Build a filing packet (28-line pleading PDF/DOCX, exhibits, cover forms) from a matter's markdown sources. Use when asked to build, rebuild, list, or check staleness of an envelope, or when a src/ edit needs to become a filing-ready PDF.
---

# Build a filing envelope

Run from the matter directory (it has `envelopes.yaml` and a
`Makefile` that includes prosaic's).

## The loop

1. `make list` — the envelopes this matter defines, and their variants.
2. `make <envelope> VARIANT=<public|sealed|...>` — build one. Under
   the hood this is `<prosaic>/cli/sc build`, which honors staleness:
   an up-to-date envelope is not rebuilt (`--force` overrides).
3. **Read stderr.** The build warns rather than fails on things you
   must act on:
   - `front-matter key X is not read by anything` — misspelled or
     invented key; fix it or make it a YAML comment. Recognized keys:
     `<prosaic>/pleading/front_matter_keys.yaml`.
   - `spaced dash` — the em-dash rule was violated in a source
     (`text---text`, never `text --- text`).
   - `no --variant specified` — output landed in `out/<envelope>/`
     instead of a variant subdirectory.
4. Verify the output PDF: page count, caption, exhibit letters, the
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
- Stale output is a hazard, not clutter: `<prosaic>/cli/sc clean .`
  reports files the config can no longer produce; only `--apply`
  deletes, and only a human decides.
- Rebuilding is a `build` commit, separate from the `draft` commit
  that changed the sources.

References: `specs/pleading/generator.md`, `docs/forms.md`,
`pleading/pleading_markdown_spec.md`.
