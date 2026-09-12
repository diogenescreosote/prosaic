#!/usr/bin/env python3
"""Find court-filed papers the record holds but `pleadings/` does not.

WHAT THIS CATCHES
─────────────────
Filed documents reach a matter through more than one door: counsel serves
a filed copy by email, the e-filing system (Odyssey eFile, whatever EFSP
fronts it) mails an acceptance with the stamped copy attached or behind a
link, the clerk transmits an order. Triage routes the *bytes* into `assets/` and the
*facts* into the knowledge vault -- but nothing forces the third step,
a `pleadings/` copy with a MANIFEST row. A filed order can therefore sit
in `assets/gmail/attachments/` for weeks while `pleadings/` -- the record
of what the court has -- knows nothing about it.

This tool scans every text sidecar under `derived/text/` for the indicia
of a court-filed or court-issued paper (e-file stamps, clerk stamps,
judicial-officer signature blocks) and reports the documents not
represented in `pleadings/`. It also flags e-filing acceptance emails
whose stamped copies were never captured at all -- portal links expire,
so those need a human promptly.

It REPORTS ONLY. Provenance is recorded by a human at intake (see
pleadings_manifest.py); a scanner cannot decide what the court has, and
this one never moves, copies, or renames anything. Its output is a list
of candidates for a human to confirm or dismiss.

DUPLICATE HANDLING
──────────────────
The same filed paper often arrives several times (served copy, portal
copy, a re-export of a damaged thread). Rules, in order:

1. BYTE-IDENTITY DEDUPES. Candidates are grouped by SHA-256 of the
   original PDF. A candidate whose bytes match any file in `pleadings/`
   is represented -- not re-flagged. Multiple identical copies across
   the record collapse to one report row listing every path.
2. MANIFEST HASH CITATIONS COUNT. MANIFEST rows record provenance
   hashes as `SHA-256 \\`xxxxxxxx…\\``. A candidate whose hash starts
   with a cited prefix (8+ hex chars) is represented, wherever the
   bytes live.
3. TEXT SIMILARITY NEVER SUPPRESSES. Two stamped copies with different
   bytes may be different papers -- a corrected filing, an amended
   order, a superseded version -- and both must surface. When a
   candidate's normalized sidecar text matches a `pleadings/` document,
   that is printed as a hint ("same text as ...") on the row, and the
   row still appears. Byte-identity is the only automatic silencer.
4. HUMAN DISMISSALS ARE RECORDED, NOT REPEATED. A candidate a human
   has judged not to belong in `pleadings/` (an exhibit copy of an
   order the folder already holds, a records production that merely
   contains an order) is written to `pleadings/SCAN_DISMISSALS.md`:
   one line per dismissal, `<sha256-prefix>  <reason>`, prefix 12+ hex
   chars. Dismissed hashes stop being reported; the file is the audit
   trail of what was judged and why. Dismissal is by hash, so a new
   scan of the same bytes stays quiet but a DIFFERENT copy of a
   similar paper still surfaces.

USAGE
    python3 pleadings_scan.py <matter_dir>

Exit 0: nothing unrepresented. Exit 1: candidates need human review.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

# Indicia of a court-filed or court-issued paper, checked against the
# extracted text of each document. Ordered strongest-first; a document
# is a candidate when any signal beyond a bare title match fires.
SIGNALS = [
    ("efiled-stamp", re.compile(r"electronically\s+filed", re.I)),
    ("clerk-stamp", re.compile(
        r"clerk\s+of\s+the\s+court[^\n]{0,120}\n?[^\n]{0,120}deputy\s+clerk",
        re.I)),
    ("deputy-clerk", re.compile(r"\bdeputy\s+clerk\b", re.I)),
    ("judicial-officer", re.compile(r"\bjudicial\s+officer\b", re.I)),
    ("order-title", re.compile(
        r"\b(order\s+(on|granting|denying|after)|findings\s+and\s+order"
        r"|minute\s+order|notice\s+of\s+entry)\b", re.I)),
]


def is_candidate(hits: set[str]) -> bool:
    """A stamp makes a candidate; weaker signals only in combination.

    `judicial-officer` alone matches the footer label printed on every
    blank Judicial Council form, and `deputy-clerk` alone matches any
    email a clerk ever signed; each is meaningful only next to a title
    or the other. A real filing stamp (`efiled-stamp`, `clerk-stamp`)
    is sufficient by itself.
    """
    if hits & {"efiled-stamp", "clerk-stamp"}:
        return True
    return ("deputy-clerk" in hits
            and hits & {"order-title", "judicial-officer"})

# E-filing acceptance emails. The EFSP front-ends vary; the Odyssey
# eFile platform behind them is what standardizes the acceptance
# notice: an "accepted" disposition naming a Filing ID and/or Envelope
# number, with the stamped copy attached or behind a link. The link
# dies; the flag should not wait for it to.
ACCEPTED = re.compile(r"\baccepted\b", re.I)
EFILE_ID = re.compile(
    r"\b(?:filing\s+id|envelope(?:\s+number)?)[:\s#]{0,3}(\d{6,})", re.I)

# Never pleadings candidates: the matter's own work product (out, src,
# staging, decl_cover_sheets build inputs), blank form stock, reference
# material, pleadings itself, discovery instruments (clerk-issued
# subpoenas live in discovery/ by convention, not pleadings/), and
# processed_files (raw provenance bytes whose record entry is the
# assets/ or discovery/ twin).
SKIP = re.compile(
    r"derived/text/(out|src|staging|reference|pleadings|processed_files"
    r"|discovery)/"
    r"|derived/text/assets/(decl_cover_sheets|forms)/"
    r"|_migration|audit_log")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalized_text(sidecar: Path) -> str:
    """Sidecar body with whitespace and the provenance header collapsed,
    for the similarity *hint* (rule 3) -- never for suppression."""
    body = sidecar.read_text(errors="replace")
    body = re.sub(r"^\[\[\[.*?\]\]\]", "", body, flags=re.S)  # header block
    return re.sub(r"\s+", " ", body).strip().lower()


def original_for(matter: Path, sidecar: Path) -> Path | None:
    """derived/text/<rel>.pdf.txt -> <rel>.pdf (the original bytes)."""
    rel = sidecar.relative_to(matter / "derived" / "text")
    orig = matter / str(rel)[: -len(".txt")]
    return orig if orig.exists() else None


def manifest_hash_prefixes(manifest: Path) -> set[str]:
    if not manifest.exists():
        return set()
    return {m.lower() for m in re.findall(
        r"SHA-256\s*`([0-9a-f]{8,})[`…]", manifest.read_text(), re.I)}


def dismissed_prefixes(pleadings: Path) -> set[str]:
    """Hash prefixes a human has dismissed, from SCAN_DISMISSALS.md."""
    f = pleadings / "SCAN_DISMISSALS.md"
    if not f.exists():
        return set()
    return {m.lower() for m in re.findall(
        r"^\s*`?([0-9a-f]{12,64})`?\s+\S", f.read_text(),
        re.I | re.M)}


def scan(matter: Path) -> int:
    text_root = matter / "derived" / "text"
    pleadings = matter / "pleadings"
    manifest = pleadings / "MANIFEST.md"

    pleading_hashes: dict[str, str] = {}
    pleading_texts: dict[str, str] = {}
    for pdf in sorted(pleadings.glob("*.pdf")):
        pleading_hashes[sha256(pdf)] = pdf.name
        sidecar = text_root / "pleadings" / (pdf.name + ".txt")
        if sidecar.exists():
            pleading_texts[normalized_text(sidecar)] = pdf.name
    cited = manifest_hash_prefixes(manifest)
    dismissed = dismissed_prefixes(pleadings)
    manifest_text = manifest.read_text().lower() if manifest.exists() else ""

    groups: dict[str, dict] = defaultdict(lambda: {"paths": [], "hits": set(),
                                                   "same_text": None})
    acceptances: list[tuple[str, str]] = []

    for sidecar in sorted(text_root.rglob("*.pdf.txt")):
        rel = str(sidecar.relative_to(matter))
        if SKIP.search(rel):
            continue
        text = sidecar.read_text(errors="replace")

        if ACCEPTED.search(text):
            for fid in EFILE_ID.findall(text):
                if fid not in manifest_text:
                    acceptances.append((fid, rel))

        hits = {name for name, rx in SIGNALS if rx.search(text)}
        if not is_candidate(hits):
            continue
        orig = original_for(matter, sidecar)
        if orig is None:
            continue
        digest = sha256(orig)
        if digest in pleading_hashes:          # rule 1: same bytes, done
            continue
        if any(digest.startswith(p) for p in cited):   # rule 2: cited hash
            continue
        if any(digest.startswith(p) for p in dismissed):  # rule 4: judged
            continue
        g = groups[digest]
        g["paths"].append(str(orig.relative_to(matter)))
        g["hits"] |= hits
        g["same_text"] = pleading_texts.get(normalized_text(sidecar))

    status = 0
    if groups:
        status = 1
        print(f"{len(groups)} filed-looking document(s) not represented "
              f"in pleadings/ (confirm or dismiss each -- this tool "
              f"never moves files):")
        for digest, g in sorted(groups.items(), key=lambda kv: kv[1]["paths"]):
            hint = (f"  [same text as pleadings/{g['same_text']} -- "
                    f"different bytes: possibly a corrected or amended "
                    f"version, NOT auto-suppressed]" if g["same_text"] else "")
            print(f"  sha256 {digest[:12]}…  "
                  f"[{','.join(sorted(g['hits']))}]{hint}")
            for p in g["paths"]:
                print(f"    {p}")
    if acceptances:
        status = 1
        seen: set[str] = set()
        print("acceptance email(s) whose Filing ID no MANIFEST row cites "
              "-- capture the stamped copy before the portal link expires:")
        for fid, rel in acceptances:
            if fid in seen:
                continue
            seen.add(fid)
            print(f"  Filing ID {fid}  ({rel})")
    if status == 0:
        print("pleadings scan: every filed-looking document in the record "
              "is represented in pleadings/.")
    return status


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    matter = Path(sys.argv[1]).resolve()
    if not (matter / "derived" / "text").is_dir():
        sys.exit(f"{matter}: no derived/text/ -- run `sc text ensure` first")
    return scan(matter)


if __name__ == "__main__":
    raise SystemExit(main())
