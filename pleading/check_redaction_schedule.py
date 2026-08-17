#!/usr/bin/env python3
"""Cross-check redaction configs against the schedule that authorises them.

A redaction schedule and the configs implementing it drift, silently and in
both directions. The configs are written while reading the documents, so they
find material the schedule never described; the schedule is edited for
argument, so items get renumbered, narrowed or dropped. Neither file knows
about the other, and nothing on the page shows the mismatch.

That drift is a legal problem, not a bookkeeping one. A redaction the schedule
does not enumerate is relief nobody asked the court for, applied anyway. An
enumerated item with nothing implementing it is relief asked for and not
delivered. Both are discovered by the reader, not the author.

So: every operation carries an `item` naming its schedule identifier, and this
tool checks that the identifiers on both sides agree.

    check_redaction_schedule.py <schedule.md> <config.json> [<config.json> ...]

The schedule is any markdown file whose tables have a first column holding the
item identifier. Identifiers are matched literally, so use stable ones.

USE STABLE, PER-SECTION IDENTIFIERS -- A1, B2, C12 -- NOT ONE RUNNING NUMBER.
With a single 1..N sequence, dropping one row renumbers every row after it and
silently invalidates every config label downstream, while both files still look
internally consistent. Per-section identifiers confine an edit to its section.

EXIT STATUS
───────────
1 if any operation names an item the schedule does not contain (the serious
direction: unauthorised redaction), or if the schedule is unreadable.
Enumerated items with no operations are reported but do not fail: filing-level
relief ("seal the original"), material routed to a conditional lodgment, and
items awaiting a document not yet in hand all legitimately have none. Read the
list and confirm each is one of those.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def schedule_items(md: Path) -> list[str]:
    """Item identifiers from the first column of every markdown table row."""
    items: list[str] = []
    for raw in md.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        first = line.strip("|").split("|")[0].strip().strip("`*_ ")
        if not first or set(first) <= set("-: "):
            continue
        if first.lower() in {"#", "item", "id", "no", "no."}:
            continue
        # An identifier, not prose: short, no spaces.
        if len(first) <= 8 and " " not in first:
            items.append(first)
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("schedule", type=Path)
    ap.add_argument("configs", type=Path, nargs="+")
    args = ap.parse_args()

    if not args.schedule.exists():
        print(f"ERROR: no schedule at {args.schedule}", file=sys.stderr)
        return 1
    declared = schedule_items(args.schedule)
    dupes = {i for i in declared if declared.count(i) > 1}
    declared_set = set(declared)

    ops: dict[str, int] = defaultdict(int)
    where: dict[str, set[str]] = defaultdict(set)
    untagged: list[tuple[str, str]] = []
    for cfg_path in args.configs:
        cfg = json.loads(cfg_path.read_text())
        for op in cfg.get("redactions", []):
            if "_section" in op:
                continue
            item = op.get("item")
            if not item:
                untagged.append((cfg_path.name, op.get("description", "")[:70]))
                continue
            ops[item] += 1
            where[item].add(cfg_path.name)

    unauthorised = sorted(set(ops) - declared_set)
    opless = [i for i in declared if i not in ops and i not in dupes]

    print(f"schedule: {args.schedule.name} --- {len(declared_set)} item(s)")
    print(f"configs:  {len(args.configs)} file(s), {sum(ops.values())} operation(s)")
    print()

    if dupes:
        print(f"  DUPLICATE identifiers in the schedule: {sorted(dupes)}")
    for name, desc in untagged:
        print(f"  ERROR  operation has no 'item': {name}: {desc}")
    for i in unauthorised:
        print(f"  ERROR  operation cites '{i}', which the schedule does not "
              f"contain (in {', '.join(sorted(where[i]))})")
    if opless:
        print(f"  {len(opless)} enumerated item(s) with no operation --- confirm each "
              f"is filing-level, a lodgment, or awaiting a document:")
        print(f"    {', '.join(opless)}")
    if not (untagged or unauthorised or dupes):
        print("  OK: every operation is authorised by an enumerated item.")

    return 1 if (untagged or unauthorised or dupes) else 0


if __name__ == "__main__":
    sys.exit(main())
