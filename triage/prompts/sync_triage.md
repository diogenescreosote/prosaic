Automated evidence-sync triage for this matter. The scheduled sync just
brought in the NEW files listed at the end of this prompt. Each line is
`<connector> <absolute path>`. Fold everything into project knowledge
per this matter's agent contract conventions (AGENTS.md, or legacy
CLAUDE.md).

**Read every page before you catalog anything.** The failure this
prompt exists to prevent is a confident catalog row written after
reading part of a document. For each file:

```bash
python3 <prosaic>/triage/read_coverage.py --text <file.pdf>
```

Read that output end to end and check the closing page count against
the document's. No `head`, no `grep`-instead-of-reading, no
first-page-only. A page with no text layer is not an empty page --- the
tool flags it and exits non-zero; OCR it (`ocr_supplement.py`) and read
the OCR, or rasterize and look. An attachment inside an email export is
its own document and gets its own read. If a document cannot be fully
read, say which pages, mark the row PARTIAL and "needs human review",
and move on --- that is a fine outcome; silently reading less is not.
The full discipline is the `triage-inbox` skill.

Per-connector handling:

**gmail** (assets/gmail/, born-digital searchable PDFs; `sc text ensure`
has already written their page-marked `.txt` sidecars --- do not
hand-write sidecars, and do not OCR them):
- Append one row per file to assets/gmail/CATALOG.md: date, subject,
  participants, a 1–2 sentence gist, and case relevance. Mark
  privileged attorney-client threads as such. Keep rows in filename
  (chronological) order.
- Read the whole thread, not the top message: a forward carries the
  quoted chain beneath it, and the operative fact is often in the
  oldest message. Note any attachment the export carries, and treat it
  as a document in its own right.

**mycase** (inbox/mycase/ staging, already renamed to dated
snake_case; the staging subdirectory mirrors the portal folder and is
a routing hint):
- Route each file to its proper home, moving it out of staging:
  court-filed/conformed documents (file stamps, conformed captions)
  → pleadings/ ; drafts and unfiled work product from counsel
  → lawyer_drafts/ ; correspondence, records, and exhibit source
  material → the right assets/ subdirectory (with an INDEX.md row, and
  an OCR-supplement check per the agent contract if scanned).
- Before moving into pleadings/, check for an existing copy (compare
  content, not just names) — if the document already exists there,
  delete the staged duplicate instead. Keep names in the dated
  snake_case convention; fix obvious typos in names when the document
  itself shows the correct spelling.

**any other connector**: treat its output as inbox material — follow
the matter agent-contract triage conventions (literate rename, OCR
supplement if scanned --- `sc text ensure` does this and writes the
sidecar; check its output rather than redoing it --- INDEX.md row, route to the right
directory).

Then, for ALL connectors:
- Update KNOWLEDGE.md where content is case-significant (new events,
  orders, deadlines, admissions, evidence, posture changes).
- Add TODO.md / QUESTIONS.md items only for genuinely new action items
  or open questions, per the live-list conventions (time-sensitive
  first; resolved items are deleted, not struck through).
- Never put drafting-history annotations in pleading sources; never
  write ` --- ` with spaces around it (em-dash convention).

Before you finish, re-list the staged files and account for every one
--- routed, or deliberately left with a stated reason. Count in equals
count out. Report, by name, every file you could not fully read or
could not route.

Be conservative: when significance or routing is unclear, leave the
file where it is, note it in the catalog/INDEX with "needs human
review", and move on. You are a clerk, not a lawyer: never draft,
file, send, or sign anything from this triage pass.
