---
name: new-matter
description: Scaffold a new matter directory - layout, git repo, commit hooks, agent contracts, backup upstream. Use when starting work on a new case or bringing an existing pile of documents under prosaic's conventions.
---

# Scaffold a matter

1. `<prosaic>/cli/sc init <dir> --git` — creates the layout
   (`specs/matter.md`), copies the templates (AGENTS.md contract,
   KNOWLEDGE/TODO/QUESTIONS, envelopes.yaml, matter.yaml), links the
   Makefile, initializes git, installs the commit hooks. Rerunnable:
   existing files are kept unless `--force`.
2. **Edit `matter.yaml`**: caption, court, parties, connectors,
   backup. This is configuration the human owns — draft it, then ask.
3. **Workspace contract**: the matter inherits shared conventions
   from `../AGENTS.md` (symlink to
   `<prosaic>/templates/workspace/AGENTS.md`). If the parent
   directory has no such file, create the symlink — otherwise none of
   the shared rules are in force.
4. **Backup upstream** (ADR-0016): every matter has one;
   `<prosaic>/cli/sc backup init .` sets up the default local bare
   repo, `matter.yaml` can name a private GitHub repo instead.
   Verify with `sc backup push .`.
5. **Fill the contract's blanks**: the matter AGENTS.md "Who is who"
   section (parties, counsel, court) and quirks. Getting names right
   here prevents the most damaging cheap mistake available.
6. First commit: `config(matter): scaffold <name>` — the hooks
   enforce the commit shape from the start.

Existing documents come in through `inbox/` and the
[triage-inbox](../triage-inbox/SKILL.md) skill, never dropped
directly into `assets/`.

References: `specs/matter.md`, `docs/matter-layout.md`,
`docs/backup.md`, `docs/commits.md`.
