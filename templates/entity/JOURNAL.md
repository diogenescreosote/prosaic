# Journal of Acts

<!-- prosaic: the entity's journal of acts (ADR-0052). Append-only;
     `sc journal check` validates it and the commit hook refuses an
     unannotated edit. Entries go at the bottom, in the same commit as
     the record (or report) of the act. -->

This is the running record, in order, of every official act of
**Example Foundation**: each thing the organization, its board, its
officers, or anyone acting with authority under its governing
documents actually did. It is the place to answer "when did we decide
that, who decided it, and where is the paper?" The documents
themselves are in `assets/`; each entry says which one.

**What belongs here.** Formation filings. Adoption and amendment of
the articles and bylaws. Board votes and written consents, with the
vote. Elections, appointments, resignations and removals of directors
and officers. Hiring and firing. Adoption of policies. Contracts and
commitments the board authorizes. Delegations of authority. Any
exercise of an approval or veto right by a body that has one under
the governing documents. Filings with agencies, and determinations
received from them.

**What does not.** Drafts, plans, intentions, and discussions that
decided nothing. An act goes in when it has happened.

**How entries are written.** Each entry is numbered (J-0001, J-0002,
... with no gaps) and added at the bottom, in the order entered. The
date in the heading is the date of the act; the `Entered` line is the
date the entry was written, which may be later. Every entry has the
six lines shown in the example below; write `n/a` where one does not
apply and `pending: <what>` where the record is not yet in hand.

**Nothing is deleted.** A mistake is corrected by a new entry titled
"Correction to J-0007: ...". Rarely, an entry is edited in place;
then a note goes directly under the changed text saying what changed
and why:

> **Amended 2026-02-01 by Jane Roe:** vote count corrected from 4-1 to 5-0 --- the minutes were misread.

Superseded wording stays readable (it may be struck through,
`~~like this~~`), never removed.

Example entry:

```
## J-0001 · 2026-01-15 · Articles of incorporation filed
- **Act:** Articles of incorporation filed with the Secretary of State and endorsed as filed.
- **By:** Jane Roe, incorporator
- **Vote:** n/a
- **Authority:** n/a
- **Record:** assets/01 Formation/2026-01-15_articles_of_incorporation_endorsed.pdf
- **Entered:** 2026-01-20 by Jane Roe
```

---

## Entries
