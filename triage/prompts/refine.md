Nightly knowledge refinement for this matter (ADR-0044). You propose;
you do not change knowledge. The only file you may create or write is
`{proposal}`. Do not edit any note, index, TODO, QUESTIONS, or
document. Do not run the sync. Do not commit.

Read `{inputs}` first: it lists every commit and changed file since the
last pass, the vault's lint state, notes whose sources changed, stale
notes, text-coverage gaps, the last sync's outcome, and the open
questions. Then read the changed documents' text under `derived/text/`
and the notes they touch, in full.

Write `{proposal}` with these sections, each item concrete enough to
accept or reject with one word:

1. **Proposed note edits.** For each, the note (`[[stem]]`), the exact
   text to add or change, the source (path and page) for every fact, and
   the date. Quote documents verbatim; never paraphrase a quotation.
2. **New notes needed.** Type, title, aliases seen in the record, and the
   facts with sources.
3. **Contradictions.** Where a note says one thing and a document or a
   later note says another. Cite both.
4. **Questions for the human.** What only they can answer: a date the
   record does not fix, a decision, an identity. One line each, most
   time-sensitive first.
5. **Housekeeping.** Lint errors, notes without sources, unsearched
   documents, failed connectors, staging still present.

Rules: absolute dates only; no fact without a source or an explicit
"(unsourced)"; never invent a name; mark anything uncertain as such.
Keep the whole proposal under 300 lines; a human decides it in a
thirty-minute standup. Date the top of the file {date}.
