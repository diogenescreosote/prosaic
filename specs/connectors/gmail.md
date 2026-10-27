# Spec: gmail connector

## Purpose

Email with opposing parties, counsel, vendors, and institutions is
evidence, and it should arrive in the matter continuously — as mail
that can be read, re-read, and re-rendered, plus paper a court can
take — rather than being hunted down thread by thread the week before
a filing. The connector captures every thread involving the configured
correspondents into `assets/gmail/`: the raw messages as the record,
and Gmail's print view as the rendering of them.

Capture and presentation are two steps (ADR-0038). Everything the
connector stores is raw; everything a reader looks at is derived from
what is stored, and can be produced again.

## Promises

1. **The raw message is the record.** Every captured message is stored
   exactly as the Gmail API returns it for `format=raw` — RFC 822
   bytes, headers, MIME structure, quoted chains and attachment
   payloads intact — in one mbox per thread at
   `assets/gmail/mbox/<pdf stem>.mbox`. Nothing is summarized,
   stripped, or normalized on the way in.
   *(tested: tests/test_connectors_gmail.py)*
2. **The mbox is append-only and lossless.** mboxrd quoting is exactly
   reversible, so a message read back out of an mbox is byte-identical
   to the one appended; a thread that grows appends only its new
   messages, deduplicated on `Message-ID` (a digest of the bytes for a
   message that has none), so bytes already written are never
   rewritten and an mbox backed up yesterday is a prefix of today's.
   *(tested: tests/test_connectors_gmail.py)*
3. **Rendering is a pure function of (mbox, options).** The print-view
   PDF, the extracted attachments and the `.eml` emission are all
   produced by parsing the stored bytes, with no call to the Gmail API,
   so any thread ever captured can be re-rendered at any time by anyone
   holding the file. `sc mail-render <mbox>` is that step on its own.
   *(tested: tests/test_connectors_gmail.py)*
4. **Court-usable print view, complete by default.** Each thread
   renders as Gmail's print view — sender, recipients, dates and
   subject on each message, attachments listed by name and size — the
   presentation courts and opposing counsel already recognize from
   Gmail printouts. `--quoted show` is the default: the stored PDF
   carries the quoted reply chains, because a record that hides content
   is not one. `--quoted hide` reproduces Gmail's own
   `[Quoted text hidden]` behavior for whoever wants it.
   *(tested: tests/test_connectors_gmail.py)*
5. **Attachments land beside the PDF, extracted from the mail.** Every
   part with a filename whose bytes did not go into the rendered body
   is written to `assets/gmail/attachments/<pdf stem>/<sanitized
   name>`, each with its own `NEW` line — the print view can only list
   an attachment's *name*, and a document whose value is its contents
   is invisible to triage until the file itself lands. Inline images
   actually embedded in the rendering are excluded; a `Content-ID` or
   an inline disposition alone does not make a part inline, because
   mailers stamp both onto genuine documents. Files over 25MB are
   listed and skipped with a `SKIPPED` line. A file already present at
   its target path with the expected size is not rewritten.
   *(tested: tests/test_connectors_gmail.py)*
6. **Criteria are correspondents, not searches.** Configuration is a
   list of addresses and bare domains, each optionally bounded by
   `after:`/`before:` dates — so the corpus is defined by *who* the
   case is about and *when* the relevant period runs, and the same
   config re-run captures new mail with the same meaning.
   *(untested)*
7. **A matter may watch several mailboxes.** `accounts:` lists
   addresses; each has its own OAuth token, and the ledger is keyed by
   account and then by thread id, so the same thread id issued by two
   mailboxes cannot collide. Omitting `accounts:` means one unnamed
   mailbox on the existing token, exactly as before, and the first
   listed account inherits that token — so adding a second mailbox
   costs one authorization and never invalidates the first.
   *(tested: tests/test_connectors_gmail.py)*
