# Spec: gmail connector

## Purpose

Email with opposing parties, counsel, schools, and providers is
evidence, and it should arrive in the matter continuously — as PDFs
a court can take — rather than being hunted down thread by thread
the week before a filing. The gmail connector exports every Gmail
thread involving the configured correspondents into
`assets/gmail/`, one PDF per thread, in a form that matches Gmail's
own print view.

## Promises

1. **Court-usable print view.** Each thread renders as Gmail's print
   view — sender, recipients, dates, and subject on each message —
   the presentation courts and opposing counsel already recognize
   from Gmail printouts, not a lossy text dump. *(untested)*
2. **Criteria are correspondents, not searches.** Configuration is a
   list of addresses and bare domains, each optionally bounded by
   `after:`/`before:` dates — so the corpus is defined by *who* the
   case is about and *when* the relevant period runs, and the same
   config re-run captures new mail with the same meaning.
   *(untested)*
3. **Incremental by filename.** A thread already exported is not
   re-fetched; re-running adds only what is new. *(untested)*
4. **Chronological, literate names.** Output is
   `YYYYMMDD_<subject_snake_case>.pdf`, so the directory reads as a
   dated correspondence log without opening a file. *(untested)*
5. **Contract compliance**: `NEW` lines on stdout only, straight to
   its `assets/gmail/` destination (born-digital, no triage routing
   needed), OAuth token outside the matter, exit nonzero on failure.
   *(untested)*

## Non-obvious constraints

- **Output goes directly to `assets/`, not staging** — a Gmail
  thread's identity and home are unambiguous, so routing judgment
  (the reason staging exists) adds nothing. Triage's job for these
  files is cataloging (a CATALOG.md row per thread), not moving.
- **No OCR, no `.txt` sidecars**: the PDFs are born-digital and
  already searchable; supplementing them would violate the
  no-redundant-copies rule.
- **Date bounds are per-correspondent, not global**, because
  relevance windows differ — an opposing party's entire history may
  matter while a vendor's is only relevant after the contract date.
- **The export is only as complete as the account and the query.**
  The connector pulls threads *involving* configured addresses; it
  does not attest completeness of production. Anything offered as a
  complete record still needs human verification against the
  mailbox.
- **A domain criterion is broad by design** (any correspondent at
  the firm); use it for institutions, not for fishing.
