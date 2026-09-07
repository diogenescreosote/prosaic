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

## `/judgereview` sees only what the court sees

The bench persona reads this filing, its exhibits and the filed record
under `pleadings/`, and nothing else: no knowledge notes, memos, TODO,
assets or discovery. `sc find --scope pleadings <term>` restricts a
search to the filed record for the same reason.

## `/secondopinion`: a different mind, then integration

`/secondopinion <envelope> -- <one paragraph on what the draft must
achieve>` sends the draft and the brief to the `second-opinion` role,
normally another vendor's model, through `sc review second-opinion`,
which writes the raw numbered suggestions as a report. The drafting
model then weighs every suggestion against the sources, the record and
the vault and writes an integration report in three lists: accepted
(with the exact before/after edit and its source), rejected (with the
reason), and needs your input (as a question). It applies nothing until
you say apply.

The role is configured in `matter.yaml`:

```yaml
agent:
  roles:
    second-opinion:
      cmd: <prosaic>/sync/second_opinion_openai.sh   # any stdin-to-stdout command works
      credential: prosaic.openai                     # Keychain item, exported as OPENAI_API_KEY
      model: gpt-5                                   # exported as AGENT_RUN_MODEL
```

The bundled script posts to any OpenAI-compatible endpoint
(`OPENAI_BASE_URL`), local servers included. The key lives in Keychain
(`security add-generic-password -a "$USER" -s prosaic.openai -w`), never
in a file. Whether a given draft may leave the machine is the matter's
decision.

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
