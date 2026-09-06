#!/usr/bin/env python3
"""Page-level read coverage for PDFs being triaged.

The failure this exists to prevent: an agent opens a 40-page filing,
reads the first page and the exhibit list, writes a confident INDEX row,
and never learns that page 31 contains the only mention of a new account
or the only date that moves a deadline. Nothing downstream can detect
that; the row looks exactly like a row written after a real read.

So reading is made mechanical and checkable. Two modes:

    read_coverage.py <path...>            # the coverage table
    read_coverage.py --text <path>        # every page's text, page-marked

`--text` is the one you actually read from. It emits the WHOLE document
with `[[[ page k of N ]]]` markers, so the pages are in context and the
markers prove which ones. Pages the text layer cannot speak for are
emitted as an explicit `<< NO TEXT LAYER >>` marker rather than as
silence -- an empty page and an unextractable page look identical in a
naive dump, and only one of them is safe to skip.

The coverage table classifies each page:

    text        enough extractable text, and no big embedded raster
    garbled     plenty of extractable text with no English function word
                in it. A PDF whose embedded font carries a nonstandard
                encoding extracts as consistent nonsense: the page
                renders perfectly and the text layer is meaningless.
                Nothing about the dump looks wrong, so this is the one
                failure mode a careful reader can still miss. Rasterize
                and read, or OCR with --force-ocr into a new file.

                This one over-flags, deliberately. A page that is all
                labels and numbers -- a tax form's summary page, a
                statement's transaction grid, an invoice's payment
                table, an ID card -- can carry no function word and be
                perfectly readable. Treat `garbled` as "look at this
                page", not as "this page is broken": the cost of a
                false positive is one glance, and the cost of a false
                negative is a document nobody read
    image-bodied  text present, but a raster image covers a large part
                of the page: an email export carrying a screenshot, a
                declaration with a photographed exhibit. The header
                extracts and the body does not, so a naive dump reads
                as complete while the actual content is invisible.
                This is the quietest way to miss a document
    sparse      some text, but little enough that it is probably a scan
                with a caption band, a form with a filled overlay, or a
                page whose body is an image -- OCR it or look at it
    image-only  no text at all, and drawn content present: a scan. OCR
                (`ocr_supplement.py`) or rasterize and look
    blank       no text and nothing drawn: genuinely empty

Exit status is 1 when any page is not fully covered by its text layer,
so a triage pass can gate on it:

    python3 read_coverage.py inbox/*.pdf || echo "OCR needed first"

Usage:
    read_coverage.py [--text] [--json] [--min-chars N] <path...>

  --text        dump page-marked full text instead of the table
  --json        machine-readable table
  --min-chars   chars below which a page counts as `sparse` (default 60)
  --min-image   fraction of page area a raster must cover to make the
                page `image-bodied` (default 0.15)
"""
import json
import os
import sys

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 (the `fitz` alias warns on stdout)
except ImportError:  # older PyMuPDF
    import fitz

DEFAULT_MIN_CHARS = 60
DEFAULT_MIN_IMAGE = 0.15

UNCOVERED = ("image-bodied", "sparse", "image-only", "garbled")

# A page of real English prose or of a filled-in form almost always
# contains at least one of these, in some case. A page of correctly
# extracted text that contains none of them is nearly always a font
# encoding failure rather than a document without common words.
FUNCTION_WORDS = ("the", "and", "for", "of", "to", "in", "is", "on",
                  "you", "that", "with", "not", "this", "or", "by")


def looks_garbled(text):
    low = text.lower()
    return not any(f" {w} " in low or low.startswith(w + " ") for w in FUNCTION_WORDS)


def largest_image_fraction(page):
    """Fraction of the page covered by its biggest embedded raster."""
    area = abs(page.rect.get_area())
    if not area:
        return 0.0
    biggest = 0.0
    for img in page.get_images(full=True):
        try:
            rect = page.get_image_bbox(img)
        except (ValueError, RuntimeError):
            continue
        biggest = max(biggest, abs(rect.get_area()) / area)
    return biggest


