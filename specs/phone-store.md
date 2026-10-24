# Spec: the phone message store

## Purpose

A matter that keeps a phone's daily SMS Backup & Restore files needs
to ask, many times a day, "what passed between this phone and that
number, and when?" and "where did anyone write this phrase?". Reading
a gigabyte-scale backup per question (`phone_logs.py`, see
[phone-logs.md](phone-logs.md)) answers correctly but slowly.
`triage/phone_store.py` (`sc phone`) ingests the backups once, and
then only what is new, into one SQLite file per matter, so that every
later question is answered in milliseconds with the same provenance
discipline. Decision record: ADR-0048.

## Promises

1. **One store per matter, configured in matter.yaml.** `phone:` names
   `sources` (globs; `~` expands; relative paths resolve against the
   matter), `since` (the date of relevance) and `db` (default
   `derived/phone/messages.sqlite`). *(tested: test_phone_store.py)*
2. **Nothing older than `since` is stored.** Records before it are
   skipped at ingest. Moving `since` later prunes what is now older.
   Moving it earlier makes backups that were judged unneeded eligible
   again. *(tested: test_phone_store.py)*
3. **Overlapping backups never duplicate.** Every message and call has
   a dedup key (kind, normalized counterpart(s), date, type, text, and
   for MMS the shape of its parts) under a UNIQUE index. Ingesting the
   same history from any number of backups yields one row per record.
   *(tested: test_phone_store.py)*
4. **Ingest is incremental.** A source file already ingested with the
   same size and mtime is not opened. A new large backup is read only
   across the date intervals the store's coverage lacks (each started a
   few days early), reached by bisection, so a daily run reads that
   backup's new tail. A backup found out of date order is reread in
   full. Small files are always read whole. *(tested:
   test_phone_store.py)*
5. **Attachment bytes are never stored.** MMS text parts become the
   message body; every other part keeps content type, name, decoded
   size and sha256. *(tested: test_phone_store.py)*
6. **Text search is substring search, indexed.** `--text` matches any
   substring of a message body or subject, case-insensitively, through
   an FTS5 `trigram` index kept in sync by triggers. Without trigram
   support (SQLite before 3.34) the store builds a `unicode61` index
   and substring search falls back to a scan. *(tested:
   test_phone_store.py)*
7. **Number matching is format-blind**, as in phone-logs.md: digits
   only, the last ten for full-length numbers, exact for short codes,
   lowercased text for alphanumeric sender IDs. A group MMS matches on
   any participant (from, to, or cc). *(tested: test_phone_store.py)*
8. **Reports declare their provenance.** A search report opens with
   the machine-extract banner, the query, the store's `since`, its
   coverage by record kind, and the number of backups read. *(tested:
   test_phone_store.py)*
9. **Sources are read-only.** Backups are opened for reading and
   never modified. *(tested: test_phone_store.py)*

## Non-obvious constraints

- **The store is derived.** It is never edited by hand and never cited.
  Delete it and `sc phone ingest` rebuilds it. A line from a report is
  verified against the backup or the phone before it enters a filing.
- **The store is cumulative.** A message deleted from the phone stays
  once ingested. Coverage records which date ranges were read from
  which backup, so "no rows" is reported together with what was
  searched, never as proof that nothing happened.
- **The bisection depends on the backup's order**: a run of each
  record tag, ascending by date within it. That was verified on real
  backups (October 2026), it is checked on every segment read, and a
  violation falls back to a full read rather than trusting the order.
- **No content in logs.** Ingest prints file names, counts, byte
  totals and timings, and nothing from a message.
