# ADR-0038: Raw mail is the record; the print view is a rendering of it

**Status:** Accepted (September 6, 2026)

## Context

The gmail connector's job is to bring correspondence into a matter as
evidence. Since it was written it has done that by fetching a thread
through the API and rendering an imitation of Gmail's print view to
`assets/gmail/<date>_<subject>.pdf`. The PDF was the only thing kept.

Two things went wrong with that, and they have the same root.

**The rendering hides content.** Gmail's print view collapses a reply
chain to `[Quoted text hidden]`, and the renderer reproduced that
faithfully — enough heuristics to recognize six mailers' quoting
conventions and replace each with the marker. For a person reading
their own mail that is a courtesy. For a record it is the opposite of
one: the exported PDF asserts that a message said less than it said.
The heuristics also mis-fire, which is how a run of fixes went — a
forward whose entire body lived inside a `gmail_quote` div came out
empty, and genuine attachments carrying a `Content-ID` were dropped as
inline images. Each fix was correct and each was invisible until
someone happened to open the right file.

**The rendering could not be corrected after the fact.** This is the
part that matters. Every one of those fixes improved the code for
messages captured *after* it; the threads already exported kept
whatever the old heuristics did to them, because the material the
renderer consumed — the API's `payload` tree, the attachment bodies,
the quoted text it decided to drop — was never written down. Re-running
the connector does not re-export a thread whose `historyId` has not
moved, and re-fetching years of mail to repair a rendering bug is not a
thing anyone will do. A defect in a presentation layer had become
permanent damage to the record.

Behind both: **the artifact being kept was a rendering, and a rendering
is a lossy, opinionated, version-dependent function of something else.**
The something else was thrown away.

A second, smaller problem arrived at the same time. One OAuth token
means one mailbox, and a person with two accounts — the second one
carrying the aliases used for service — has correspondence the
connector structurally cannot see. A message sent from the second
account was simply never captured, and nothing reported its absence.

## Decision

1. **The canonical record is the raw message, stored verbatim.** The
   connector fetches each message with the Gmail API's `format=raw`,
   base64url-decodes it, and stores those RFC 822 bytes — headers,
   MIME structure, quoted chains, attachment payloads, signatures,
   all of it. That is the artifact the matter keeps. Nothing is
   summarized, stripped, or normalized on the way in.

2. **One mbox per thread, in mboxrd, at
   `assets/gmail/mbox/<pdf stem>.mbox`.** The alternatives were a
   single matter-level mbox and one `.eml` per message plus an index.

   Per-thread wins on three counts. A thread is the unit the rest of
   the system already works in — one PDF, one attachments directory,
   one ledger entry, one catalog row — so a per-thread file needs no
   index to say which messages belong together, and the renderer's
   input is a whole file rather than a range inside one. It keeps
   writes local: a thread that grows appends to its own small file,
   where a matter-level mbox is rewritten or appended under a lock and
   corrupts as a unit. And it survives triage's habits — a thread can
   be moved, copied to an expert, or attached to an email as one file.

   Against `.eml`-per-message: a directory of a thousand files with an
   index is a format we would have to define, maintain, and explain,
   and the index is exactly the thing that goes stale. mbox is a
   format every mail client on every platform already opens. The
   `.eml` view is not lost — `--eml n` writes any stored message out as
   one, byte-for-byte, because an `.eml` file *is* an RFC 822 message
   and emitting one is a copy rather than a re-serialization.

   mboxrd specifically, not mboxo or mboxcl2: it is the only common
   variant whose "From " quoting is losslessly reversible, so
   `read(append(m)) == m` byte-for-byte, which is the whole claim
   being made about this file.

3. **The mbox is append-only, and stored bytes are never rewritten.**
   A grown thread appends its new messages; deduplication is on
   `Message-ID` (with a digest of the bytes as the fallback for a
   message that lacks one). An mbox that was backed up or hashed
   yesterday is a byte-exact prefix of the one on disk today.

