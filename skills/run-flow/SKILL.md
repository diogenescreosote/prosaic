---
name: run-flow
description: Run a files-first flow - a YAML graph of agent, command, judge, and gate steps for judgment work like drafting loops and adversarial review. Use when a task says to run a flow, when a gated run needs resuming, or when repetitive judgment work deserves a reusable loop instead of ad-hoc prompting.
---

# Run a flow

Flows (`specs/flows.md`, ADR-0024) are to judgment work what the
Makefile is to builds. The repo ships them in `flows/`; a matter may
carry its own.

## Running

```
<prosaic>/cli/sc flow <flow.yaml> --input source=src/Declaration.md
```

- Outputs land in `.flow/<name>-<stamp>/` — read them; they are the
  work product.
- Exit 3 means a gate: the run directory has an
  `APPROVAL-<id>.pending` file naming the human decision. Present it
  to the user; NEVER approve a gate yourself — renaming to
  `.approved` is the user's act, then rerun with `--resume <rundir>`.
- A failed judge prints its rationale per round; three failed rounds
  fail the run, and the intermediate files show why.

## Writing a flow

Follow `flows/draft-review.yaml` as the model. Rules that matter:

- Prompts receive PATHS (`{step_id}` is a file path); tell the agent
  to read them.
- A flow must not edit matter sources — it writes into its run
  directory, and a human adopts results by hand. Put a gate before
  anything a court, counsel, or counterparty would ever see.
- Deterministic steps (render, hash, grep) are `command` steps or,
  better, calls into Make and the existing CLIs; do not restate build
  logic inside a flow.
- New reusable flows are documented like any capability: the flow
  file's own header comment says what it is for and how to invoke it.

References: `specs/flows.md`, ADR-0024, ADR-0020 (the agent seam).
