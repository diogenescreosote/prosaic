# ADR-0040: Routine operations are harness commands, not deliberation

**Status:** Accepted (September 6, 2026)

## Context

A month of session transcripts from a live deployment showed where the
time goes. Every routine request --- build this envelope, open the
PDFs, commit, report stale output --- was a prose instruction to a
frontier model working inside a session whose context had grown to
several hundred thousand tokens. The model re-read the skill, decided
how to run the CLI, ran it, read the result, and decided what to say.
A bare rebuild took forty seconds at the median; when the build warned,
the model fixed the source on its own initiative and the turn ran for
minutes. Median context per call was 380k tokens, and per-call latency
roughly doubled between a 100k and a 600k context. The cost was not the
model; it was re-reading a huge prefix to do something a shell already
knew how to do.

The system already has the deterministic surface: `sc build`,
`sc build-doc`, `sc clean`, `sc list`, `sc form`. What it lacked was a
way for the harness to reach that surface without a round of thought,
and a way to start a session with the two-minute orientation instead of
the whole knowledge file.

ADR-0020 made `cli/agent-run` the one seam to a headless agent and asked
that harness-specific files be labeled as such. ADR-0021 and ADR-0029
made skills the home of agent-facing procedure. ADR-0039 made `sc` the
only build interface.

## Decision

1. **Routine operations ship as harness commands** in the matter
   template, under `templates/matter/.claude/skills/`: `build`,
   `build-doc`, `open`, `clean`, `status`, `commit`, `find`. Each runs
   the CLI through the harness's inline-execution syntax before the
   model sees anything, then relays the result. The model's job is to
   read output, not to decide how to obtain it.
2. **A relay command runs on the cheapest adequate model at low
   effort.** Build, open, clean and status declare a small model;
   commit and find declare a mid model because they write a message or
   read hits. Drafting, triage and integration are untouched by this
   ADR and stay on the strongest model available.
3. **A relay command never edits a source.** A build warning that needs
   a source edit is reported with file and line and stopped on; the
   edit is a separate, visible decision. This is what keeps "rebuild"
   from silently becoming "rewrite".
4. **Sessions start from a brief, not from the knowledge file.** A
   `SessionStart` hook prints `sc brief`, a deterministic page: case,
   envelopes, dates from the knowledge file's calendar headings, the
   top of TODO, recent docket commits, sync and inbox state, and the
   routine commands. The knowledge file is read by section, on demand.
5. **The bundle is prosaic's, installed by `sc init` and refreshed by
   `sc harness install`.** The checkout path is resolved at install
   time from a placeholder, because these files run shell commands. A
   matter customizes through `.claude/settings.local.json` and skills
   under other names; the bundle's files are overwritten on refresh.
6. **The bundle is harness-specific and says so.** It targets the
   Claude Code skill and hook format. Another harness gets its own
   bundle directory; the deterministic commands they wrap (`sc brief`,
   `sc open`, `sc find`) are harness-neutral and live in `cli/sc`.

## Consequences

- A routine turn costs one short call on a small model with a small
  context, or none. The measured tail --- minutes spent fixing sources
  under a "rebuild" prompt --- becomes a request the user sees and
  approves.
- `sc brief` gives every session the same orientation; a session that
  needs more reads the section it needs. Loading a whole knowledge file
  into context is now a choice, not the default.
- `sc find` is the first tier of record search: ripgrep over every
  text file and sidecar, and an explicit list of PDFs that have no text
  layer and were therefore not searched. "Not in the record" is only
  sayable after that list is empty or accounted for. The knowledge
  graph and entity index that make the later tiers cheap are a
  separate decision.
- The per-command `model:` values are a starting point, chosen by the
  measured task shape, and are expected to be tuned per deployment.
- Nothing here changes `agent-run` or the flow runner; batch agent work
  keeps its one seam.
