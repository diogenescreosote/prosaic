#!/usr/bin/env python3
"""Keep a matter's `pleadings/` folder honest about what the court actually has.

THE INVARIANT
─────────────
`pleadings/` holds the court-filed version of each document, and nothing else.
Where a true conformed copy is not available and a substitute stands in -- an
unstamped as-served copy, a portal download, counsel's own copy -- the
substitution is declared, in writing, in `pleadings/MANIFEST.md`.

WHY IT NEEDS ENFORCING
──────────────────────
A PDF gives no sign of its own provenance. A working copy someone drew
redaction boxes on, a draft that was never filed, and the conformed filing all
look alike in a file listing, and they sort together by date. Once a working
copy is sitting in `pleadings/`, every later reader -- including every agent --
treats it as the record, and reasons from it. Conclusions then get drawn about
what the court has and what the other side did, and those conclusions are
wrong in a way nothing downstream can detect.

Matching some other copy you have is not evidence of provenance either. Two
files being byte-identical only proves they are the same file; it says nothing
about whether either came from the court.

So provenance is not inferable and must be recorded by a human at intake. This
tool checks that the record exists and matches the disk; it cannot and does not
try to determine provenance itself.

MANIFEST FORMAT
───────────────
`pleadings/MANIFEST.md` contains one GitHub-flavoured markdown table. Required
columns, in any order, matched case-insensitively:

  | File | Status | Source | Notes |

`File`    the file name in `pleadings/` (backticks optional)
`Status`  one of:
            conformed        bears the clerk's filing stamp
            efiled           e-filing confirmation copy from the portal
            as-served        unstamped copy as served by a party  [SUBSTITUTE]
            portal           downloaded from a case portal, unstamped [SUBSTITUTE]
            counsel-copy     copy supplied by counsel, unstamped     [SUBSTITUTE]
            unverified       provenance not established              [SUBSTITUTE]
            not-in-hand      known to exist, not yet obtained (no file required)
`Source`  free text: where it came from, and when
`Notes`   free text

CHECKS
──────
- every PDF in `pleadings/` has a manifest row, and every row a file
- every row's Status is a known value
- `_ocr` siblings inherit their base file's row and need none of their own
- files whose Status is a SUBSTITUTE are listed prominently, because they are
  the ones a reader must not mistake for the record
- rows marked `conformed`/`efiled` are spot-checked for filing-stamp text; a
  missing stamp is reported as a contradiction to resolve, not an error
- `not-in-hand` rows are listed as outstanding retrievals

Exit 1 on a structural failure (missing row, missing file, unknown status).
Substitutes and stamp contradictions are reported without failing: they are
facts about the record, not defects in the manifest.

USAGE
─────
  pleadings_manifest.py <matter-dir> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import fitz  # type: ignore[import]
except ImportError:
    fitz = None  # stamp spot-check is optional

SUBSTITUTE = {"as-served", "portal", "counsel-copy", "unverified"}
FILED = {"conformed", "efiled"}
KNOWN = SUBSTITUTE | FILED | {"not-in-hand"}

STAMP = re.compile(
    r"(ELECTRONICALLY\s+FILED|E-?FILED|Clerk of the Court|FILED\s*\n|"
    r"Superior Court of California|by fax|Deputy Clerk)", re.I)


def parse_manifest(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Parse the document table out of MANIFEST.md.

    A manifest is a document meant for humans, so it will contain other tables
    -- a legend of status values, notes, whatever the matter needs. Taking the
    first table found is therefore wrong: it parses the legend and reports every
    real row as having an unknown status. Select the table whose header actually
    carries the required columns, and ignore the rest.
    """
    if not path.exists():
        return [], [f"no manifest at {path}"]

    required = ("file", "status", "source")
    tables: list[tuple[list[str], list[dict[str, str]]]] = []
    header: list[str] | None = None
    rows: list[dict[str, str]] = []

    def flush() -> None:
        if header is not None:
            tables.append((header, rows))

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            if header is not None:          # table ended
                flush()
                header, rows = None, []
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue                        # separator row
        if header is None:
            header = [c.lower() for c in cells]
            rows = []
            continue
        row = dict(zip(header, cells))
        row["file"] = row.get("file", "").strip("` ")
        row["status"] = row.get("status", "").strip("` ").lower()
        rows.append(row)
    flush()

    matching = [(h, r) for h, r in tables if all(n in h for n in required)]
    if not matching:
        cols = " / ".join(", ".join(h) for h, _ in tables) or "(no tables found)"
        return [], [f"no table in {path.name} has all of the required columns "
                    f"{required}; tables present: {cols}"]
    if len(matching) > 1:
        return (matching[0][1],
                [f"{len(matching)} tables in {path.name} carry the required "
                 f"columns; using the first. Merge them."])
    return matching[0][1], []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("matter", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pdir = args.matter / "pleadings"
    if not pdir.is_dir():
        print(f"ERROR: no pleadings/ directory under {args.matter}", file=sys.stderr)
        return 1

    rows, errors = parse_manifest(pdir / "MANIFEST.md")
    by_file = {r["file"]: r for r in rows if r["file"]}

    on_disk = sorted(p.name for p in pdir.glob("*.pdf"))
    def base_of(name: str) -> str:
        return re.sub(r"_ocr(?=\.pdf$)", "", name)

    missing_row = [n for n in on_disk
                   if n not in by_file and base_of(n) not in by_file]
    missing_file = [r["file"] for r in rows
                    if r["status"] != "not-in-hand"
                    and r["file"] and r["file"] not in on_disk]
    bad_status = [(r["file"], r["status"]) for r in rows
                  if r["status"] not in KNOWN]

    substitutes = [r for r in rows if r["status"] in SUBSTITUTE]
    outstanding = [r for r in rows if r["status"] == "not-in-hand"]

    contradictions: list[str] = []
    if fitz is not None:
        for r in rows:
            if r["status"] not in FILED or r["file"] not in on_disk:
                continue
            try:
                doc = fitz.open(pdir / r["file"])
                head = "\n".join(doc[i].get_text() for i in range(min(3, len(doc))))
            except Exception:
                continue
            if head.strip() and not STAMP.search(head):
                contradictions.append(r["file"])

    result = {
        "errors": errors,
        "files_without_a_manifest_row": missing_row,
        "manifest_rows_without_a_file": missing_file,
        "unknown_status_values": bad_status,
        "substitutes": [{k: r.get(k, "") for k in ("file", "status", "source")}
                        for r in substitutes],
        "not_in_hand": [{k: r.get(k, "") for k in ("file", "source")}
                        for r in outstanding],
        "claims_filed_but_no_stamp_found": contradictions,
        "pdfs_on_disk": len(on_disk),
        "manifest_rows": len(rows),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"pleadings/ under {args.matter}")
        print(f"  {len(on_disk)} PDF(s) on disk, {len(rows)} manifest row(s)")
        for title, items in (
            ("ERROR  no manifest row", missing_row),
            ("ERROR  row has no file", missing_file),
            ("ERROR  unknown status", [f"{f}: {s}" for f, s in bad_status]),
        ):
            for it in items:
                print(f"  {title}: {it}")
        for e in errors:
            print(f"  ERROR  {e}")
        if substitutes:
            print(f"\n  {len(substitutes)} SUBSTITUTE(S) --- not the court's own copy:")
            for r in substitutes:
                print(f"    [{r['status']}] {r['file']}  ({r.get('source','')})")
        if outstanding:
            print(f"\n  {len(outstanding)} document(s) NOT IN HAND:")
            for r in outstanding:
                print(f"    {r['file'] or '(unnamed)'}  ({r.get('source','')})")
        if contradictions:
            print("\n  Declared filed, but no filing-stamp text found "
                  "(resolve, do not ignore):")
            for f in contradictions:
                print(f"    {f}")
        if not (missing_row or missing_file or bad_status or errors):
            print("\n  MANIFEST OK: every PDF is accounted for.")

    return 1 if (missing_row or missing_file or bad_status or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
