---
name: fill-form
description: Fill a California Judicial Council form (CIV-110, EFS-020, MC-025, MC-030, SUBP-010, SUBP-025) from its YAML descriptor. Use when a filing needs an official form completed, or when adding or changing a form descriptor.
---

# Fill a Judicial Council form

One engine executes every form from a YAML descriptor
(`<prosaic>/pleading/forms/registry/<id>.yaml`); no form has its own
code path (ADR-0006).

## The loop

1. `<prosaic>/cli/sc form list` — the registered forms.
2. `<prosaic>/cli/sc form info <id>` — the descriptor's fields,
   checkboxes, and agent guide. This output is designed to be enough
   to fill the form correctly without reading the registry source.
3. `<prosaic>/cli/sc form fill <id> ...` per the info output.
4. Overflow: text that does not fit spills to an MC-025 attachment
   automatically (ADR-0007) — never truncate a filing to make it fit,
   and never shrink text below legibility.

## The verification discipline (non-negotiable)

Never trust a JC field name: the official AcroForms misname fields
freely (`specs/pleading/forms/README.md` collects the horror stories).
Any change to a descriptor requires empirical verification:

1. Fill the form with distinctive test values.
2. Rasterize the filled PDF (PNG per page).
3. Look at it — yourself, or via the AI judge
   (`tests/harness/ai.py`) with a rubric naming what must appear
   where.

A descriptor change without a fill-rasterize-look pass is a defect
even if the tests stay green.

## Adding a form

New descriptor in `pleading/forms/registry/`, the blank PDF beside the
others, a spec page under `specs/pleading/forms/`, and deterministic
tests in `pleading/tests/`. Follow an existing descriptor's shape; the
descriptor schema is documented in
`pleading/pleading_markdown_spec.md`.

References: `specs/pleading/forms/README.md`, `docs/forms.md`.
