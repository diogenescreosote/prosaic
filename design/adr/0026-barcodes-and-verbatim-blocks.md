# 0026 — Barcodes at physical module size; verbatim fixed-width blocks

**Status:** accepted (2026-08)

## Context
The QR block shipped as a one-format feature sized in grid lines, and
the estate templates carried their armored key blocks in fenced code
blocks the parser does not implement — so the fences rendered
literally, the typographic pass turned the `-----` armor headers into
em dashes, and the proportional font rewrapped the base64. A key
block that survives printing only as a picture of corruption defeats
the purpose of printing it. Two lessons: machine-readable symbols
should be specified by symbology and physical geometry, not display
convenience; and verbatim content needs a construct whose contract is
verbatim.

## Decision
1. **`\barcode{format}{payload}{caption}`** (and `\barcodefile` for
   file payloads) replaces the QR-specific macros. Formats: `qr`
   (qrencode, as before), `code128` and `pdf417` (zint, declared
   optional in the manifest). Symbols print at
   **0.75 mm modules** (qr, code128; the GS1 general-distribution
   neighborhood) or **0.5 mm** (pdf417, whose stacked rows tolerate
   less X-dimension), and are scaled up until the smaller side
   reaches **40 mm** — sized for recorder-office scanners and
   camscanned nearly-flat paper — scaled down only when wider than
   the text column. PDF417 targets a **3:1 width:height
   ratio** (its handheld-scanner sweet spot), found by searching
   zint's column count; a symbol at the target that would overflow
   the column is capped at column width. Payloads reach generators
   via stdin or a temp file, never argv.
2. **`\fixedwidth{ ... }`** is the verbatim construct: opened and
   closed on their own lines, every interior line renders monospace
   exactly as written — collected before comment stripping and
   exempt from every typographic substitution. Fenced code blocks
   remain unsupported; the spec now says so and points here. The
   size fits the longest line to the column (10 pt floor 6 pt), so a
   64-column armor block fits letter geometry without wrapping.
3. **Anchored keys print three ways, redundantly**: armored text
   (fixedwidth), the gpg fingerprint on its own fixedwidth line
   between armor and symbol, and the QR. Fingerprint checking is the
   fastest human-grade verification; the armor is the recoverable
   worst case; the symbol is the no-typing path.

## Consequences
The estate templates and the drafting conventions get symbols that
scan at the sizes the specs promise, and armored material that
re-imports from paper. Costs: zint joins the optional dependencies;
PDF417's column search renders the symbol a handful of times
(milliseconds); and fixedwidth blocks deliberately have no styling —
anything needing emphasis is not verbatim content. Amends the QR
feature this replaces; tests moved to pleading/tests/test_barcode.py
with the round-trip discipline intact.
