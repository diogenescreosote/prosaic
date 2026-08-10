## What & why

## Checklist
- [ ] No real case data anywhere (fixtures are fictional: Jane Roe / Smith v. Roe / 24CV00000)
- [ ] Relevant `specs/` consulted; updated first if behavior changed
- [ ] Tests ride along (deterministic; AI-judged where judgment-shaped) — see docs/testing.md
- [ ] `PROSAIC_AI_TESTS=0 uv run pytest -q` green; `uv run ruff check .` and `uv run mypy prosaic tests` clean
- [ ] Form descriptor changes: empirically verified (fill → rasterize → look) with evidence in the PR
- [ ] New ADR in `design/` if this crosses component boundaries
