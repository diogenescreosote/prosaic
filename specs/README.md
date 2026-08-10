# specs/ — what each part of prosaic is *for*

These files are **teleological, not architectural**: each one states
the purpose of a component, the promises it makes to the people (and
agents) who rely on it, and the non-obvious constraints that bound it —
without prescribing how it is built. `docs/` explains how to *use* the
system; `design/` records how and why it is *built* the way it is;
`specs/` says what it must *accomplish* to be considered working.

## What specs are for

1. **Directing development.** A component's spec is written (or
   revised) before the component; implementation follows the spec, not
   the other way around. When code and spec disagree, one of them is
   wrong *on purpose* — decide which, then fix it.
2. **Generating tests.** Tests should follow from specs with only
   modest cognition and creativity. Every promise in a spec is a test
   waiting to be written; every non-obvious constraint is a regression
   waiting to be prevented. Scenario tests (`tests/scenarios/`)
   reference the spec they execute; a promise with no test is marked
   `(untested)` in the spec until someone closes the gap.
3. **Aligning agents.** AI agents build and maintain much of this
   system. A spec is the durable statement of intent that survives any
   one session's context.

## How to write one

- **Frame: aspiration and obligation.** "The form filler exists so
  that a self-represented person can produce filings a clerk accepts
  without knowing PDF internals. It promises: …" Not: "The form filler
  uses pypdf to …".
- **Promises are testable sentences.** Prefer "every output form's
  signature and date lines are empty" over "handles signatures
  correctly."
- **Constraints carry their reasons.** "Originals are never modified
  (an altered original is spoliation-adjacent and destroys evidentiary
  value)" — the *why* is what keeps future changes honest.
- Keep one component per file; keep files short enough to read whole;
  link related specs rather than repeating them.

## Index

- [matter.md](matter.md) — the matter directory: layout, knowledge
  files, and the conventions that make a case navigable
- [pleading/generator.md](pleading/generator.md) — Markdown →
  pleading-paper rendering and envelope assembly
- [pleading/forms/README.md](pleading/forms/README.md) — the JC form
  system: descriptors, engine, and its promises
- [pleading/forms/<id>.md](pleading/forms/) — per-form specs: what the
  form is for, its legal role, and its non-obvious constraints
- [connectors/README.md](connectors/README.md) — the connector
  contract and the promises every connector makes
- [connectors/<name>.md](connectors/) — per-connector specs
- [sync.md](sync.md) — scheduled evidence sync: cadence, catch-up,
  failure behavior
- [triage.md](triage.md) — the AI clerk: what it may and may not do
- [cli.md](cli.md) — the `sc` command surface

## Relationship to design/

`design/` holds Architecture Decision Records (ADRs): point-in-time
choices with context, alternatives, and consequences ("descriptors are
YAML data, not Python subclasses, because…"). Specs say *what must be
true*; ADRs say *what we decided and why*. A spec rarely changes; ADRs
accumulate. When an ADR is superseded, the spec usually didn't move.
