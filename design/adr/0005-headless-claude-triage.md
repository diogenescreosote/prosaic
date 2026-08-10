# 0005 — AI triage as a headless Claude Code session

**Status:** accepted (2026-08)

## Context
Folding new evidence into catalogs/knowledge requires reading
documents and editing files under conventions — agent work. The
project already assumes Claude Code for interactive use; unattended
runs can't answer permission prompts.

## Decision
Triage is one `claude -p <prompt> --dangerously-skip-permissions`
invocation per sync, run *inside the matter directory* so the matter's
CLAUDE.md contract binds it. The prompt is a versioned template file,
not code. Risk is bounded by the conservative-clerk rules, the narrow
worklist (only files connectors reported NEW), and git review of every
change.

## Consequences
The full conventions apply to automation for free; behavior is tunable
by editing Markdown. Costs: skipped-permissions trust (mitigated as
above) and single-harness coupling — accepted honestly; the seam is
one CLI call, documented for substitution, with no speculative
abstraction layer built (tested is better than portable-in-theory).
