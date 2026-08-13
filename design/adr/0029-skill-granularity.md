# 0029 — Skill granularity: split by co-activation, demote by layer

**Status:** accepted (2026-08)

## Context
ADR-0021 made skills the agent-facing capability packaging but said
little about sizing them. The naive instinct — split everything
small so an agent loads as little as possible — misreads the cost
structure: a skill's DESCRIPTION is loaded into every session
unconditionally (it is the routing index), while its BODY loads only
when triggered. Splitting therefore adds permanent index weight per
fragment, and over-split systems fail at routing (the model picks
one of the three skills it needed; cross-reference chains cost a
load per hop and a chance to stop hopping) before they fail at
loading. The real optimization target is threefold: index weight,
plus expected body-tokens per task, plus — dominating both — the
probability that the right rule is NOT in context when a decision is
made. A missing rule costs a defective filing; forty extra lines
cost forty lines.

## Decision
1. **Split by co-activation, not by topic.** The unit is what one
   task needs in context at once. Wrong-split tell: two skills
   always load together, or one body mostly points at the other.
   Wrong-merge tell: the description needs an "and" joining triggers
   that never co-occur.
2. **Demote before splitting: code > data > prose.** A rule the
   renderer can enforce becomes code plus a test plus one table row
   (the stranded-heading fix: ~700 lines of doctrine arrived, ~15
   lines of keep-with-next code and a one-row "enforced" entry
   remain). A rule that varies by jurisdiction becomes data a skill
   points at. Only judgment stays prose.
3. **Layer by loading condition.** Always-loaded (AGENTS.md, the
   descriptions): invariants and routing only. Per-task (skill
   bodies): the map — commands, order, judgment — capped at 120
   lines, enforced by test. On-pointer-follow (specs, ADRs,
   references): unbounded depth, paid only when chased. A body over
   the cap is fixed by demotion down a layer, not by splitting into
   a sibling skill.
4. **State everything once.** A rule appearing in two skills is a
   defect; cross-link instead. Same principle as the statutory texts
   living as shared constants across the three renderers.
5. **Skill count grows slower than capability count.** New machinery
   usually lands as an engine plus one table row and one command in
   an existing skill; a new skill requires a task-shape no current
   description covers. If the two counts ever track each other, the
   packaging has failed.

## Consequences
The tuned system loads on the order of one or two hundred lines of
exactly-relevant instruction per task, and the index stays cheap.
Costs: judgment calls about co-activation are judgment calls, and
the 120-line cap will occasionally force a demotion someone would
rather not do — which is the point. The operative version of these
rules lives in skills/README.md, where a contributor adding a skill
actually looks; this ADR records why. Extends ADR-0021.
