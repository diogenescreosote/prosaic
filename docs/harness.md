# The coding-agent harness bundle

*Harness-specific: this document and `templates/matter/.claude` target
Claude Code's skill and hook format (ADR-0020 asks that such files say
so). The commands they wrap --- `sc brief`, `sc open`, `sc find`,
`sc build`, `sc clean` --- are plain CLI and work from any agent.*

## Why it exists

ADR-0039 records the measurement: routine requests were costing a
frontier model a round of thought inside a several-hundred-thousand-
token session, and "rebuild" often turned into unrequested source
edits. The bundle makes each routine operation a slash command that
runs the CLI *before* the model sees the prompt and then relays the
output on a small model at low effort.

## What is installed

`sc init` writes it; `sc harness install <matter>` refreshes it.

```
.claude/settings.json          SessionStart hook -> sc brief
.claude/skills/build/          /build <envelope> [--variant V] [--final]
.claude/skills/build-doc/      /build-doc src/<source>.md
.claude/skills/open/           /open <envelope|path> ...
.claude/skills/clean/          /clean   (report only; --apply is yours)
.claude/skills/status/         /status  (brief + git status + stale report)
.claude/skills/commit/         /commit <type(scope): subject> [-- paths]
.claude/skills/find/           /find <term> ...
```

Each SKILL.md has the checkout path baked in at install time (the
template carries `@@PROSAIC@@`), so moving the prosaic checkout means
running `sc harness install` again.

## How a relay command works

```markdown
---
name: build
model: claude-haiku-4-5
effort: low
allowed-tools: Bash("<prosaic>/cli/sc" build *)
---
## Build output
!`"<prosaic>/cli/sc" build $ARGUMENTS 2>&1; echo "[exit $?]"`
## Instructions
Relay the output verbatim. Do not edit any source. ...
```

The `` !`…` `` line executes when the command is invoked and its output
replaces the line; the model reads a finished result. The trailing
`echo "[exit $?]"` keeps a failing build from aborting the skill so the
failure is relayed rather than swallowed.

## Model choice

| Command | Model | Why |
|---|---|---|
| build, build-doc, open, clean, status | `claude-haiku-4-5`, effort low | pure relay of CLI output |
| commit | `claude-sonnet-5`, effort medium | writes a commit body in the matter convention |
| find | `claude-sonnet-5`, effort medium | reads hits, runs variants, OCRs unsearched PDFs |

Drafting, triage and integration of new documents are not routine and
are not in this bundle; they stay on the strongest model available.
Tune the `model:` lines per deployment; they are a starting point.

## The session brief

`sc brief .` prints: case name, number, court and role; envelopes;
lines under any KNOWLEDGE.md heading that reads like a calendar
(hearing, key dates, deadline, upcoming); the top eight TODO items and
the QUESTIONS count; the last five `docket` commits and the last three
commits; last sync age, connectors, inbox count, working-tree size,
KNOWLEDGE.md length; and the routine commands. It is deterministic and
takes well under a second. The hook fires on `startup`, `resume`,
`clear` and `compact`.

Habit that goes with it: one session per task. The month of transcripts
that motivated this had twenty sessions running for days carrying four
fifths of all calls.

## Record search: `/find`

`sc find` is tier one of the three-tier search (explicit graph, ripgrep,
cheap reader) described in the v2 proposal. It greps every `.md`,
`.txt`, `.yaml`, `.json`, `.csv`, `.srt`, `.eml` and `.html` under the
matter except `out/`, `.state/`, `.git/`, `.flow/`, and lists every PDF
that has neither a `.txt` sidecar nor an `_ocr` sibling as UNSEARCHED.
The `/find` skill then makes a Sonnet-class reader open the hits,
search name variants and OCR misspellings, OCR-supplement short
unsearched lists, and say "not in the record" only after all of that,
with the searched scope stated.

## Customizing without forking

- Per-matter permission and hook additions go in
  `.claude/settings.local.json`, which the bundle never writes.
- A matter's own commands go under other skill names; the seven bundle
  names are overwritten on refresh.
- To disable the brief for one matter, remove the `SessionStart` entry
  in `.claude/settings.json` after install; it will come back on the
  next `sc harness install`, so prefer a local override.
