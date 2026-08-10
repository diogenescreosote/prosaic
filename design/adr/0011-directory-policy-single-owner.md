# 0011 — One owner for directory policy, asked over a process boundary

**Status:** accepted (2026-08)

## Context
Where prosaic keeps logs, durable data, and caches was decided
wherever the question first came up: `~/Library/Logs/prosaic`
hardcoded in two shell scripts and again in a Node module. Three
copies of one policy, in three languages, none of which knew about the
others. That is a portability bug and a privacy leak at once, and it
teaches itself — a tree that declares POSIX-first and then hardcodes an
Apple path trains the next contributor, human or agent, to hardcode.
The polyglot split (ADR-0002) means any shared policy has at least two
consumers in two runtimes, so "put it in a library" has no single
answer.

## Decision
Directory policy has exactly one implementation: `app_path` in
`cli/sc`, exposed as `sc paths <kind>` for `log-dir`, `data-dir`, and
`cache-dir`. `sync/lib.sh` and `connectors/core/paths.js` call it
rather than reimplementing it. Each kind is overridable by
`PROSAIC_{LOG,DATA,CACHE}_DIR`, and anything that spawns children
resolves once and exports the answer — `matter_sync.sh` exports
`PROSAIC_LOG_DIR`, so the connectors it spawns inherit it and the
hot path spawns no resolver at all. Apple locations on macOS, XDG
elsewhere, with `data-dir` pinned to `~/.local/share` on both because
that is where live browser profiles already sit; moving it needs a
migration, not a default.

## Consequences
The copies cannot drift because there are no copies — a stronger
guarantee than a test asserting that copies agree, and the hygiene
sweep (`tests/test_repo_hygiene.py`) can now forbid home-directory
paths outright because there is a resolver to use instead. Cost: a
subprocess on the cold path, and Node's `paths.js` fails with an
actionable error if `cli/sc` or `python3` is missing — acceptable,
since it is one spawn, cached, and normally skipped via inheritance.
This does not disturb ADR-0004: launchd and the FDA shim remain the
macOS scheduling backend, now reached through a platform dispatch in
`install_schedule.sh` that refuses elsewhere by name. The scheduler
abstraction itself is still owed its own ADR.
Alternatives: duplicate the logic per runtime and test that the copies
agree (rejected — a test that catches drift is worse than a structure
that cannot drift); a shared config file both runtimes parse (rejected
— policy with a platform conditional is code, and a file that must be
generated is a fourth copy); a Node implementation with Python calling
it (rejected — `sc` is already the dispatcher every entry point goes
through).
