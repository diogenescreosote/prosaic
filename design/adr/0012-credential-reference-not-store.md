# 0012 — A matter names a credential, not a credential store

**Status:** accepted (2026-08)

## Context
Connectors authenticate to law-firm and records portals with a real
login. The lookup called macOS `security` directly from
`portal_common.js`, and `matter.yaml` spelled the key
`keychain_service:` — a config file naming an Apple mechanism, in a
project whose stated posture is that platform specifics live behind
seams. The key had lock-in: it appears in every matter already
written. Headless and CI runs, which have no keyring at all, had no
way in.

## Decision
`connectors/core/secrets.js` resolves a credential *reference* to
`{account, password}` through a chosen backend: `env`
(`PROSAIC_OFW_USERNAME` / `_PASSWORD`, derived from the reference by
upper-casing and collapsing non-alphanumerics), `keychain` (macOS
generic passwords), or `auto` — the default — which takes `env` if
present and falls back to `keychain` on Darwin. `credential:` replaces
`keychain_service:` in `matter.yaml`; the old key still resolves,
behind a `DeprecationWarning`, so matters in flight do not break.
`env` deliberately wins under `auto`: that is what lets a container, a
CI job, or a developer pointing one run at a test account override
without touching the user's keyring. Secret Service, `pass`, and
age/sops backends are *not* written — there is no machine to test them
on, and an untested credential backend is worse than an absent one; the
`auto` path on an unrecognized platform fails with a message naming the
two environment variables to set and the file to extend.

## Consequences
The same `credential: prosaic.mycase` works on a laptop and in a
container, and a new backend is a function in one file rather than an
edit to every connector. A half-configured environment (username
without password) is an error rather than a silent fallthrough to the
keyring, which would otherwise present as a mystifying wrong-account
login. Cost: two names for one thing until the deprecated key is
removed, and `env` beating `keychain` means a stale exported variable
can quietly shadow the keyring entry — the tradeoff accepted in
exchange for overridability.

This seam lives in Node, not in `cli/sc`, which is where ADR-0011 put
directory policy and where the roadmap sketched a `sc secret get`.
The difference is the consumer count: paths have callers in both
runtimes, credentials have callers only in `connectors/`. Putting
credential resolution behind a subprocess today would buy nothing and
would widen the blast radius of a secret — it would cross a process
boundary and could land in an argument list or a log. If a Python
consumer ever appears, `sc secret get` is the move, and this ADR gets
superseded rather than quietly outgrown.
Alternatives: keep calling `security` inline and add platform
conditionals at each call site (rejected — three copies of the same
conditional); an encrypted file in the repo (rejected — privileged
credentials do not belong in a tree that gets pushed); require
environment variables only, dropping the keyring (rejected — the
interactive Mac user is the primary user and should not export secrets
into a shell).
