# 0048 — The phone message store is a derived index, not a record

**Status:** accepted (2026-10)

## Context
SMS Backup & Restore writes a full `sms-*.xml` every day, and a full
one runs past a gigabyte: the messages themselves are a few megabytes
and the rest is inline base64 attachments. `triage/phone_logs.py`
streams a backup per question. Over a synced drive, where an uncached
region reads at a few megabytes a second, each question costs minutes,
and a deployment that keeps months of daily backups pays it again for
every search.

ADR-0001 rejected a SQLite catalog of the matter because it would be a
second source of truth that drifts from disk. That reasoning governs
anything a person maintains. It does not reach an index that no person
edits, that is rebuilt from originals that never change, and whose
loss costs nothing but a rerun.

## Decision
Each matter may keep one SQLite file of its phone traffic
(`derived/phone/messages.sqlite` by default, gitignored), configured
by a `phone:` block in matter.yaml and maintained by `sc phone ingest`.
It is an index under ADR-0042: derived, never edited by hand, never
cited. The backups stay the record; a report from the store says so in
its banner and names the coverage it was drawn from.

Ingest is incremental on two levels. A backup already ingested with
the same size and mtime is never opened again. Within a new backup, the
store reads only the date intervals that no earlier backup has covered,
and reaches them by bisecting byte offsets. That works because a backup
is a run of `sms` records then a run of `mms` records (or one run of
`call` records), each in ascending date order, and because `<` cannot
occur inside an attribute value or base64, so a record's start tag can
be found from any offset. A backup that turns out not to be ordered is
read in full. Files under 64 MB (calls backups) are always read whole,
which also keeps entries that a later backup no longer carries.

Attachment bytes are never stored: each part keeps its content type,
name, decoded size and sha256, so a cited attachment can still be
matched to its original.

## Consequences
After the first population a daily run reads the tail of one new file,
seconds instead of minutes, and a search takes milliseconds. Substring
search is indexed (FTS5 `trigram`, falling back to `unicode61` word
search plus `LIKE` where SQLite predates it).

The store is cumulative: a message deleted from the phone stays in it
once ingested. That is the point for evidence, and it means the store
can hold what no current backup does. The reports say which backups
were read.

What is given up: the bisection reads each new large backup only where
coverage is missing, so a message whose date falls inside covered
months but which appears only in a later backup is missed unless it
falls within the overlap margin (three days by default).
`--exhaustive` reads every new file in full when that matters.
Alternatives: a cache of `phone_logs.py` results (rejected: keyed on
queries, so no new question benefits); copying backups to local disk
(rejected: gigabytes a day, and the parse remains).
