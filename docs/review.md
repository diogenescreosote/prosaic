# Preflight review

Four optional checks a drafter runs before signing, each a slash command
and a skill, none of them a gate (ADR-0045). Reports are derived
artifacts under `derived/review/<target>/`, tied to the exact revision
they reviewed.

| Command | Persona | Model | Reads |
|---|---|---|---|
| `/citecheck <env>` | the cite checker | Opus | the extractor's table, the sources, `knowledge/authorities.yaml` |
| `/clerkreview <env>` | filing and calendar clerk | Opus | sources, built PDFs, `*.fields.json` |
| `/judgereview <env>` | the skeptical bench | Opus | sources, the record via `sc find` |
| `/oppo <env>` | opposing counsel | Fable | sources, the record, `knowledge/topics/opposing-counsel-profile.md` |
| `/preflight <env>` | collator | Sonnet | the four current reports |

## Plumbing

```
sc review paths <env|src/x.md>        # sources, built outputs, profile, current and STALE reports
sc review cites <env|src/x.md>        # deterministic citation table with authority-cache status
sc review report <env> --check NAME   # create the report file with its hash header; prints the path
sc review status [<env>] [--tidy]     # current vs stale for every report; --tidy moves stale to superseded/
```

## Staleness

A report's header records the sha256 of every source it reviewed and the
combined hash, which also appears in the filename. When a source
changes, `sc review status` marks the report stale and rewrites its
status line; `--tidy` moves it into `superseded/`. Every skill runs
`sc review paths` first and is told which reports are stale, so no
persona quotes a critique of a revision that no longer exists.
`/preflight` tidies before collating.

## The authority cache

`knowledge/authorities.yaml`:

```yaml
authorities:
  "code civ. proc., § 1987.1":
    status: verified            # verified | bad | superseded
    proposition: court may direct compliance with a subpoena on terms it declares
    checked: 2026-09-07
    source: official code, accessed 2026-09-07
```

Keys are the normalized cite (`sc review cites` prints them). The check
treats a cached cite as existing and still reads the proposition against
the draft's use.

## Running a persona on another model

Skills route to Claude models. To read a draft with a different vendor's
mind, run the batch form: `sc flow run flows/draft-review.yaml` with
`PROSAIC_AGENT_CMD` pointing at that vendor's agent CLI (see
`docs/scheduling.md` for roles). The report shape is the same.