4. **Rendering is a separate step, reading the mbox, and is a pure
   function of (mbox, options).** The print-view PDF, the extracted
   attachments, and the `.eml` emission all come from parsing the
   stored bytes; none of them touches the Gmail API. So any thread
   ever captured can be re-rendered at any time, with different
   options, by anyone holding the file — which is what makes a
   rendering defect a bug to fix rather than damage to regret.

5. **The default shows quoted text.** `--quoted show` is the default
   because the stored PDF should be complete; `--quoted hide`
   reproduces Gmail's print behavior for whoever wants the familiar
   shape. The heuristics are kept, demoted from "what capture does" to
   "what one rendering option does."

6. **Attachments come out of the MIME parts, not a second API call.**
   The bytes are already in the mbox. Extraction is local, and the
   rule for what counts as an attachment (a part with a filename whose
   bytes did not land in the rendered body) is unchanged.

7. **A matter may watch several mailboxes.** `connectors.gmail.accounts`
   lists addresses; each has its own OAuth token under the creds
   directory, and `auth.js --account <email>` authorizes one — checking
   that the mailbox consented to is the one named, because consenting
   as the wrong Google account fails silently and looks like an empty
   mailbox. The ledger is keyed by account and then by thread id,
   because Gmail thread ids are scoped to a mailbox and two accounts
   can hand out the same one. No `accounts:` key means one unnamed
   mailbox on the existing token, exactly as before.

8. **The mbox gets no `NEW` line.** The connector contract says a
   connector announces every file it writes, and this is the deliberate
   exception: the mbox is the source the announced PDF was rendered
   from, not a second document. Announcing it would put two rows in a
   matter's catalog for one piece of evidence and send triage looking
   for the difference between them.

## Consequences

**A matter now stores each thread twice — once as mail, once as
paper — and that is the intended shape, not redundancy.** The PDF is
what a court, opposing counsel, and the matter's own index work in.
The mbox is what the PDF can be rebuilt from. They are not two copies
of one thing; they are a source and a rendering, and the no-redundant-
copies rule was always about two *equivalent* artifacts.

**It follows that the two belong on opposite sides of a matter's
`.gitignore`.** The PDFs under `assets/gmail/` are regenerable and
bulky; `assets/gmail/mbox/` is the record and is not regenerable from
anything the matter holds. A matter that ignores the first should
commit the second.

**Threads captured before this decision have no mbox and cannot get one
implicitly.** `pull.js --backfill-mbox` fetches raw mail for ledger
entries that lack one, renders nothing, and prints no `NEW` lines — so
a catch-up over a large matter does not re-triage every PDF the matter
already has. It is opt-in and rate-limited because it costs one API
call per thread, and the ledger is written after each thread, so a run
bounded by `--limit` resumes where the last one stopped. A thread never
backfilled keeps its old PDF and no source; nothing pretends otherwise.

**The connector now parses MIME itself, with no new dependency.** What
real mail uses is a bounded grammar — header unfolding, content-type
parameters including the RFC 2231 forms, encoded-words, base64 and
quoted-printable, multipart recursion — and about three hundred lines
covers it. A mail-parsing library would put a fourth upgrade treadmill
under the one part of this system that must still read a 2015 message
in 2035, and unknown constructs degrade here to "a leaf part with these
raw bytes," which loses nothing.

**The print view still fetches Gmail's logo and file-type icons from
gstatic**, as Gmail's own print view does, so it is recognizably a
Gmail printout. That is the one thing in the rendering that is not
local: a render with no network produces the same layout with the
images missing. Nothing else in the pipeline needs a network.

**Two mailboxes that both hold the same conversation produce two
threads, two mboxes, and two PDFs** (the second collision-suffixed).
That is honest — they are two mailboxes' records of it, with different
headers, different labels, and possibly different recipients — and the
alternative, merging by `Message-ID` across accounts, would silently
assert that one account's copy stands for both.
