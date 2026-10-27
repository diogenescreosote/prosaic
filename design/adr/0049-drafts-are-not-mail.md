# 0049 — Drafts are not mail

**Status:** accepted (2026-10)

## Context
Gmail keeps unsent drafts inside the thread they answer, and the API
returns them beside the real messages. The connector first excluded
drafts from renders after a cancelled scheduled send was rendered as a
letter that had gone out. It still listed and counted them, though, so
the brief could say a reply was "still sitting in Drafts", and
captures made before the filter had already stored and rendered
drafts. A draft-only thread came out as an ordinary print-view PDF:
"1 message", From the mailbox owner, To the other side. Nothing on its
face said it was never sent, and every downstream reader (triage, the
mail index, `sc find`, a drafting agent) treated it as correspondence.

Counting drafts was a half-measure. A count invites the next question
("what does it say?"), and a draft's words are the owner's private
working material, not something anyone received. Whether a reply
went out is answered by the sent mail, which is in the record.

## Decision
A draft is not mail. The gmail connector never lists, fetches, stores,
renders, counts, announces or records one:

- every search it makes carries `-in:drafts`, and every message with
  the `DRAFT` label is dropped before it is fetched and again on the
  fetched message's own labels;
- the mbox writer refuses a `DRAFT`-labelled message, so a caller that
  forgets to filter cannot store one;
- a thread that is nothing but drafts produces no file;
- the ledger keeps nothing about drafts (old `draftCount` and
  `latestDraftAt` fields are tolerated and dropped on rewrite), and
  the brief's unsent-drafts section is gone;
- an mbox written before this rule is never rendered with its draft:
  the thread's drafts' Message-IDs are held in memory during an export
  and excluded.

The only exception is the user's explicit instruction about a
particular draft. No tool performs it; a person who wants a draft in
the record puts it there deliberately, marked as what it is.

Legacy captures are cleaned by an audit, `sc mail-audit-drafts`. It is
report-only by default and quotes no draft. With `--apply` it moves
draft-only renders, and the old copies of mixed threads, into
`.private/gmail_drafts/` (gitignored, outside every search, never
deleted) and rebuilds the mixed threads without their drafts. Moving
rather than deleting keeps "originals are sacred": the bytes still
exist, just not in the record. The mbox is append-only (ADR-0038), and
this is the one sanctioned exception: the original mbox moves out
whole, and a new one is written with the same bytes for every message
that is not a draft. Stored messages that Gmail no longer has at all
might be old draft versions or deleted mail. Those are reported as
unverified and never moved, because only a person can tell which.

## Consequences
- A matter can no longer learn from the brief that a reply is still in
  Drafts. That was the cost of the old count, and it is accepted: the
  sent mail shows what went out.
- A draft-only thread that is later sent shows up as a new thread on
  the next listing that covers it, and is captured then.
- The audit needs the mailbox (drafts.list and per-thread metadata), so
  it runs with the matter's token. A thread deleted from Gmail can't
  be checked, and its render stays as it is.
- The mail index skips any message whose Message-ID the audit recorded
  as a draft, or whose Takeout-style `X-Gmail-Labels` names Drafts, so
  a legacy mbox that has not been cleaned yet still does not feed a
  draft into a search.
