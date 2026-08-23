---
name: phone-logs
description: Extract the call and message history with a given phone number (optionally within a date window) from SMS Backup & Restore XML exports into a citable markdown report. Use when someone asks what calls or texts happened with a number, needs a communications timeline for a declaration, or hands you calls-*.xml / sms-*.xml phone backups to search.
---

# Extract phone logs for a number

Phones running SMS Backup & Restore drop daily `calls-*.xml` and
`sms-*.xml` files (the sms ones run to gigabytes — never open them
whole, never load them into context). The extractor streams them,
filters to the number(s) you name, de-duplicates across overlapping
daily backups, and writes one chronological markdown report:

```bash
python3 <prosaic>/triage/phone_logs.py \
    -n "+1 (555) 000-1234" \
    --after 2026-04-01 --before 2026-08-22 \
    -o report.md  /path/to/backups/
```

- **Inputs**: XML files, or a directory (it globs `calls-*.xml` and
  `sms-*.xml`; `--kind calls|sms|both` narrows that). Passing every
  overlapping daily backup is fine and normal — duplicates collapse.
- **`-n` repeats** for several numbers in one report; any format
  (matching is on digits). Group MMS match if the number is any
  participant.
- **`--after`/`--before`** are inclusive, local-time, `YYYY-MM-DD`
  or full ISO timestamps.
- **The freshest backups suffice** when they are `type="full"` (see
  the root element): each contains the phone's whole history, so one
  calls file + one sms file is usually the complete record.

The report opens with a machine-extract banner, the query, the source
files, and de-duplicated counts; calls render as a table, messages as
quoted chronological entries with `[attachment: <type>]` markers
(media is never decoded). Promises and format details:
`specs/phone-logs.md`.

## Discipline

- The report is a **machine extract, not evidence**. Verify any line
  against the backup (or the phone) before it enters a filing, and
  keep the banner intact when quoting the report into working notes.
- Sources are originals: leave them where they are, modify nothing.
  Write reports to the matter's working area (or a scratch dir), not
  beside the backups.
- Absence of a row proves little — backups cover one device's SMS/MMS
  and cellular calls only (no Signal/WhatsApp/FaceTime, no deleted-
  before-backup material). Say so when reporting "no contact found."
- A report naming real parties is case material: it never enters the
  prosaic repo, its tests, or examples.
