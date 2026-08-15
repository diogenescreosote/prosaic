# 0032. Local modules: a gitignored overlay for deployment-specific content

## Status

Accepted (August 2026).

## Context

prosaic is public and generic. Its live deployments need content that
must never be tracked here: practice-area form packs, extra
connectors, extra front-matter keys, deployment contracts. The first
answer was a private fork ("changes flow down, never up"), which
worked but put every generic fix one merge away from the deployments,
invited development in the wrong repo, and made the fork's identity
(README counts, contract renames) a standing conflict surface.

## Decision

A deployment extends prosaic through a single gitignored directory,
`local/`, at the repo root, mirroring the repo layout. The overlay is
discovered at runtime; nothing in prosaic references any specific
local module:

- `local/pleading/forms/registry/*.yaml` and `local/pleading/forms/*.pdf`
  join the descriptor registry and blanks search path
  (`form_fill.REGISTRY_DIRS` / `BLANKS_DIRS`); on an id collision the
  local descriptor wins.
- `local/pleading/front_matter_keys.yaml` merges into
  `recognized_front_matter_keys()`.
- `local/pleading/auto_bindings.py` may define `AUTO_BINDINGS` to add
  or override `auto:` bindings (`jc_common._load_local_auto_bindings`).
- `local/connectors/<name>/pull.js` joins connector dispatch
  (`sync/matter_sync.sh`: `connector_entry`, `installed_connectors`);
  the legacy envelopes.yaml key scan derives from installed connector
  names instead of a hardcoded tuple; the local copy of a name wins.
- Anything else in `local/` (templates, specs, tests) is inert to
  prosaic: consumed by symlinks or run explicitly, never imported.

A deployment is therefore a plain prosaic checkout plus a `local/`
tree, which is itself a separate (typically private) repository
cloned in place. The tests here must pass with or without a local
overlay present.

## Consequences

- The private-fork pattern is retired for new work; deployments track
  prosaic main directly and update by `git pull`.
- Local content cannot hook arbitrary internals: the seams above are
  the contract. A local need that doesn't fit them is a prosaic
  feature request, made here, generically.
- The leak guard stays intact in deployments because deployment
  content lives under `local/`, which is untracked.
- `list_forms()` and friends report the union, so `sc form info` and
  build errors name local forms naturally.
