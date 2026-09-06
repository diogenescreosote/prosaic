# Agent Instructions — <Matter Name>

This directory holds evidence, work product, and configuration for one
matter — **no program code**. Builds, connectors, scheduling, form
filling, and triage prompts come from prosaic; never copy tooling in
here, and never edit prosaic from inside this matter.

<!-- prosaic: the matter-level agent contract, read by any coding
     agent (CLAUDE.md beside it is a pointer here). Template from
     prosaic/templates/matter/AGENTS.md. Keep it to what is SPECIFIC
     to this matter — the shared conventions live in the workspace
     contract and are inherited automatically. Duplicating them here
     creates a second copy that drifts and silently overrides. -->

**The shared conventions live in the workspace contract `../AGENTS.md`**
(a symlink to `prosaic/templates/workspace/AGENTS.md`) and load
automatically alongside this file: dash rules, NOTREAL and the draft
banner, triage and INDEX.md, change authority, commits, backup,
conduct. Where the two disagree, this file wins for this matter.

If there is no workspace contract above this directory, copy
`prosaic/templates/workspace/AGENTS.md` into the parent directory
(or symlink it) — otherwise none of those rules are in force.

---

## Tooling map (what lives where)

| Need | Use |
|---|---|
| Build a filing envelope | `make <envelope>` (this dir; `Makefile` includes prosaic's) |
| List envelopes | `make list` |
| Report stale build output | `<prosaic>/cli/sc clean .` |
| Fill a Judicial Council form | `<prosaic>/cli/sc form fill <id> …` (`sc form info <id>` first) |
| OCR-supplement a PDF | `python3 <prosaic>/pleading/ocr_supplement.py <in.pdf> <assets_dir>` |
| Pull sources + triage now | `<prosaic>/cli/sc sync .` |
| Redact a PDF | `python3 <prosaic>/pleading/redact_pdf.py …` |
| Re-render a stored email thread | `<prosaic>/cli/sc mail-render assets/gmail/mbox/<stem>.mbox --pdf <out>` |
| Back up this matter | `<prosaic>/cli/sc backup push .` |

Configuration: `matter.yaml` (case, connectors, backup),
`envelopes.yaml` (filing envelopes). Connector/sync state lives in
`.state/` (gitignored, regenerable).

---

## STOP. `assets/gmail/mbox/` is the record; the PDF is a rendering

The gmail connector stores each thread twice, and the two are not
copies of each other (ADR-0038):

- `assets/gmail/mbox/<stem>.mbox` — every captured message as raw
  RFC 822 bytes, exactly as it was transmitted. **This is the
  evidence.** It is append-only: never edit it, never reformat it,
  never delete a message out of it. Commit it.
- `assets/gmail/<stem>.pdf` — Gmail's print view, *rendered from that
  mbox*, and regenerable from it at any time with
  `sc mail-render <mbox> --pdf <path>`. Bulky and derived; a matter
  may gitignore it.
- `assets/gmail/attachments/<stem>/` — the thread's attachment parts,
  extracted from the same bytes.

So: read the PDF, cite the PDF, catalog the PDF. But when a question
is about what a message actually *said* — full headers, the quoted
chain, an attachment the print view only names — go to the mbox.
`sc mail-render <mbox> --list` enumerates it and `--eml n:<path>`
writes any single message out verbatim.

The PDF shows quoted reply chains by default. If one reads
`[Quoted text hidden]`, it was rendered under `--quoted hide` (or
predates ADR-0038) — re-render it rather than reporting the thread as
incomplete.

---

## Who is who

<!-- Parties, counsel on each side, the court and department, and any
     name that an agent could plausibly confuse. Get this right: a
     misattributed quote or a letter addressed to the wrong side is
     the most damaging cheap mistake available. -->

## This matter's quirks

<!-- Anything true here that is not true generally: unusual layout,
     a directory that moved and left stale paths behind, a document
     set with its own naming convention, a standing instruction from
     counsel. Delete this heading if there are none. -->