8. **Incremental by thread ledger.** `.state/gmail.json` records every
   exported thread by account and Gmail thread id, with the
   `historyId`, message count and message ids it had when exported. A
   routine run does not list the whole history: it lists only threads
   with a message inside a `newer_than:` window sized from the last run
   plus two days of slack (three-day floor), and a full listing runs on
   the first run, on `--full`, or when the last full pass is a week old
   (a full pass is what reconciles a message removed with nothing
   added). Capture is incremental at the message level too: a changed
   thread fetches only the Gmail ids the ledger has not already stored
   in its mbox, so a grown thread costs one fetch, not one per message.
   Together these keep a run at O(recent threads + new messages) rather
   than O(history). A thread whose `historyId` is unchanged is skipped
   from the list stub alone — no metadata fetch, no render, no `NEW` — so a broad domain
   filter does not re-examine the whole history every run. A thread
   whose *message set changed* — it grew, or a message was deleted and
   another threaded in beside it at the same count — is re-exported and
   re-triaged; a thread whose `historyId` moved for a label or
   read-state change only refreshes its ledger entry. An entry recorded
   before message ids were kept falls back to the count comparison
   until its next export or backfill. Drafts are excluded throughout
   (promise 14). *(tested)* Because identity is the thread id rather than the filename,
   triage may move or rename an exported PDF and it will not be
   re-pulled. A matter whose `assets/gmail/` predates the ledger
   absorbs those files on first run instead of re-exporting them. A
   pre-ledger file is absorbed only if no other thread already claims
   its name: two threads never share a filename, because the mbox path
   follows the filename and a shared name would mix two threads into
   one record. The backfill repairs any such sharing it finds (first
   claimant keeps the name, the rest are renamed and rendered afresh,
   the mixed mbox is deleted and each thread recaptured; PDFs are
   rendered one at a time after the concurrent captures, because the
   renderer shares one browser page). A thread Gmail reports as gone is
   marked in the ledger and not retried; its PDF is its record. *(tested)* The
   ledger is written after each successful export, so a crash
   mid-batch never repeats work already done. *(untested)*
9. **Chronological, literate names.** Output is
   `YYYYMMDD_<subject_snake_case>.pdf`, with the thread's mbox and
   attachments directory named from the same stem, so the directory
   reads as a dated correspondence log without opening a file.
   *(untested)*
10. **Backfill is opt-in, quiet, and resumable.** `--backfill-mbox`
    fetches raw mail for ledger entries that have no mbox — threads
    exported before ADR-0038 — and does nothing else: no render, no
    `NEW` line, so a matter's triage is not re-run over PDFs it
    already holds. `--limit N` bounds a run against the API's rate
    limit and the ledger is written after each thread, so the next run
    resumes where the last stopped. *(untested)*
11. **Contract compliance**: `NEW` lines on stdout only, straight to
    its `assets/gmail/` destination (born-digital, no triage routing
    needed), OAuth tokens outside the matter, exit nonzero on failure.
    *(untested)*

12. **Concurrent, bounded fetching.** A thread's raw messages are
   fetched with up to 6 requests in flight, the metadata for threads
   that may need work with up to 8, and a backfill keeps up to 4 threads
   in flight (`--concurrency N` overrides), all under a 60-second
   per-request timeout with retry on timeout, reset, 429 and 5xx. The
   bounds sit well under Gmail's 250-units-per-second per-user quota.
   Ledger writes stay ordered; results keep input order. *(tested)*

13. **The list's edges are watched; the list is never widened.** The
    address list is the only capture criterion (promise 6), and its
    failure mode is silence: a correspondent nobody listed leaves no
    trace in the record, however much they matter. So every run also
    reads the *metadata* of the mailbox owner's own sent messages in
    the same window --- To, Cc, Date, Subject; never a body; capped at
    200 messages --- and writes every recipient the list does not cover
    to `.state/gmail_unlisted.json` (one row per address, newest
    sighting, dropped once the list covers it). The brief prints the
    report; `connectors.gmail.ignore_unlisted` silences addresses and
    domains that are noise, and automated locals (`noreply`,
    `notifications`, `mailer-daemon`, …) and the owner's own mailboxes
    are never reported. Nothing is exported from that check.
    *(tested: tests/test_mail_guard.py)*
14. **A draft is not mail, and nothing about it enters the record**
    (ADR-0049). Every search the connector makes carries `-in:drafts`
    (the thread listing and the sent-mail watch alike), every message
    carrying Gmail's `DRAFT` label (unsent drafts, including scheduled
    sends not yet gone) is dropped before it is fetched and again on
    the fetched message's own labels, and the mbox writer refuses one
    whoever hands it over. A draft is never stored, rendered, counted,
    announced or recorded in the ledger; a thread that is nothing but
    drafts produces no file at all. Ledger entries written by earlier
    versions may still carry `draftCount`/`latestDraftAt`; they are
    tolerated, never read, and dropped when the entry is rewritten.
    An mbox written before this rule that still holds a draft is
    never rendered with it: the thread's drafts' Message-IDs are held
    in memory during an export and excluded. The brief says nothing
    about drafts. The one exception is the user's own explicit
    instruction to look at a particular draft, which no tool here
    performs. *(tested: tests/test_mail_guard.py,
    tests/test_connectors_gmail.py)*
