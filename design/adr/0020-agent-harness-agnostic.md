# 0020 — One agent-CLI seam; contracts named AGENTS.md

**Status:** accepted (2026-08)

## Context
Three places invoked the `claude` CLI by name: the sync triage pass,
the AI test judge, and the availability probe that skips `-m ai`
tests. The agent contracts were files named CLAUDE.md. ADR-0005
accepted that coupling honestly ("the seam is one CLI call,
documented for substitution") rather than building a speculative
abstraction. The substitution is no longer speculative: contributors
and users run other harnesses (Codex, Gemini CLI), and prosaic's
conventions are harness-independent facts about the work, not about
any vendor.

## Decision
1. **`cli/agent-run` is the only place an agent CLI is named.** It
   reads a prompt on stdin, dispatches to the first of claude / codex
   / gemini found on PATH (forced with `PROSAIC_AGENT_CLI`; fully
   custom via `PROSAIC_AGENT_CMD`), and normalizes the three flags the
   callers need: `--check` (is any agent available), `--dir` (grant a
   read directory), `--yolo` (skip permission prompts, for the triage
   pass ADR-0005 already bounded). Each provider's incantation is one
   function; adding a provider is one case branch.
2. **Contracts are `AGENTS.md`.** The development contract, the
   workspace contract, and the matter contract live in AGENTS.md — the
   name the broadest set of harnesses reads. Each keeps a CLAUDE.md
   beside it that is a pointer (an `@AGENTS.md` import), so
   Claude Code loads the same rules with no duplication. Triage
   prompts refer to "the matter's agent contract" and tolerate the
   legacy name in existing matters.
3. **Harness-specific machinery stays, labeled as such.** The
   `.claude/agents/tester.md` subagent definition is Claude Code's
   implementation of the tester role that AGENTS.md defines
   role-first; another harness implements the role its own way or
   runs the tiers inline.

## Consequences
Provider drift lands in one file (a CLI renames a flag: one-line
fix). The dependency manifest declares all three CLIs as optional
alternatives, `required: false`; `sc deps` reports them, and no image
carries any of them. Costs: agent-run is bash, so Windows remains
out of scope (already true repo-wide), and the `--yolo` trust
decision is now visible in one script rather than buried in a
sync script — which is where it belongs.

Amends ADR-0005 (the triage invocation now goes through agent-run)
and the "single-harness coupling" consequence recorded there.
