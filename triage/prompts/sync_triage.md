Automated evidence-sync triage for this matter. The scheduled sync just
brought in the NEW files listed at the end of this prompt. Each line is
`<connector> <absolute path>`. Fold everything into project knowledge
per this matter's CLAUDE.md conventions.

Per-connector handling:

**gmail** (assets/gmail/, born-digital searchable PDFs; no OCR, no .txt
sidecars):
- Append one row per file to assets/gmail/CATALOG.md: date, subject,
  participants, a 1–2 sentence gist, and case relevance. Mark
  privileged attorney-client threads as such. Keep rows in filename
  (chronological) order.

**mycase** (inbox/mycase/ staging, already renamed to dated
snake_case; the staging subdirectory mirrors the portal folder and is
a routing hint):
- Route each file to its proper home, moving it out of staging:
  court-filed/conformed documents (file stamps, conformed captions)
  → pleadings/ ; drafts and unfiled work product from counsel
  → lawyer_drafts/ ; correspondence, records, and exhibit source
  material → the right assets/ subdirectory (with an INDEX.md row, and
  an OCR-supplement check per CLAUDE.md if scanned).
- Before moving into pleadings/, check for an existing copy (compare
  content, not just names) — if the document already exists there,
  delete the staged duplicate instead. Keep names in the dated
  snake_case convention; fix obvious typos in names when the document
  itself shows the correct spelling.

**any other connector**: treat its output as inbox material — follow
the matter CLAUDE.md triage conventions (literate rename, OCR
supplement if scanned, sidecar, INDEX.md row, route to the right
directory).

Then, for ALL connectors:
- Update KNOWLEDGE.md where content is case-significant (new events,
  orders, deadlines, admissions, evidence, posture changes).
- Add TODO.md / QUESTIONS.md items only for genuinely new action items
  or open questions, per the live-list conventions (time-sensitive
  first; resolved items are deleted, not struck through).
- Never put drafting-history annotations in pleading sources; never
  write ` --- ` with spaces around it (em-dash convention).

Be conservative: when significance or routing is unclear, leave the
file where it is, note it in the catalog/INDEX with "needs human
review", and move on. You are a clerk, not a lawyer: never draft,
file, send, or sign anything from this triage pass.
