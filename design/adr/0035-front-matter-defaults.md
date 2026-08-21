# ADR-0035: Front-matter defaults — box config, shadowed by matter config

**Status:** Accepted (August 21, 2026)

## Context

Some caption values are properties of the person running the
deployment, not of any one document: a designated electronic-service
address, for instance, is the same on every proof of service in every
matter on the box. Restating such values in every source's front
matter invites drift — and the first omission shipped a proof of
service carrying the wrong e-service address.

ADR-0031 holds that prosaic-the-repo stores no state, and ADR-0032
gives every deployment a gitignored `local/` tree for exactly this
kind of box-specific content.

## Decision

A three-level default chain for front-matter values, lowest precedence
first:

1. `local/config.yaml` → `front_matter_defaults:` (deployment-wide);
2. `<matter>/matter.yaml` → `front_matter_defaults:` (per-matter
   shadow);
3. the source's own front matter, which always wins.

`jc_common.front_matter_defaults(case_dir)` loads the chain; the
pleading build merges it under the parsed front matter, and the form
engine merges the box level under direct-fill metas. Missing or
unparseable files contribute nothing. First use:
`filer_eservice_address`, feeding e-service proofs through the
`eservice_address` auto binding.

## Consequences

- prosaic itself still stores nothing (ADR-0031 intact): the box level
  lives in the gitignored/cloned `local/`, the matter level in the
  matter's own config.
- A default is invisible in the source that uses it; `sc form info`
  and the built PDF are where its effect shows. Registered keys only —
  an unregistered key in a defaults block will trip the same
  unknown-key warning as in a source.
- Defaults apply to FRONT MATTER only, not to per-form `forms:` blocks
  — form-specific values stay in sources or descriptors.
