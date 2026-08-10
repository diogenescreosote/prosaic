# Hosted deployment — constraints and design notes

**Status: not decided, not scheduled.** prosaic is local-first (see
[ADR 0001](adr/0001-plain-files-over-database.md)). This file records
what a hosted version
would have to satisfy, so the local design does not accidentally
foreclose it — and so the decision, when it comes, is made against
written constraints rather than momentum.

The shape under discussion: agents and their tooling run on a Linux
server; the matter tree lives there on a real filesystem; users read
through the browser and contribute through an inbox.

---

## The constraint that dominates everything

Moving matter files onto a server puts **privileged material in a
third party's hands**. That is a professional-responsibility
question before it is an engineering question, and it is the reason
this is deferred rather than merely unbuilt.

The general position — that storing client material with a cloud
provider is compatible with confidentiality obligations *provided
reasonable security measures are taken* — is widely accepted, but the
specific obligations vary by jurisdiction and the phrase "reasonable
measures" carries the weight. Before shipping anything hosted, this
needs actual research against the relevant rules, not an engineer's
summary. At minimum it implies:

- Encryption at rest, and a defensible answer about who holds keys
- Access logging sufficient to reconstruct who saw what
- A data-processing agreement with the hosting provider, which becomes
  a subprocessor
- A breach-notification path that exists before it is needed
- A deletion guarantee that is real, including backups

**Hard tenant isolation is the piece to design first**, because it is
the one that cannot be retrofitted: container per matter, distinct
UIDs, no shared mounts, no path by which one tenant's agent can read
another tenant's tree. Everything else on this list can be added
later; this one has to be structural.

## What gets easier

Worth recording, because these are genuine wins and not just costs:

- **No cloud-sync filesystem semantics.** A real Linux filesystem
  means no File Provider, no dehydrated placeholders, no cache
  eviction, no full-tree grep that is fast until one day it isn't.
- **Scheduled work actually runs.** The current launchd catch-up-once
  design exists because laptops sleep. A server does not.
- **Docker becomes the right tool.** Everything awkward about
  containerizing a consumer desktop app — the VM layer, the missing
  GPU, the Docker Desktop install — is not a problem on a Linux host.
  Reproducible deployment is exactly what containers are for.
- **Long jobs stop being the user's problem.** A seventeen-minute
  portal sync does not need the user's machine awake.

## Access: don't mount

The instinct is to give users a mounted tree, read-only except for
`inbox/`. That split is exactly what mount protocols handle worst, and
the cross-platform story is bad: SSHFS needs macFUSE, a kernel
extension that is increasingly hostile on Apple Silicon; macOS's
WebDAV client is historically unreliable.

**The web UI is already the read path.** It renders better than
Finder, and search, chronology, and exhibit context are things a
filesystem cannot show. The inbox is a one-way upload — a form, not a
filesystem. That covers the ordinary user completely.

For users who genuinely want files on disk, offer a one-way sync down
(rclone, or letting the server write into a folder the user's existing
Dropbox/Drive account syncs) as a *convenience copy*, explicitly not
the source of truth. Do not try to make it writable.

## The power-user path

Running Claude Code locally against a remote tree reintroduces every
sync and concurrency problem that hosting was supposed to remove.
Two clean options, no hybrid:

1. **Local mode** — the whole stack, tree included, runs on the user's
   machine. This is the product described in the roadmap.
2. **SSH to the server** and run Claude Code there. Costs nothing to
   support, and gives a power user the full environment with no
   architectural compromise.

## Audio: an unresolved policy question

The workspace rule is that privileged audio is transcribed locally and
never uploaded to a cloud transcription service. A server the operator
controls is not "a cloud transcription service" in the sense that rule
was written to prohibit — but it *is* privileged audio leaving the
user's machine.

This needs an explicit decision rather than an architectural default.
The plausible answers are: transcribe on the client and upload only
text; transcribe server-side with a stated policy and per-tenant
encryption; or refuse to accept audio in hosted mode at all.

## Things the local design should preserve

To keep this option open at near-zero cost, the local build should
avoid:

- Any assumption that the tree is on the same machine as the browser
  (keep the server/UI boundary honest even when both are localhost)
- Any assumption of a single user in the data model — jobs and
  mutations should carry an actor, even when the actor is always the
  same person
- Absolute paths baked into stored artifacts
- Anything that makes the matter directory non-portable between an
  APFS volume and an ext4 one
