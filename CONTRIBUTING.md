# Contributing

Thanks for helping build client-side litigation infrastructure.

## Ground rules

- **No case data, ever.** PRs must contain no real names, case
  numbers, addresses, or document content from actual matters. Use
  "Jane Roe"/"John Doe", "Smith v. Smith", and fictional facts.
  Maintainers will reject anything that smells real.
- **Originals-are-sacred applies to code too**: processing code must
  never modify input files; outputs are new files.
- **Connectors** are the main contribution surface — see
  [docs/connectors.md](docs/connectors.md) for the contract and the
  hard-won portal-automation advice. A new connector needs a
  `manifest.json`, config documented in the manifest and docs, and
  graceful unconfigured/failure behavior.
- **Docs are load-bearing.** The AI triage layer reads the same
  conventions humans do; a behavior change without a doc/template
  change is half a change.
- Python: 3.12+, deps in `pyproject.toml`, installed with `uv sync`.
  Node: 18+, deps in `connectors/package.json`. Match the style of
  the file you're editing — especially in the ported operational
  trees, which keep their upstream style deliberately (see
  [AGENTS.md](AGENTS.md)).

## Specs, design, tests

The full workflow — spec-first, tests-with-features, and the tiered
nonblocking test protocol — is in [docs/development.md](docs/development.md)
(agents: the operative copy is the repo-root AGENTS.md).

- Changes to behavior start from `specs/` (what must be true) and,
  for cross-cutting choices, an ADR in `design/` (what we decided and
  why). Code that contradicts an accepted spec or ADR needs the
  document changed first.
- Run the test harness: `uv run pytest` (see docs/testing.md;
  AI-judged checks need the `claude` CLI and are skipped without it).
  New features come with scenario coverage — deterministic checks
  first, AI judgments for the properties only judgment can see.

Also run the demo matter end-to-end before submitting:

```bash
./cli/sc init /tmp/sc-demo && cp -R examples/demo-matter/src examples/demo-matter/envelopes.yaml /tmp/sc-demo/
cd /tmp/sc-demo && make list && make demo_declaration
```

Portal connectors can't be CI-tested against live services; include a
debug dump (redacted) or DOM description with selector changes.
