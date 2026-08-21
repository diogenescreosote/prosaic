# ADR-0034: Module repos — commit-pinned submodules under modules/

**Status:** Accepted (August 21, 2026)

## Context

ADR-0032 gave deployments a gitignored `local/` overlay for
deployment-specific descriptors and blanks. It solved "patch a stock
form without editing the repo," but it cannot be *shared*: local/ is
untracked by design, so a family of forms developed in one deployment
(e.g. California family-law forms, which are deliberately kept out of
the public repo) exists only as loose files on one machine — no
history, no distribution, no pinning.

What is wanted is the smallest possible package system: a deployment
points at another repo and says "include what's here," pinned to a
commit.

## Decision

**Module repos are ordinary git repos mirroring the prosaic layout,
included as git submodules under `modules/<name>/`.** Nothing more.

- A module repo carries the same subtree shapes it overlays:
  `pleading/forms/registry/*.yaml`, `pleading/forms/*.pdf`,
  `specs/pleading/forms/*.md`, `docs/…` as needed.
- A deployment includes one with
  `git submodule add <url> modules/<name>` — the gitlink IS the
  commit pin; updating a module is `git -C modules/<name> pull` plus
  committing the new gitlink. No lockfile, no resolver, no manifest.
- There is no dependency DAG. Modules cannot include modules. If two
  modules collide on a form id, discovery order (alphabetical by
  module name) decides, and the collision is the deployment's problem
  to notice — the dumbest workable rule, on purpose.
- Discovery precedence, first hit wins:
  `local/` → `modules/<name>/` (alphabetical) → built-in.
  `local/` stays what ADR-0032 made it: uncommitted, per-deployment,
  outranking everything — the scratch space in front of the modules.
- Public/private split falls out naturally: generic form families are
  committed to prosaic itself; jurisdiction- or practice-specific
  families (family law) live in their own repos — private where
  appropriate — and are pulled in only by the deployments that want
  them. The no-case-material rule applies to module repos exactly as
  it applies to prosaic: a module carries blank forms and generic
  descriptors, never matter facts.

## Consequences

- `modules/` is a tracked directory in a deployment fork; prosaic
  itself ships it empty. Submodule ergonomics (clone with
  `--recurse-submodules`, the extra commit to bump a pin) are accepted
  as the cost of getting pinning and distribution from git itself.
- Engine discovery (`form_fill.py`) scans the module subtrees; other
  overlay points (triage prompts, templates) can adopt the same rule
  when a module first needs them — deliberately not built ahead of
  need.
- First module: `family-law-forms` (private), carrying the FL-series
  descriptors previously living in a deployment's local/ overlay.
