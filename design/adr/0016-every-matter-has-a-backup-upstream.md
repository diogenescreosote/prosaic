# 0016 — Every matter has a backup upstream; the default is a local bare repo

**Status:** accepted (2026-08)
**Amends:** [ADR 0014](0014-docket-shaped-commits.md) — "never push a
matter" becomes "never push a matter anywhere but its configured
backup remote."

## Context
ADR-0001 makes a matter a directory of plain files with git as its
history, and ADR-0014 forbade agents to push one anywhere. That was
right about the risk — a matter is privileged material and must not
leave the machine by accident — and wrong about the consequence: it
left the entire history of a live case existing in exactly one place,
on one disk. The realistic threat is not hardware failure. It is a
stray `rm -rf`, a bad `git checkout`, a cloud-sync client eating a
directory it was mid-write on. Those destroy the working tree and
`.git` together, and a rule against pushing guarantees there is no
second copy.

The trouble is that the obvious fix, a private repo on a hosting
service, is not available to most of the people this is for. A
self-represented litigant does not have a paid GitHub account, and
requiring one would make the backup story "there isn't one" for the
default user.

## Decision
A matter declares a `backup:` block in `matter.yaml` and gets a git
remote named `backup` — never `origin`, which a matter has no business
having and whose name invites the muscle memory of a bare `git push`.

Two backends. **`local`** is the default and needs nothing: a bare
repository outside the working tree, at
`<data-dir>/backups/<matter>.git` unless a path is given. It survives
everything that deletes the matter directory, which is the threat.
**`github`** pushes to a private repository for users who have one.
Before every push — not only at `sc backup init` — the GitHub backend
asks the API whether the repository is private and refuses if it is
not, because visibility can be changed after setup and the difference
between private and public here is the difference between a backup and
a disclosure.

A `post-commit` hook backs up after every commit and is deliberately
non-fatal: a failed push must never fail a commit. `sc backup
init|push|status` drives it by hand.

## Consequences
The single-copy problem goes away for every user, not just the ones
with a hosting account, and it goes away without anyone remembering to
do anything — a backup you must remember to run is one you learn about
after you needed it. `sc backup status` answers "is my case backed
up?" in one line.

The honest limits, since a backup that is trusted further than it goes
is worse than none. The local backend is **same-machine**: it defeats
`rm -rf` and a bad checkout, not a stolen laptop, a failed disk, or
disk encryption you cannot unlock. Offsite for the default user is
unsolved and stays open — an encrypted bundle pushed to ordinary cloud
storage is the likely shape, and it is not built here. The GitHub
backend puts privileged client material on a third party's servers,
which is a real professional-responsibility decision for the user to
make deliberately; it is opt-in, never inferred, and the private check
runs every time rather than being trusted once.

Amending ADR-0014 narrows a rule that was doing real work, so the
narrowing is exact: an agent may push a matter to its configured
`backup` remote and to nothing else. Adding or changing that remote is
a config change the user makes; an agent does not point a matter at a
new destination on its own.
Alternatives: a second working clone (rejected — a full copy that can
itself be deleted, and it invites divergent edits); filesystem
snapshots (rejected — platform-specific, and invisible from inside the
tool); requiring a hosting account (rejected — it makes the default
user's backup story "none"); `git bundle` to a file on a schedule
(rejected for now as the primary, since it is a snapshot rather than a
history and has no incremental push, but it is the natural basis for
the offsite work above).
