# 0021 — Skills: capability packaging for agents, one SKILL.md each

**Status:** accepted (2026-08)

## Context
prosaic's capabilities are documented for humans (docs/), specified
for developers (specs/), and bound to matters as conventions
(templates). What was missing is the agent-operative form: the
procedural knowledge "how do I build an envelope / fill a form /
triage an inbox," packaged so an agent loads it when the task calls
for it instead of re-deriving it from four documents. The open
agent-skills convention (a directory with a SKILL.md: YAML
frontmatter carrying `name` and `description`, then instructions) is
now read natively by several harnesses and is plain markdown for the
rest — the same harness-neutral posture as ADR-0020.

## Decision
Task-shaped capabilities get a `skills/<name>/SKILL.md` at the repo
root, indexed in `skills/README.md`. The discipline, stated there and
enforced by `tests/test_skills.py`:

1. **A skill instructs; the engine computes.** No logic in SKILL.md —
   commands to run, order, what to verify, and the pointers into
   specs/docs. If a skill wants logic, the logic becomes a CLI first.
2. Frontmatter `name` equals the directory name; `description` states
   what it does and when to use it (both halves — that field is the
   loading trigger).
3. Every skill is indexed; every index row resolves; every `sc`
   subcommand and repo path a skill names exists. Mechanically
   checked, so a renamed command cannot leave a skill instructing
   the void.

Skills are documentation with a load contract, so the documentation
row in AGENTS.md gains: an agent-facing capability must land as (or
update) a skill.

## Consequences
New capabilities (signing, cryptographic attestation, QR blocks,
estate drafting) land as skills over their CLIs, and an agent in a
matter can be pointed at one file per task. Costs: a fifth place
documentation lives — accepted because the enforcement test makes
drift fail the suite, which none of the prose alternatives could
promise, and the skill is the only one of the five written to be
*executed* rather than read about.
