# Phone logs

A phone running SMS Backup & Restore (SyncTech) can write a backup of
its messages and call log every day to a synced folder: `sms-<stamp>.xml`
and `calls-<stamp>.xml`. They are the most complete record of a
phone's traffic a matter is likely to have. They are also awkward. A
full `sms-*.xml` runs past a gigabyte, nearly all of it inline base64
attachments, and a calls backup holds only the months the phone's call
log still keeps.

prosaic reads them two ways.

| Tool | Use it for |
|---|---|
| `sc phone` (the store) | Everyday questions over a matter's backups: who, when, what was said. Answers in milliseconds. |
| `triage/phone_logs.py` | A one-off extract from a backup the store does not cover, such as a file someone hands you. |

Both produce reports that open with a machine-extract banner. A report is
for drafting and analysis. Verify any line against the backup or the
phone before it goes into a filing.

## The store

### Configure

In `matter.yaml`:

```yaml
phone:
  sources:
    - "~/Drive/sms-*.xml"            # globs; ~ expands; relative = the matter
    - "~/Drive/calls-*.xml"
  since: "2024-05-01"                # date of relevance: nothing older is stored
  db: derived/phone/messages.sqlite  # the default; keep derived/phone/ gitignored
  # overlap_days: 3                  # how far back each new read starts
```

Add `derived/phone/` to the matter's `.gitignore` (new matters have
it). The store is derived (ADR-0048). Delete it and the next ingest
rebuilds it from the backups, which are never modified.

### Ingest

```sh
sc phone ingest <matter>        # new backups only; prints one line per file
sc phone ingest <matter> --exhaustive   # read every new file in full
```

Each file gets one line on stderr: its status, the rows it added, the
bytes it read and how long it took. Nothing from any message is
printed.

How it stays cheap:

- **A file already ingested with the same size and mtime is never
  opened again.**
- **Calls backups (anything under 64 MB) are read whole.** They are
  small, and reading every one keeps calls a later backup has dropped.
- **Large backups are read only where the store lacks coverage.** A
  backup is a run of `sms` records followed by a run of `mms` records,
  each in date order. The store records which date ranges it has read
  in full, per record kind. A new backup is read only across the
  ranges still missing, starting `overlap_days` early to catch late
  arrivals, and those ranges are reached by bisecting byte offsets.
  A daily run reads the new file's last few days and nothing else. A
  backup found out of order is read in full instead.
- **On first population, the newest backup goes first.** If its
  history does not reach back to `since`, older backups are chosen by
  a greedy interval cover over their first records and backup dates.
  The rest are marked `covered` without being opened.

Attachments are never stored. Each MMS part keeps its content type,
file name, decoded size and sha256, which is enough to match a cited
attachment to the original. Text parts become the message body.
RCS messages appear in the backup as `sms` or `mms` records, depending
on the phone's messaging app, and are stored as the backup gives them.

### Search

```sh
sc phone search <matter> --number "(555) 000-1234" --from 2026-04-01 --to 2026-06-30
sc phone search <matter> --text "pick up" --kind sms
sc phone search <matter> --number 5550001234 --format json -o extract.json
sc phone stats <matter>
```

- `--text`: a case-insensitive substring of the body or subject,
  indexed through FTS5 trigram, so mid-word matches work. Queries
  under three characters fall back to a scan. Text searches cover
  messages only, since calls carry no text.
- `--number`: any format, repeatable. Matching uses the last ten
  digits, or the exact digits for short codes. A group MMS matches on
  any participant.
- `--from` / `--to`: inclusive local dates.
- `--kind sms|mms|call`, `--limit N`, `--format md|json`, `-o FILE`.

The Markdown report states the query, the store's `since`, the date
coverage per record kind, and how many backups were read. Calls come
as a table and messages as quoted entries with attachment markers.
`sc phone stats` lists counts, spans, coverage, and each backup the
store read, with its bytes and time.

### What absence means

A search that finds nothing has searched one phone's SMS, MMS and
cellular call log, within the coverage the report prints. It has not
searched Signal, WhatsApp, FaceTime, or anything deleted before the
first backup that was read. The store is cumulative: something deleted
from the phone after a backup was ingested stays in the store.

## The one-off extractor

```sh
python3 <prosaic>/triage/phone_logs.py -n "+1 555 000 1234" \
    --after 2026-04-01 --before 2026-08-22 -o report.md /path/to/backups/
```

It streams the given files and reads them in full every time.
Contracts: [specs/phone-logs.md](../specs/phone-logs.md) and
[specs/phone-store.md](../specs/phone-store.md).
