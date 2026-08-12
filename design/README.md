# design/ — how it's built, and why

Where `specs/` states what each component must accomplish, this
directory records the *decisions* that shaped how it does so:
lightweight **Architecture Decision Records** (ADRs). The goal is
coherence — a place where a change that cuts across components gets
checked against the reasoning that produced the current seams, so the
project accretes decisions instead of middleware.

## Rules

- One decision per file, numbered, never edited after acceptance —
  supersede with a new ADR that links back.
- Format: **Context** (the forces), **Decision** (one paragraph),
  **Consequences** (what gets easier, what gets harder, what we gave
  up). Alternatives considered get a sentence each, not an essay.
- Write the ADR when the decision is made, not after the code works.
  An unrecorded decision is a future argument.
- If implementing something requires violating an accepted ADR, stop
  and write the superseding ADR first.

## Index

- [0001](adr/0001-plain-files-over-database.md) Plain files over a database
- [0002](adr/0002-polyglot-python-node.md) Polyglot Python + Node, thin CLI
- [0003](adr/0003-connector-contract.md) Connectors as processes with a NEW-line protocol
- [0004](adr/0004-launchd-with-fda-shim.md) launchd + compiled FDA shim for scheduling on macOS
- [0005](adr/0005-headless-claude-triage.md) AI triage as a headless Claude Code session
- [0006](adr/0006-forms-as-descriptors.md) JC forms as YAML descriptors, one engine
- [0007](adr/0007-mc025-overflow.md) Overflow spills to MC-025, never shrinks below legibility
- [0008](adr/0008-pytest-plus-llm-judge.md) pytest + in-house LLM judge for the test harness
- [0009](adr/0009-tiered-nonblocking-testing.md) Tiered nonblocking testing with delegated cheap-model runs
- [0010](adr/0010-no-buried-magic.md) No buried magic; extraction where it pays
- [0011](adr/0011-directory-policy-single-owner.md) One owner for directory policy, asked over a process boundary
- [0012](adr/0012-credential-reference-not-store.md) A matter names a credential, not a credential store
- [0013](adr/0013-system-dependencies-declared-once.md) System dependencies declared in a manifest; the image is built from it
- [0014](adr/0014-docket-shaped-commits.md) Docket-shaped commits, and what an agent may commit
- [0015](adr/0015-unfiled-documents-announce-themselves.md) An unfiled document says so on every page
- [0016](adr/0016-every-matter-has-a-backup-upstream.md) Every matter has a backup upstream; the default is a local bare repo
- [0017](adr/0017-banner-stamps-the-whole-packet.md) The draft banner stamps the whole packet, in a reclaimed band
- [0018](adr/0018-form-attachments-are-not-pleadings.md) A form attachment is not a pleading, and the build enforces it
- [0019](adr/0019-one-system-not-two.md) One system, not two: the typed library is removed
- [0020](adr/0020-agent-harness-agnostic.md) One agent-CLI seam; contracts named AGENTS.md
- [0021](adr/0021-skills-as-capability-packaging.md) Skills: capability packaging for agents, one SKILL.md each
- [0022](adr/0022-paper-anchored-attestation.md) Paper-anchored attestation: pinned keys, dual hashes, a signed manifest

Also:

- [hosted-deployment-notes.md](hosted-deployment-notes.md) — constraints a
  server-hosted deployment would have to satisfy. Not a decision; a
  record of the forces, kept so the local-first design doesn't
  foreclose it by accident.
