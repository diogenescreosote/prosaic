# 0002 — Polyglot Python + Node, thin CLI

**Status:** accepted (2026-08)

## Context
The pleading generator (~8k lines, battle-tested in real filings) is
Python/reportlab/pypdf. Browser automation and Gmail print-view
rendering are Node/Puppeteer. Rewriting either to unify languages
risks regressions in exactly the code that must not regress.

## Decision
Keep both: `pleading/` is a Python package, `connectors/` a Node
package, `cli/sc` a thin Python dispatcher that shells out. Each side
owns its dependency file.

## Consequences
Maximum reuse of proven code; each ecosystem used where it's
strongest. Contributors need both toolchains (mitigated: each side
runs independently; docs say which you need for what). Cross-language
calls happen only at process boundaries with text protocols — which
ADR-0003 turns into a feature.
Alternatives: all-Python via Playwright (rejected for now: rewrites
working scrapers); all-TS (rejected: rewrites the generator).
