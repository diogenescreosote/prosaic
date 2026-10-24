---
name: phone-logs
description: Extract the call and message history with a given phone number (optionally within a date window), or find where a phrase was texted, from SMS Backup & Restore XML exports into a citable markdown report. Use when someone asks what calls or texts happened with a number, needs a communications timeline for a declaration, searches text messages for words, or hands you calls-*.xml / sms-*.xml phone backups to search.
---

# Extract phone logs for a number

Phones running SMS Backup & Restore drop daily `calls-*.xml` and
`sms-*.xml` files (the sms ones run to gigabytes: never open them
whole, never load them into context). There are two tools. **Use the
matter's store first.**

## 1. The matter's phone store (`sc phone`)

If `matter.yaml` has a `phone:` block, the backups are already indexed
in `derived/phone/messages.sqlite`. Bring it current, then search:

```bash
sc phone ingest <matter>                  # new backups only; seconds on a daily run
sc phone search <matter> --number "(555) 000-1234" --from 2026-04-01 --to 2026-08-22 \
    -o report.md
sc phone search <matter> --text "pick up" --kind sms     # substring, any case
sc phone stats <matter>                   # counts, coverage, backups read
```

- `--number` repeats, in any format. A group MMS matches on any
  participant. `--text` is a substring of the message text, indexed,
  and covers messages only (calls carry no text). `--kind
  sms|mms|call`, `--format json`, and `--limit` narrow the output.
- The report states the store's **coverage** (the date ranges read per
  record kind). Quote it when you report a result, and above all when
  you report an absence. Call logs on a phone keep only months, so
  call coverage usually starts later than message coverage.
- No `phone:` block? Propose one to the human (see prosaic
  `docs/phone-logs.md`). It is configuration, but the source paths are
  theirs to name. Add `derived/phone/` to the matter's `.gitignore`.

## 2. Fallback: stream a backup (`phone_logs.py`)

For a backup the store does not cover (a file someone hands you, or
dates before the store's `since`), use the streaming extractor:

```bash
python3 <prosaic>/triage/phone_logs.py \
    -n "+1 (555) 000-1234" \
    --after 2026-04-01 --before 2026-08-22 \
    -o report.md  /path/to/backups/
```

- **Inputs**: XML files, or a directory (it globs `calls-*.xml` and
  `sms-*.xml`; `--kind calls|sms|both` narrows that). Overlapping
  daily backups are fine, since duplicates collapse. It reads every
  file in full, which takes minutes for a gigabyte backup.
- **`-n` repeats**, in any format; **`--after`/`--before`** are
  inclusive local-time `YYYY-MM-DD` or ISO timestamps.

Both reports open with a machine-extract banner, the query, the
sources and counts. Calls render as a table and messages as quoted
chronological entries with `[attachment: <type> ...]` markers. Media
is never decoded into the report. Promises: `specs/phone-store.md`,
`specs/phone-logs.md`.

## Discipline

- The report is a **machine extract, not evidence**. Verify any line
  against the backup (or the phone) before it enters a filing, and
  keep the banner intact when quoting the report into working notes.
- Sources are originals: leave them where they are, modify nothing.
  Write reports to the matter's working area (or a scratch dir), not
  beside the backups. Never commit the store.
- Absence of a row proves little. Backups cover one device's SMS/MMS
  and cellular calls only (no Signal/WhatsApp/FaceTime, nothing
  deleted before the first backup read). Say so, with the coverage,
  when reporting "no contact found."
- A report naming real parties is case material: it never enters the
  prosaic repo, its tests, or examples.
