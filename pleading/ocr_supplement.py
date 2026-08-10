#!/usr/bin/env python3
"""OCR-supplement a PDF for the lawyering workspace.

Embeds a searchable text layer on the pages of a PDF that LACK one, while
leaving any page that already has text (or an existing OCR layer)
completely untouched -- it supplements, it never replaces. Writes a new
file named `<stem>_ocr.pdf` next to the source (or into an output dir),
and never modifies the original.

Convention (see the workspace CLAUDE.md "OCR on triage" section): whenever
a PDF is triaged out of `inbox/` into `assets/`, run this to produce the
`_ocr` sibling, and store the original and the `_ocr` version side by
side. Then update `assets/INDEX.md`.

Mechanism: `ocrmypdf --skip-text`, which OCRs only pages that have no text
and passes text-bearing pages through unchanged. This is what guarantees
existing OCR/text is never overwritten.

Usage:
    python3 ocr_supplement.py <input.pdf> [output_dir] [--force]

  output_dir  where to write <stem>_ocr.pdf (default: alongside input)
  --force     write the _ocr copy even if every page already has text
              (default: skip, and say so, since the copy would be
              text-identical to the original and just waste space)
"""
import os
import subprocess
import sys

import fitz  # PyMuPDF


def pages_without_text(path):
    doc = fitz.open(path)
    try:
        blank = sum(1 for p in doc if not p.get_text().strip())
        return blank, doc.page_count
    finally:
        doc.close()


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    force = "--force" in args
    positional = [a for a in args if not a.startswith("--")]
    src = positional[0]
    if not os.path.isfile(src):
        sys.exit(f"no such file: {src}")
    outdir = positional[1] if len(positional) > 1 else (os.path.dirname(src) or ".")
    stem = os.path.splitext(os.path.basename(src))[0]
    if stem.endswith("_ocr"):
        sys.exit(f"refusing to OCR an already-_ocr file: {src}")
    out = os.path.join(outdir, stem + "_ocr.pdf")

    blank, total = pages_without_text(src)
    if blank == 0 and not force:
        print(f"[skip] {src}: all {total} page(s) already have a text layer; "
              f"no _ocr version needed (use --force to make one anyway).")
        return

    print(f"[ocr]  {src}: {blank}/{total} page(s) lack text; "
          f"OCR-supplementing (existing text preserved) -> {out}")
    # --skip-text: only OCR pages with no text; never touch existing text.
    subprocess.run(["ocrmypdf", "--skip-text", "-l", "eng", src, out], check=True)
    print(f"[done] {out}")


if __name__ == "__main__":
    main()
