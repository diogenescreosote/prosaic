# Upgrading an existing matter

Every convention change ships with a migration, and one command runs
all of them: `sc upgrade <matter>`. It is idempotent, deterministic, and
ends with the list of steps that still need a human or an agent.
`--dry-run` prints what would happen and changes nothing. The canonical
target is a live matter that predates all of this.

```
sc upgrade . --dry-run
sc upgrade .
```

| Change | ADR | What `sc upgrade` does | What remains for a person or an agent |
|---|---|---|---|
| Routine commands and session brief | 0040 | installs or refreshes `.claude/settings.json` and the seven skills, path resolved; `settings.local.json` untouched | commit `config(harness)`; start a new session to see the brief |
| Text coverage | 0041 | runs `sc text ensure`: OCR copies and page-marked text for every document | photo pages need a human description; audio needs the local STT pipeline; commit `triage(text)` |
| Derived tree | 0042 | `sc text migrate`: moves tool-written siblings under `derived/`; adds `derived/ocr/` to `.gitignore` | agent-made `_ocr.pdf` siblings that INDEX rows name move only with `--include-legacy-ocr` |
| Knowledge vault | 0043 | preserves the single file under `knowledge/_migration/`, splits it into staging notes, makes `KNOWLEDGE.md` the index, adds `.obsidian/` to `.gitignore` | the `migrate-knowledge` skill (agent, Fable) folds staging into notes; a human reviews in Obsidian and removes staging; commit `record(knowledge)` |
| Ignore rules | 0042, 0043 | adds `derived/ocr/`, `.obsidian/`, `.state/` | |
| Scheduled sync | 0041 | checks a launchd job exists; the script is read from the checkout at run time | `sc schedule .` if none is installed |

Run it again after every deployment merge; a step already done reports
itself complete. Commit each step's result under its own type, by
explicit path, and never while another session is committing in the
same matter.