15. **Legacy drafts are found and moved out on request.**
    `pull.js --audit-drafts` (and `sc mail-audit-drafts`) compares the
    mailbox's drafts (`drafts.list` and the `DRAFT` label; metadata and
    Gmail's snippet only) and each captured thread as Gmail holds it now
    (`threads.get` metadata) against the record: a stored message whose
    Message-ID is a draft's; a PDF-only render whose text holds the
    opening words of one of its thread's drafts, or whose thread holds
    nothing but drafts; an mbox no ledger entry names; and a PDF no
    ledger entry names, matched by the filename the draft's own date
    and subject would have produced plus its opening words. Each
    render is reported as DRAFT-ONLY, MIXED, or UNVERIFIED (a stored
    message the Gmail thread no longer has: deleted, or an earlier
    saved version of a draft; or a render with no mbox whose print view
    counts more messages than Gmail now holds, so that it may be the
    only record of deleted mail) with every file that belongs to it ---
    PDF, `.txt`, `_ocr.pdf`, mbox, attachments directory, and their
    `derived/` text, OCR and thread-body files --- every Markdown file
    that mentions it, and copies elsewhere under `assets/`. The report
    names files and Gmail ids, never a draft's subject or words, and
    a report run writes nothing. `--apply` moves each draft-only
    render's files to `.private/gmail_drafts/<stem>/` (paths kept, a
    manifest with the evidence, each file's sha256 and the ledger
    entry) and drops its ledger entry; moves a mixed render's files the
    same way and rebuilds it without its drafts, from its own mbox when
    there is one (every other message byte-identical) or by a fresh
    capture otherwise, announcing the new PDF and attachments with
    `NEW` lines; adds `.private/` to the matter's `.gitignore` first;
    records the drafts' Message-IDs in `.state/gmail_drafts.json` for
    the mail index's guard; and never touches an UNVERIFIED render or
    deletes anything. Markdown that mentions a moved render is
    reported, not edited. *(tested: tests/test_drafts_audit.py)*
16. **A refresh_token is never lost.** Google sends one only at
    consent; a token file without it stops working an hour later and
    every pull fails with `invalid_grant`. The two writers of a token
    file (auth.js after consent, the OAuth client's refresh handler)
    merge into the file as it is on disk at that moment, never into a
    snapshot taken when the run began: empty values never overwrite, a
    `refresh_token` in the file survives any refresh that does not
    bring a new one, a file re-authorized while a run was going is left
    alone, and a consent that returns no `refresh_token` keeps the one
    already saved for that mailbox. Writes are atomic and mode 0600.
    Each file records the mailbox it authorizes (`account`); the
    primary account's own file and `credentials.json` are kept in step
    (a refresh writes both, unless `credentials.json` is recorded as
    another mailbox or holds a separate grant), and the primary reads
    whichever of the two still has a `refresh_token`. A file with none
    is named in a warning. No token value is ever printed.
    *(tested: tests/test_gmail_creds.py)*

## Non-obvious constraints

- **The mbox is deliberately not announced.** The connector contract
  says every file written gets a `NEW` line; the mbox is the exception
  (ADR-0038). It is the source the announced PDF was rendered from,
  not a second document, and announcing it would put two catalog rows
  in the matter for one piece of evidence.
- **A matter should commit the mbox and may ignore the PDF.** The PDFs
  are regenerable and bulky; `assets/gmail/mbox/` is the record and is
  regenerable from nothing the matter holds.
- **Output goes directly to `assets/`, not staging** — a Gmail
  thread's identity and home are unambiguous, so routing judgment
  (the reason staging exists) adds nothing. Triage's job for these
  files is cataloging (a CATALOG.md row per thread), not moving.
- **No OCR, no `.txt` sidecars**: the PDFs are born-digital and
  already searchable; supplementing them would violate the
  no-redundant-copies rule. The mbox is not a redundant copy of the
  PDF — it is what the PDF is made from.
- **Date bounds are per-correspondent, not global**, because
  relevance windows differ — an opposing party's entire history may
  matter while a vendor's is only relevant after the contract date.
- **Two mailboxes holding the same conversation produce two threads,
  two mboxes and two PDFs**, the second collision-suffixed. They are
  two mailboxes' records of it, and merging them would assert that one
  account's copy stands for both.
- **The print view fetches Gmail's logo and file-type icons from
  gstatic**, as Gmail's own print view does. It is the only part of
  rendering that is not local; a render with no network produces the
  same layout with the images missing.
- **The export is only as complete as the accounts and the query.**
  The connector pulls threads *involving* configured addresses from
  the configured mailboxes; it does not attest completeness of
  production. Anything offered as a complete record still needs human
  verification against the mailboxes.
- **A domain criterion is broad by design** (any correspondent at
  the firm); use it for institutions, not for fishing.

## Configuration

```yaml
connectors:
  gmail:
    accounts:                        # optional; one OAuth token each
      - jane@example.com             #   the first inherits the
      - service@example.com          #   pre-accounts token
    addresses:
      - opposing.party@example.com
      - examplefirm.com              # bare domain matches the whole firm
      - address: someone@example.com
        after: 2024/04/01            # Gmail search bounds (optional)
    quoted: show                     # show (default) | hide, in the PDF
    out_dir: assets/gmail            # optional
    ignore_unlisted:                 # never reported as uncaptured
      - newsletter.example
```
