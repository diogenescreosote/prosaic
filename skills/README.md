# Skills: agent-facing capability packaging

A skill is a directory holding one `SKILL.md`: procedural knowledge an
agent loads when a task calls for it, in the open agent-skills
convention (YAML frontmatter with `name` and `description`, then
instructions). Skills are how prosaic's capabilities present
themselves to whatever agent is driving — the harness-neutral
counterpart to the contracts in `AGENTS.md` (ADR-0021).

The discipline:

- **A skill instructs; the engine computes.** SKILL.md tells the agent
  which commands to run, in what order, and what to verify. Behavior
  lives in the engines the skill points at, covered by their specs and
  tests. If writing a skill makes you want to put logic in it, the
  logic belongs in a CLI the skill calls.
- **`name` in frontmatter equals the directory name.** The
  `description` says what the skill does AND when to reach for it —
  that one field is how an agent (or its harness) decides to load the
  rest of the file.
- **Skills stay current or fail the suite.** `tests/test_skills.py`
  enforces the structure, the index below, and that every command a
  skill names still exists. What it cannot check — whether the
  instructions are any good — is on you, same as docs.
- **One skill per task-shape**, not per component: "build a filing
  packet" is a skill; "the pleading renderer" is a component with a
  spec.

Harness note: some harnesses discover skills automatically (Claude
Code and compatible tools read `SKILL.md` frontmatter); any other
agent can read this index and open the file it needs. Nothing here
depends on a particular harness.

## Index

| Skill | What it does |
|---|---|
| [estate-plan](estate-plan/SKILL.md) | Draft, execute, and cryptographically bind a California estate plan from the estate pack |
| [esign](esign/SKILL.md) | Send a document for e-signature via DocuSeal and bring the signed original + audit log back |
| [crypto-attest](crypto-attest/SKILL.md) | Sign, verify, hash, manifest, and timestamp matter documents against a paper-anchored key |
| [build-envelope](build-envelope/SKILL.md) | Build a filing packet (pleading PDF/DOCX, exhibits, cover forms) from a matter's markdown sources |
| [fill-form](fill-form/SKILL.md) | Fill a Judicial Council form from its YAML descriptor, with the verification discipline |
| [triage-inbox](triage-inbox/SKILL.md) | Move new material from inbox/ to assets/ under the matter conventions |
| [drafting-conventions](drafting-conventions/SKILL.md) | Pagination and signature-block discipline: what the renderer enforces, what the drafter judges |
| [run-flow](run-flow/SKILL.md) | Run or write a files-first flow: agent/judge/gate graphs for drafting loops and review passes |
| [new-matter](new-matter/SKILL.md) | Scaffold a matter directory: layout, git, hooks, contracts, backup |
