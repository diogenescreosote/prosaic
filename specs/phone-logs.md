# Spec: phone log extraction

## Purpose

Phones export their complete call and message history as SMS Backup &
Restore XML (`calls-*.xml`, `sms-*.xml`) — files that are unreadable
in bulk (a full message backup runs to gigabytes of inline base64
attachments) and useless in a filing until the traffic with one
counterpart is isolated. `triage/phone_logs.py` exists so that a
clerk — human or agent — can answer "what contact was there with this
number, in this window?" with a single command, and get back a
markdown report another session can quote, count, and cite from
without ever opening the raw XML.

## Promises

1. **Streaming, bounded memory.** Backups are parsed incrementally;
   a multi-gigabyte `sms-*.xml` is processed without loading the
   document into memory. *(tested: test_phone_logs.py)*
2. **Number matching is format-blind.** `+17075551234`,
   `(707) 555-1234`, and `1-707-555-1234` all name the same line:
   comparison is on digits, last-ten for full-length numbers, exact
   for short codes. A group MMS matches if the target number is any
   participant. *(tested: test_phone_logs.py)*
3. **Date filtering is inclusive and local.** `--after`/`--before`
   take `YYYY-MM-DD` (or a full ISO timestamp) and bound the report
   inclusively, interpreted in the machine's local timezone — the
   same clock the backup's `readable_date` values show. *(tested:
   test_phone_logs.py)*
4. **Duplicates collapse.** Daily full backups overlap almost
   entirely; the same call or message appearing in any number of
   input files yields one report row. *(tested: test_phone_logs.py)*
5. **Attachments are noted, never extracted.** MMS media appears as
   a `[attachment: <mime-type>]` marker. The report stays text, and
   no base64 payload is decoded or written anywhere. *(tested:
   test_phone_logs.py)*
6. **The report declares its own provenance and limits.** Every
   report opens with a machine-extract banner, the query (numbers,
   window), the source files with their backup dates, and
   post-deduplication counts — so a reader knows what was searched
   and what to verify before citing. *(tested: test_phone_logs.py)*
7. **Sources are read-only.** Input XML is never modified; output
   goes to stdout or the `-o` path only.

## Non-obvious constraints

- **The report is evidence-adjacent, not evidence.** It is a machine
  extract for drafting and analysis; anything quoted in a filing is
  verified against the backup (or the phone) by a human first. The
  banner exists to make skipping that step conspicuous.
- **Direction codes are the phone's, decoded conservatively.** Call
  `type` and SMS `type`/`msg_box` values outside the documented maps
  render as `type=N` rather than a guessed label — a mislabeled
  direction in a custody or harassment timeline is worse than an
  honest unknown.
- **This parses one format on purpose.** SMS Backup & Restore XML is
  the format the running deployments actually produce. Carrier CSVs,
  iPhone extractions, and Google Voice takeouts are different tools
  for a different day; grafting them here would blur the promises
  above.
