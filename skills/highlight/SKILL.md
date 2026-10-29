---
name: highlight
description: Make a highlighted excerpt of a received PDF - yellow boxes on named phrases, anchored to the printed words by OCR, so a scanned or deskewed document draws the court's eye to the right lines - with highlight_pdf.py, then look at the rendered page. Use when a declaration or brief points the court at particular passages of a long or scanned exhibit and an excerpt "with the ... passages highlighted" is to be attached. Never for redaction; load `redact` for that.
---

# Highlight an exhibit excerpt

A highlighted excerpt tells the court where to look. A box that lands
beside the words it was meant to mark, or on no words at all, does the
opposite. So the boxes are placed by the tool from the phrases you name,
never by hand, and the result is checked by eye on the rendered page.

Highlighting is not redaction. Nothing is removed and nothing is
proved absent; a highlight that covers a name is a highlighted name.
For withholding anything, load `redact`.

## The command

```bash
python3 <prosaic>/pleading/highlight_pdf.py <in.pdf> <out.pdf> \
    --pages 4,10 \
    --phrase "asked the school to enforce the order" \
    --phrase "appearing at the school unannounced"
```

- `<in.pdf>` is the received document, usually under `assets/`. **It is
  never modified**: output always goes to a new path and the tool
  refuses an output path that is the input.
- `<out.pdf>` goes in the matter's exhibits folder (the directory the
  source's `exhibits:` paths resolve from) or `staging/<date>_<topic>/`,
  under a descriptive name that says what it is:
  `long_declaration_pp4_10_highlighted.pdf`, never `out.pdf`.
- `--pages` keeps only the pages named (1-indexed; `1,4-6`, `3-`,
  `-5`); omit it for the whole file. A page that does not exist is an
  error, never clamped.
- `--phrase` repeats, one per passage. Quote the words as printed;
  matching ignores case and punctuation, tolerates a pleading line
  number or stray glyph between two words, and follows a hyphenated
  word across lines.

Each phrase gets one translucent rectangle per printed line it
occupies, **drawn into the page content, not an annotation**: the
renderer scales and centers each exhibit page into its box when it
builds the packet, and annotations do not follow that transform (an
annotated excerpt had every box a line off in the built packet).
Never substitute a viewer's highlight tool or an annotation for the
same reason. Full semantics: `pleading/pleading_markdown_spec.md`,
"Highlighted exhibit excerpts".

## Pick the mode

| Document | `--mode` | Why |
|---|---|---|
| Born-digital PDF (an email render, a filed pleading) | `auto` (default) or `text` | the text layer is exact |
| Image-only scan, no text layer | `auto` | each page is rendered and OCR'd |
| Scan that ocrmypdf has deskewed, OCR layer offset from the picture | **`image`** | the layer finds the phrase in the wrong place; only the picture is right |

`auto` falls back to the image only where the text layer has no page
or no match. A deskewed scan's layer *does* match, so `auto` boxes the
wrong spot: use `--mode image` for any `_ocr.pdf` sibling or any scan
whose highlights sit beside the words. `--dpi` (default 200) is the
render resolution for OCR; raise it for small print.

## Read the report, then look

The report counts the rectangles on each output page and names the
mode that placed them. Then:

- **Exit 2** means a phrase matched on no selected page, listed under
  `NOT FOUND`. The output is written for the phrases that did land, but
  do not attach it. Open the source page, fix the phrase (OCR may read
  the words differently than you did) or the `--pages`, and run again
  until the exit is 0.
- **Exit 1** is an error: a bad page spec, an output path that is the
  input, a missing tesseract.
- **Exit 0 is not the end.** Render the output and look at every page:
  `pdftoppm -r 60 -png <out.pdf> <dir>/page` and read the images, or
  `sc open <out.pdf>`. Each box must sit on the words named, nothing
  more. A box on the wrong line on a scan means `--mode image`.

## Attach it

Attach the output as an ordinary exhibit `path`; its page citations
follow the excerpt's own numbering. The exhibit's `title` in the
source front matter says what was done to it, so the court is not
handed a marked document unannounced:

```yaml
exhibits:
  - shortname: "long_declaration_excerpt"
    title: "Excerpt (pp. 4, 10) of the Declaration of Dana Whitfield, with the school-enforcement passages highlighted"
    path: "exhibits/long_declaration_pp4_10_highlighted.pdf"
```

Say in what you report which phrases were placed, by which mode, that
you looked at the rendered pages, and where the unmodified original is.
