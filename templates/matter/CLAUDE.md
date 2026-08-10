# Agent Instructions — <Matter Name>

This directory holds evidence, work product, and configuration for one
matter — **no program code**. Builds, connectors, scheduling, form
filling, and triage prompts come from prosaic; never copy tooling in
here, and never edit prosaic from inside this matter.

<!-- prosaic: the matter-level agent contract. Template from
     prosaic/templates/matter/CLAUDE.md. Keep it to what is SPECIFIC
     to this matter — the shared conventions live in the workspace
     contract and are inherited automatically. Duplicating them here
     creates a second copy that drifts and silently overrides. -->

**The shared conventions live in the workspace contract `../CLAUDE.md`**
(a symlink to `prosaic/templates/workspace/CLAUDE.md`) and load
automatically alongside this file: dash rules, NOTREAL and the draft
banner, triage and INDEX.md, change authority, commits, backup,
conduct. Where the two disagree, this file wins for this matter.

If there is no workspace contract above this directory, copy
`prosaic/templates/workspace/CLAUDE.md` into the parent directory
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
| Back up this matter | `<prosaic>/cli/sc backup push .` |

Configuration: `matter.yaml` (case, connectors, backup),
`envelopes.yaml` (filing envelopes). Connector/sync state lives in
`.state/` (gitignored, regenerable).

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
