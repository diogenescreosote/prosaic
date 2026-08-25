"""The reference stamp: a nonce, printed to look like nothing at all.

Per ADR-0036 the stamp is an *index into the audit log*, not a
cryptographic commitment. It cannot be derived from the document's own
hash --- the stamp is inside the file, so a digest-derived stamp would
have to encode the hash of the bytes containing it, which is
self-referential and not computable. Patching a fixed-width placeholder
afterwards does not rescue the idea either, because patching changes the
bytes. So the stamp is a random nonce generated at signing time, and the
log maps nonce to the full digests.

Nobody verifies a stamp; they use it to find a log entry. That makes its
length a legibility decision, and twelve digits (~40 bits) is far more
than a personal log will ever need to disambiguate.

**Format.** It imitates a document-management-system stamp, because that
is the one kind of identifier that appears on legal filings without
anyone reading it:

    4823-9012-3391v1        iManage
    #12345678v1             Litera / Workshare

The formal feature worth copying is that real DMS references are
*numeric* --- they are database keys. A mixed letter-and-digit token like
`A7K4-FB2X-9M3T` carries the visual signature of base32 and reads as
encoded data; pure digit groups read as "our document system did that".
And it is never labelled: "audit log 4823…" announces itself precisely
because of the words in front of it.
"""

from __future__ import annotations

import secrets

import fitz

# Bottom-left first: where DMS stamps actually appear. The alternatives
# are fallbacks for pages whose bottom-left corner is occupied, which on
# Judicial Council forms it usually is (form number, revision date).
_X_FRACTIONS = (0.09, 0.36, 0.62)
_Y_OFFSETS_FROM_BOTTOM = (26.0, 18.0, 34.0, 12.0)

_FONT = "tiro"  # Times-Roman: the body serif, not a monospace
_SIZE = 6.0
_GREY = (0.45, 0.45, 0.45)

# A pixel darker than this counts as printed ink when testing whether a
# candidate position is clear. Generous: anti-aliased glyph edges and
# scanner grey should not veto an otherwise empty margin.
_INK_THRESHOLD = 205


def new_nonce(version: int = 1) -> str:
    """A fresh reference, e.g. '4823-9012-3391v1'.

    `secrets` rather than `random`: this is an identifier that ends up in
    a legal record, and a predictable one invites the question of whether
    entries could have been fabricated in sequence.
    """
    digits = f"{secrets.randbelow(10**12):012d}"
    return f"{digits[0:4]}-{digits[4:8]}-{digits[8:12]}v{version}"


def _region_is_clear(page: fitz.Page, rect: fitz.Rect) -> bool:
    """Whether a rectangle contains no printed ink.

    Rasterises just the candidate rectangle rather than reasoning about
    text and drawing objects, which is both simpler and correct for form
    rules, logos and scanned content alike. An empty raster is treated as
    clear.
    """
    try:
        pix = page.get_pixmap(clip=rect, colorspace=fitz.csGRAY, dpi=150)
    except (ValueError, RuntimeError):
        return False
    if not pix.samples:
        return True
    return min(pix.samples) > _INK_THRESHOLD


def apply(doc: fitz.Document, nonce: str) -> list[int]:
    """Stamp every page that has room. Returns the pages skipped.

    Every page, not just the signature page: it is what real DMS stamps
    do, so it is the least conspicuous choice, and it means a page
    extracted from the packet still carries its reference.
    """
    skipped: list[int] = []
    width = fitz.get_text_length(nonce, fontname=_FONT, fontsize=_SIZE)

    for pno, page in enumerate(doc):
        placed = False
        for y_off in _Y_OFFSETS_FROM_BOTTOM:
            for x_frac in _X_FRACTIONS:
                x = page.rect.x0 + page.rect.width * x_frac
                y = page.rect.y1 - y_off
                probe = fitz.Rect(x - 2, y - _SIZE - 2, x + width + 2, y + 3)
                if not (page.rect.contains(probe) and _region_is_clear(page, probe)):
                    continue
                page.insert_text(
                    (x, y),
                    nonce,
                    fontname=_FONT,
                    fontsize=_SIZE,
                    color=_GREY,
                )
                placed = True
                break
            if placed:
                break
        if not placed:
            skipped.append(pno)
    return skipped