def classify(page, min_chars, min_image=DEFAULT_MIN_IMAGE):
    text = page.get_text().strip()
    n = len(text)
    frac = largest_image_fraction(page)
    if n >= min_chars:
        # A page can carry a text header and an image body -- the Gmail
        # export of a screenshotted text thread is the canonical case.
        # Extraction succeeds, so nothing looks wrong, and the content
        # is never read.
        if frac >= min_image:
            return "image-bodied", n
        # ...and a page can extract a great deal of text that means
        # nothing, when the font's encoding is nonstandard.
        if n >= 200 and looks_garbled(text):
            return "garbled", n
        return "text", n
    drawn = bool(page.get_images(full=True)) or bool(page.get_drawings())
    if n == 0:
        return ("image-only" if drawn else "blank"), 0
    return "sparse", n


def survey(path, min_chars, min_image=DEFAULT_MIN_IMAGE):
    doc = fitz.open(path)
    try:
        pages = []
        for i, page in enumerate(doc, 1):
            kind, n = classify(page, min_chars, min_image)
            pages.append({"page": i, "kind": kind, "chars": n})
        return {"path": path, "pages": len(pages), "detail": pages}
    finally:
        doc.close()


def dump_text(path, min_chars, min_image=DEFAULT_MIN_IMAGE):
    doc = fitz.open(path)
    try:
        total = doc.page_count
        print(f"[[[ {os.path.basename(path)} -- {total} page(s) ]]]")
        unread = []
        for i, page in enumerate(doc, 1):
            kind, _ = classify(page, min_chars, min_image)
            print(f"\n[[[ page {i} of {total} ]]]")
            body = page.get_text().strip()
            if kind in ("image-only", "blank"):
                print(f"<< NO TEXT LAYER ({kind}) -- OCR or rasterize this page >>")
                if kind == "image-only":
                    unread.append(i)
            else:
                print(body)
                if kind == "sparse":
                    print(f"<< SPARSE ({len(body)} chars) -- likely a scan or an "
                          f"image-bodied page; OCR or rasterize to confirm >>")
                    unread.append(i)
                elif kind == "garbled":
                    print("<< GARBLED -- the text above extracted cleanly "
                          "but contains no common English word, which "
                          "means the font encoding is nonstandard and the "
                          "text layer is nonsense. The page itself is "
                          "fine: rasterize and read it, or OCR --force >>")
                    unread.append(i)
                elif kind == "image-bodied":
                    print("<< IMAGE-BODIED -- the text above is the page's "
                          "header/footer only; its body is a raster image "
                          "(a screenshot, a photographed exhibit). Extract "
                          "the image and look at it >>")
                    unread.append(i)
        print(f"\n[[[ end {os.path.basename(path)} -- {total} page(s) emitted ]]]")
        if unread:
            print(f"[[[ pages NOT covered by this dump: "
                  f"{', '.join(str(p) for p in unread)} ]]]")
        return not unread
    finally:
        doc.close()


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    as_text = "--text" in args
    as_json = "--json" in args
    min_chars = DEFAULT_MIN_CHARS
    if "--min-chars" in args:
        i = args.index("--min-chars")
        min_chars = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    min_image = DEFAULT_MIN_IMAGE
    if "--min-image" in args:
        i = args.index("--min-image")
        min_image = float(args[i + 1])
        args = args[:i] + args[i + 2:]
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        sys.exit("no input files")

    if as_text:
        ok = True
        for p in paths:
            ok = dump_text(p, min_chars, min_image) and ok
        return 0 if ok else 1

    surveys = [survey(p, min_chars, min_image) for p in paths]
    if as_json:
        print(json.dumps(surveys, indent=2))
    else:
        for s in surveys:
            counts = {}
            for d in s["detail"]:
                counts[d["kind"]] = counts.get(d["kind"], 0) + 1
            summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            print(f"{s['pages']:>4}p  {summary:<44} {s['path']}")
            flagged = [d for d in s["detail"] if d["kind"] in UNCOVERED]
            if flagged:
                pages = ", ".join(f"{d['page']}({d['kind']})" for d in flagged)
                print(f"        needs OCR or eyes: {pages}")
    bad = any(d["kind"] in UNCOVERED for s in surveys for d in s["detail"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
