# Spec: the matter directory

## Purpose

A matter is one case in one directory, laid out so that a stranger —
human or AI agent — can arrive knowing nothing and find the record,
the posture, and the open work without a guide. Everything else in
prosaic (connectors, sync, triage, builds) assumes this shape;
the matter directory is the contract they all write into. The
standard is navigability by someone with no memory of the case:
every convention below exists because an agent's context dies
between sessions and a lawyer's attention dies between hearings.

## Matter types

`matter.yaml` declares `case.type` — `litigation` (the default when
absent) or `estate`. The layout above is common to both; an estate
matter additionally keeps the **share convention** below. Tooling
must treat an unknown type as `litigation` rather than failing: the
type gates conventions, not machinery.

## Configuration lives in the matter

The matter, not prosaic, owns its bindings (ADR-0031): which
credential a connector uses (`connectors.<name>.credential`, a
Keychain item named by reference — the key material never enters the
matter) and, where it matters, which deployment
(`connectors.<name>.url`). Prosaic-global keys may exist, but a
matter must incorporate one by reference; clients refuse a connector
with no `credential:` and print the lines to add. Prosaic implements
the skills; it stores no per-matter state.

## Promises

1. **The index never lies.** `assets/INDEX.md` describes every
   non-sidecar file under `assets/` — what it is, its date, who made
   it, why it matters — and any add/remove/rename/replace updates it
   *in the same change*. An auditor can diff disk against index and
   find zero drift; bulk imports too big for hand-written rows get a
   mechanically generated backfill index that says it is one.
   *(untested)*
2. **Originals are sacred.** Processing supplements, never replaces:
   OCR goes into an `_ocr.pdf` sibling (adding text only to pages
   that lack it), extracted text into `.txt` sidecars, transcripts
   into sidecars with the raw machine output kept, redactions into
   new files. Received bytes are never modified — an altered
   original is spoliation-adjacent and destroys evidentiary value.
   *(untested)*
3. **Everything is searchable.** Every PDF triaged into `assets/`
   is checked and OCR-supplemented if any page lacks a text layer —
   an image-only PDF is invisible to grep, to search, and to every
   agent that will ever work the matter. Already-searchable files
   are *not* duplicated (a redundant `_ocr` copy fakes provenance).
   *(untested)*
4. **Names carry meaning.** Dated documents sort chronologically
   (`YYYY-MM-DD_what_it_is.pdf`); undated evidence gets a literate
   snake_case name a stranger could parse; derived artifacts share
   their original's stem. Misspelled *names* may be fixed;
   *contents* never. *(untested)*
5. **The knowledge files keep their disciplines.** `KNOWLEDGE.md` is
   durable, dated, *integrated* knowledge — facts are folded into
   the right section and corrected when superseded, with git holding
   history; it is not an append-only log. `TODO.md` and
   `QUESTIONS.md` are live lists ordered by time-sensitivity then
   importance, and resolved items are *deleted*, not struck
   through — the files reflect only what is presently open.
   *(untested)*
6. **Inbox zero is a checkable state.** `inbox/` is unprocessed by
   definition; triage moves material out with a literate name, OCR
   supplement, sidecar, preserved original bytes in
   `processed_files/`, and an index row. An empty inbox therefore
   *means something*: everything that arrived has been processed.
   *(untested)*
7. **Drafts cannot masquerade as the record.** Anything that is a
   simulation, unfiled draft, or analytical exercise carries a
   NOTREAL marker at the top, and nothing so marked may be cited as
   a real party's position or treated as filed/served/received.
   `pleadings/` holds only file-stamped or conformed court
   documents. *(untested)*
8. **The matter carries its own agent contract.** `AGENTS.md` in the
   matter root (with a `CLAUDE.md` pointer beside it) binds every AI session that opens the directory —
   index discipline, originals-are-sacred, typography, NOTREAL,
   clerk-not-lawyer — without per-session repetition. *(untested)*

## Non-obvious constraints

- **Machine work is labeled machine work.** Transcripts, speaker
  attributions, and summaries carry provenance headers and
  verify-before-citing banners — because in a filing a misattributed
  quote is worse than no quote, and the banner is what stops a
  rushed human from pasting one in.
- **`.state/` and `out/` are regenerable and gitignored**; the
  matter works best as a git repository because history is
  provenance — every triage session's changes must be diffable and
  revertable.
- **Sidecars are exempt from indexing** precisely so the index stays
  a description of *evidence*, not a mirror of every derived file.
- The layout is opinionated on purpose: tools and prompts hardcode
  these paths, so a matter that "improves" the layout silently
  drops out of automation.

## Estate matters: the share folder

An estate matter carries a `share/` directory — the live, outward
face of the plan, shared (by Drive permissions, set by hand) with
beneficiaries, successor fiduciaries, and counsel. Its contract:

- **A destination, never a source.** `share/` holds COPIES of
  executed deliverables; the originals live in `assets/executed/`
  and the matter's history lives in git. Nothing in the matter may
  treat `share/` as authoritative, and nothing regenerable lives
  only there. After every copy in, verify the copies hash-identical
  to the originals (`sc attest hash`).
- **Human-first browsing.** The tree reads like a folder a
  meticulous person maintains by hand: `START HERE.md` at the top
  explains the legal architecture in plain language (what the
  documents are, who is who, what to do on death or incapacity),
  notes it was made with prosaic (with a link), and points the rare
  technical reader at `Verification/`. Executed instruments sit
  clean in `Executed Documents/` — no sidecars beside them.
- **The cryptography is relegated, not hidden.** `Verification/`
  holds the how-to-verify document, the anchored public key, and a
  `signatures/` subfolder with the detached signatures and
  timestamp proofs. Most readers never open it; the ones who need
  it find everything.
- **`Inbox/`** is writable by the people the folder is shared with:
  where a death certificate, a funding document, or a question
  lands. It is intake, processed like any inbox — its contents are
  claims, not records, until triaged into the matter proper.
- **`Public/`** holds what the world may see: recorded instruments
  and those slated for recordation (deeds in and out of the trust,
  memoranda of trust existence). It is world-READABLE (anyone with
  the link views); write access stays with the same people as the
  rest of the tree. Set deliberately and by hand.

*(tested: tests/test_estate_pack.py pins the scaffold's presence in
the estate pack)*
