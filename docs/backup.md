# Backing up a matter

A matter is a directory of plain files with git as its history
([ADR-0001](../design/adr/0001-plain-files-over-database.md)). That is
the whole point — but until it has somewhere to push, the entire
history of a live case exists in exactly one place.

The threat is not a failed disk. It is a stray `rm -rf`, a bad
`git checkout`, or a sync client eating a directory it was mid-write
on. Those take the working tree and `.git` together.

So every matter gets a `backup` remote.
([ADR-0016](../design/adr/0016-every-matter-has-a-backup-upstream.md).)

## Setup

Add a `backup:` block to `matter.yaml`, then initialize:

```bash
sc backup init .
sc backup status .
```

`sc hooks .` installs a `post-commit` hook that pushes after every
commit, so it keeps up without anyone remembering.

### `local` — the default, no account needed

```yaml
backup:
  kind: local
  # path: ~/backups/smith.git    # optional; defaults under the data dir
```

A bare repository outside the working tree, at
`<data-dir>/backups/<matter>.git` by default (`sc paths data-dir`).
Nothing to install, nothing to sign up for.

**What it protects against:** deleting the matter directory, a
destructive git operation, a sync client corrupting the tree.

**What it does not:** a stolen laptop, a dead disk, or a full-disk
encryption key you cannot produce. It is on the same machine. Point
`path:` at an external or network volume and it covers more.

### `github` — a private repository

```yaml
backup:
  kind: github
  repo: youraccount/smith-v-smith-matter
```

Requires the `gh` CLI, authenticated. **The repository must be
private.** prosaic asks the GitHub API before *every* push — not
just at setup — and refuses if the answer is no:

```
REFUSING: you/matter is a PUBLIC GitHub repository.
A matter is privileged material and is never pushed to a public repo.
```

Visibility can be changed after setup, which is why the check is not
trusted once and cached.

Understand what this is: privileged client material on a third party's
servers. That is a professional-responsibility decision for you to
make deliberately, which is why it is opt-in and never inferred.

## Restoring

The backup is an ordinary git repository. Clone it:

```bash
git clone <backup-url> smith-v-smith
cd smith-v-smith && sc backup init .
```

Everything tracked comes back. Everything gitignored does not — for a
matter that means `.state/` (regenerable by re-running `sc sync`) and
whatever else that matter ignores. Check its `.gitignore` before
relying on the backup to hold something.

## Agents and the backup remote

[ADR-0014](../design/adr/0014-docket-shaped-commits.md) said an agent
never pushes a matter. [ADR-0016](../design/adr/0016-every-matter-has-a-backup-upstream.md)
narrows that precisely:

- An agent may push a matter to its configured `backup` remote.
- An agent may push it **nowhere else**.
- An agent does not add or repoint a `backup` remote. Where a matter
  gets copied to is a config change you make.

## Still open: offsite for everyone

The `local` backend is same-machine, and `github` needs an account
most people do not have. Offsite backup for the default user is
unsolved. The likely shape is an encrypted bundle pushed to ordinary
cloud storage — encrypted client-side, so the storage provider is
never in a position to read a privileged file. It is not built.
