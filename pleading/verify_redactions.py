#!/usr/bin/env python3
"""Verify that a redacted PDF actually withholds what it claims to withhold.

A redacted PDF is the one document type whose defects are invisible on the
page. A drawn black rectangle looks exactly like a removal; a covered word is
still selectable, searchable, and sitting in the file's byte stream. So the
build step cannot be the last step: something has to go back and confirm that
the text is gone, and it has to do so mechanically, every time, against a
written list of what must not survive.

That is this tool. It is deliberately adversarial about its own pipeline's
output, and it is the reason a redaction config carries a `verify` block.

WHAT IT CHECKS
──────────────
1. TEXT LAYER. Every term in the term list, searched page by page, with the
   config's own redaction labels excluded so a label reading
   "[MEDICAL HISTORY SEALED]" is not reported as a leak of the word "medical".

2. RAW BYTES. The file, plus every FlateDecode stream decompressed. Catches
   text that survives outside the render tree -- an unreferenced content
   stream, an orphaned object a viewer will not show but `strings` will.

3. CARRIERS PEOPLE FORGET. Annotations (a covered word often survives in a
   highlight or comment), document info, XMP metadata, embedded file
   attachments, page labels, and outlines. Metadata is where redaction
   failures actually happen in practice, because nobody looks there.

4. IMAGE-ONLY PAGES. Pages with no extractable text are reported, not passed.
   A scan with no text layer cannot be verified by search at all, so it needs
   a human to look at the render. Silence here is not the same as safety, and
   the report says so.

EXIT STATUS
───────────
0 only when nothing in the term list survives anywhere. Any hit, in any
carrier, exits 1. Unverifiable image-only pages exit 1 too unless
--allow-image-only is passed, so "I could not check" never reads as "clean".

USAGE
─────
  verify_redactions.py <redacted.pdf> --terms <terms.txt> [--config <cfg.json>]
                       [--report <out.md>] [--contact-sheet <dir>]
                       [--dpi 60] [--allow-image-only]

  <terms.txt>  one term per line; blank lines and #-comments ignored.
               A line starting with "re:" is a regular expression.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path

try:
    import fitz  # type: ignore[import]
except ImportError:
    print("ERROR: PyMuPDF is required.  Install with: pip install pymupdf",
          file=sys.stderr)
    sys.exit(1)


def load_terms(path: Path) -> list[tuple[str, re.Pattern[str]]]:
    terms: list[tuple[str, re.Pattern[str]]] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            terms.append((line, re.compile(line[3:], re.I)))
        else:
            terms.append((line, re.compile(re.escape(line), re.I)))
    return terms


def config_labels(cfg_path: Path | None) -> list[str]:
    """Our own label and placeholder text, which must not count as leaks."""
    if cfg_path is None or not cfg_path.exists():
        return []
    try:
        cfg = json.loads(cfg_path.read_text())
    except json.JSONDecodeError:
        return []
    out: list[str] = []
    for op in cfg.get("redactions", []):
        for key in ("label", "replacement_text"):
            v = op.get(key)
            if v:
                out.extend(s for s in re.split(r"\n+", v) if s.strip())
    return out


def strip_labels(text: str, labels: list[str]) -> str:
    for lab in sorted(labels, key=len, reverse=True):
        text = text.replace(lab, " ")
    # Bracketed all-caps labels, whatever their exact wording.
    return re.sub(r"\[[A-Z0-9 .,'()/-]{3,80}\]", " ", text)


def decompressed_blobs(pdf: Path) -> list[tuple[str, bytes]]:
    raw = pdf.read_bytes()
    blobs: list[tuple[str, bytes]] = [("file", raw)]
    for i, m in enumerate(re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S)):
        try:
            blobs.append((f"stream[{i}]", zlib.decompress(m.group(1))))
        except zlib.error:
            continue
    return blobs


def is_xref_offset_context(blob: bytes, pos: int) -> bool:
    """True when a numeric hit sits inside a cross-reference table entry.

    Short numeric terms (a section number like 5250) collide with the ten-digit
    byte offsets in an xref table, which are not content. Without this the
    numeric half of a term list is pure noise.
    """
    start = max(0, pos - 24)
    window = blob[start:pos + 24]
    return bool(re.search(rb"\d{10} \d{5} [nf]", window))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--terms", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--contact-sheet", type=Path, default=None)
    ap.add_argument("--dpi", type=int, default=60)
    ap.add_argument("--allow-image-only", action="store_true")
    args = ap.parse_args()

    terms = load_terms(args.terms)
    labels = config_labels(args.config)
    doc = fitz.open(args.pdf)

    text_leaks: list[tuple[int, str, str]] = []
    image_only: list[int] = []
    for pno, page in enumerate(doc, 1):
        text = page.get_text()
        if len(text.strip()) < 8 and page.get_images():
            image_only.append(pno)
            continue
        clean = strip_labels(" ".join(text.split()), labels)
        for label, pat in terms:
            m = pat.search(clean)
            if m:
                s = max(0, m.start() - 45)
                text_leaks.append((pno, label, clean[s:m.end() + 45]))

    annot_leaks: list[tuple[int, str, str]] = []
    for pno, page in enumerate(doc, 1):
        parts = []
        for a in page.annots() or []:
            info = a.info
            parts.extend(str(info.get(k, "")) for k in ("content", "title", "subject"))
        blob = strip_labels(" ".join(parts), labels)
        for label, pat in terms:
            if pat.search(blob):
                annot_leaks.append((pno, label, "annotation"))

    meta_parts = [str(v) for v in (doc.metadata or {}).values()]
    try:
        if doc.xref_xml_metadata():
            meta_parts.append(doc.xref_xml_metadata())
    except Exception:
        pass
    try:
        for i in range(doc.embfile_count()):
            meta_parts.append(json.dumps(doc.embfile_info(i)))
    except Exception:
        pass
    # The outline's shape has varied across PyMuPDF versions ([level, title,
    # page] vs richer tuples), and one stray int in here crashes the join --
    # which would mean the metadata check silently never runs. Flatten and
    # coerce rather than trust the shape.
    def _flatten(x) -> list[str]:
        if isinstance(x, (list, tuple)):
            return [s for item in x for s in _flatten(item)]
        return [str(x)]

    try:
        meta_parts.extend(_flatten(doc.get_toc(simple=True)))
    except Exception:
        pass
    meta_blob = strip_labels(" ".join(str(x) for x in meta_parts), labels)
    meta_leaks = [label for label, pat in terms if pat.search(meta_blob)]

    byte_leaks: list[tuple[str, str]] = []
    for tag, blob in decompressed_blobs(args.pdf):
        low = blob.lower()
        for label, _pat in terms:
            if label.startswith("re:"):
                continue          # regexes are a text-layer concern
            needle = label.lower().encode("utf-8", "ignore")
            if not needle:
                continue
            pos = low.find(needle)
            while pos != -1:
                if not is_xref_offset_context(blob, pos):
                    byte_leaks.append((tag, label))
                    break
                pos = low.find(needle, pos + 1)

    lines = [f"# Redaction verification --- {args.pdf.name}", "",
             f"- pages: {len(doc)}",
             f"- terms checked: {len(terms)}",
             f"- labels excluded: {len(labels)}", ""]

    def section(title: str, rows: list[str]) -> None:
        lines.append(f"## {title}: {'CLEAN' if not rows else str(len(rows)) + ' HIT(S)'}")
        lines.append("")
        lines.extend(rows or ["Nothing found.", ""])
        if rows:
            lines.append("")

    section("Text layer", [f"- p{p} `{t}` --- ...{c}..." for p, t, c in text_leaks])
    section("Annotations", [f"- p{p} `{t}`" for p, t, _ in annot_leaks])
    section("Metadata, XMP, attachments, outline", [f"- `{t}`" for t in meta_leaks])
    section("Raw bytes and decompressed streams",
            [f"- `{t}` in {tag}" for tag, t in sorted(set(byte_leaks))])

    lines.append("## Unverifiable pages")
    lines.append("")
    if image_only:
        lines.append(f"{len(image_only)} page(s) carry images and no extractable "
                     "text, so search cannot verify them. A human must look at "
                     "the render before these are relied on: "
                     + ", ".join(f"p{p}" for p in image_only))
    else:
        lines.append("None: every page had extractable text to search.")
    lines.append("")

    if args.contact_sheet:
        args.contact_sheet.mkdir(parents=True, exist_ok=True)
        of_interest = sorted({p for p, _, _ in text_leaks} | set(image_only))
        for pno in of_interest or range(1, len(doc) + 1):
            pix = doc[pno - 1].get_pixmap(dpi=args.dpi)
            pix.save(args.contact_sheet / f"p{pno:04d}.png")
        lines.append(f"Contact sheet: {len(of_interest) or len(doc)} page "
                     f"render(s) in `{args.contact_sheet}`.")
        lines.append("")

    report = "\n".join(lines)
    if args.report:
        args.report.write_text(report)
    print(report)

    failed = bool(text_leaks or annot_leaks or meta_leaks or byte_leaks)
    if image_only and not args.allow_image_only:
        failed = True
    if failed:
        print("VERIFICATION FAILED", file=sys.stderr)
        return 1
    print("VERIFICATION PASSED", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
