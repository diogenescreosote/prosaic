---

## This is an entity matter (ADR-0051)

`matter.yaml` says `case.type: entity`. This directory is the
governance record of an organization (its formation, governing
documents, board acts, officers, tax status, government filings, any
litigation), not a lawsuit. The shared machinery is unchanged; the
conventions translate as follows.

### STOP. The record must read without prosaic

The people who rely on this folder (directors, auditors, a successor
secretary, a bank, an agency) will open it in a file browser. So:

- **`START HERE.md` is the front page.** Its "Where things stand"
  table states the entity's current facts (name, form, entity number,
  date formed, office, agent, directors, officers, tax status, fiscal
  year, next deadline), each naming the record that establishes it.
  **Any triage or commit that changes one of those facts updates the
  table in the same change.** A fact with no record behind it is left
  blank or marked "pending"; never filled from a draft or from
  memory.
- **`assets/` is the record book**, in numbered sections with plain
  names (`01 Formation` … `10 Correspondence`). Every record goes in
  exactly one section, named `YYYY-MM-DD_what_it_is.pdf`, with a row
  in that section of `assets/INDEX.md`. Do not add, rename or
  reorder sections; a reader learns the shape once.
- **Records are PDFs** (or the original format received). A
  governance act that exists only as markdown is not in the record:
  it is built from `src/`, executed, and the executed PDF is filed.
  Sidecars, OCR copies and text layers stay under `derived/`, never
  beside the record.
- **Inbox is still the only way in.** Nothing is placed in `assets/`
  directly; it arrives in `inbox/` and is triaged.

### Status, not provenance by inference

`pleadings/` does not exist here. Its rule carries over to the whole
record book: each INDEX row has a status (`filed`, `acknowledged`,
`as-submitted`, `executed`, `copy`, `not-in-hand`), recorded by a
human from the face of the document. A receipt or confirmation is
`acknowledged`, not `filed`; an as-submitted copy is not the endorsed
one; a draft is never any of these. If a deadline or an answer needs
the filed or executed version and the index says otherwise, say so
and stop.

### Drafts and documents

- Governance instruments (bylaws, resolutions, written consents,
  minutes, an incorporator's action, policies) are
  `doctype: document`; letters to agencies are `doctype: letter`.
  Nothing is captioned unless it is filed in a court proceeding.
- Every draft carries `notreal:` from creation, e.g.
  `notreal: "DRAFT---not adopted"`. Only the human removes it.
- The authorities rule applies unchanged: every code section a draft
  relies on is fetched in full into `research/authorities/` and
  combed first.
- Commits: an adopted act or an endorsed filing that arrives is a
  `docket` commit with `Executed:` or `Filed:` from the face of the
  document.

### Litigation and finances

- If the entity becomes party to a proceeding, the case is its own
  litigation matter (`sc init`), linked both ways by
  `related_matters:` in `matter.yaml`. `08 Litigation` here holds only
  the papers that start and end it and the board's acts about it.
- `09 Finances` holds board-level financial records (adopted budgets,
  annual financial statements, audits, banking resolutions), not the
  books of account. Leave it empty if the books live elsewhere.
