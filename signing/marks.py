"""Turning a scanned signature into ink that can be drawn on a PDF.

Two things here are easy to get wrong in ways that look forged.

**Background removal.** The obvious approach --- make white pixels
transparent --- produces a hard-edged, jagged mark with a halo, because
the edges of a scanned pen stroke are anti-aliased to *light grey*, not
white, and JPEG compression adds noise around them. Instead this module
reads luminance as an alpha ramp: dark pixels become opaque ink, light
pixels become transparent, and the greys in between stay proportionally
translucent. Edges stay smooth, and ink colour becomes a free parameter
(blue reads as wet-signed; black reads as photocopied).

**Aspect ratio.** Judicial Council signature widgets are wide and short.
Fitting a natural-proportion cursive mark into one either overflows or
squashes it, and a horizontally compressed signature is the one artifact
a document examiner would remark on. So scaling is always proportional,
driven by height, and the mark is allowed to overhang its nominal box
horizontally --- which is what real signatures do to real ruled lines.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .base import SignerError

# Below this luminance a pixel is fully opaque ink; above the second
# value it is fully transparent. Between them alpha ramps linearly. The
# window is deliberately wide at the top: scanner backgrounds are rarely
# pure white, and clipping them to transparent is what removes the grey
# wash without also eating the faint end of a pen stroke.
_INK_BELOW = 60
_PAPER_ABOVE = 205


@dataclass(frozen=True)
class Mark:
    """A signature prepared for drawing: RGBA bytes plus its proportions."""

    png: bytes
    width_px: int
    height_px: int

    @property
    def aspect(self) -> float:
        """Width divided by height. Never varied when placing."""
        return self.width_px / self.height_px


def _alpha_from_luminance(img: Image.Image) -> Image.Image:
    grey = img.convert("L")
    span = _PAPER_ABOVE - _INK_BELOW

    def ramp(v: int) -> int:
        if v <= _INK_BELOW:
            return 255
        if v >= _PAPER_ABOVE:
            return 0
        return int(round(255 * (_PAPER_ABOVE - v) / span))

    return grey.point([ramp(v) for v in range(256)])


def _trim_to_ink(alpha: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of anything not fully transparent.

    Cropping to the ink matters for placement: a scan usually carries a
    wide margin of paper, and placing the *image* on the signature line
    would float the visible stroke somewhere above it.
    """
    return alpha.getbbox()


def _open(path: Path, pdf_dpi: int) -> Image.Image:
    """A signature source as a PIL image.

    PDF is a first-class source, and often the best one: a signature
    captured on a tablet or traced in a drawing program is *vector*, so it
    can be rendered at whatever resolution the page needs with no loss,
    and it carries genuine transparency rather than a photographed sheet
    of paper. Rendering with alpha keeps that --- there is nothing to key
    out, because unpainted areas were never painted.
    """
    if path.suffix.lower() == ".pdf":
        import fitz

        with fitz.open(path) as doc:
            if doc.page_count == 0:
                raise SignerError(f"{path} has no pages")
            pix = doc[0].get_pixmap(dpi=pdf_dpi, alpha=True)
            return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    try:
        img = Image.open(path)
        img.load()
        return img
    except OSError as exc:
        raise SignerError(f"cannot read signature image {path}: {exc}") from None


def prepare(
    path: Path,
    ink: tuple[int, int, int] = (16, 24, 92),
    max_dimension: int = 2000,
    pdf_dpi: int = 1200,
) -> Mark:
    """Load a signature source and return drawable RGBA ink.

    A source that already carries real transparency keeps **its own
    colour**: it was prepared deliberately, and a signature's ink colour
    is part of what makes it that person's signature. `ink` applies only
    when alpha had to be derived from luminance --- i.e. a scan of paper,
    where the source is effectively greyscale anyway. It defaults to a
    dark navy, which reads as a pen and survives black-and-white
    photocopying.
    """
    img = _open(path, pdf_dpi)

    with img:
        # Transparency that actually varies means the background is
        # already absent; re-deriving alpha from luminance would treat
        # those transparent regions as white paper and paint over them.
        if img.mode in ("RGBA", "LA") and _has_real_alpha(img):
            rgba = img.convert("RGBA")
        else:
            alpha = _alpha_from_luminance(img)
            rgba = Image.new("RGBA", alpha.size, (*ink, 255))
            rgba.putalpha(alpha)

        box = _trim_to_ink(rgba.getchannel("A"))
        if box is None:
            raise SignerError(
                f"{path} appears blank: no pixel dark enough to be ink. "
                "Check that it is a signature and not an empty page."
            )
        rgba = rgba.crop(box)

        if max(rgba.size) > max_dimension:
            scale = max_dimension / max(rgba.size)
            new = (max(1, int(rgba.width * scale)), max(1, int(rgba.height * scale)))
            rgba = rgba.resize(new, Image.LANCZOS)

        buf = io.BytesIO()
        rgba.save(buf, format="PNG", optimize=True)
        return Mark(png=buf.getvalue(), width_px=rgba.width, height_px=rgba.height)


def _has_real_alpha(img: Image.Image) -> bool:
    """Whether an alpha channel actually varies.

    Many PNGs are RGBA with a fully opaque alpha, which carries no
    background information at all --- treating those as pre-prepared
    would paste a white rectangle onto the page.
    """
    a = img.convert("RGBA").getchannel("A")
    lo, hi = a.getextrema()
    return lo < 250


def place_rect(
    mark: Mark,
    rule: tuple[float, float, float, float],
    target_height: float = 34.0,
    overhang: float = 1.15,
    sit_below: float = 3.0,
) -> tuple[float, float, float, float]:
    """Where to draw `mark` so it sits on a signature rule like a pen would.

    `rule` is the bounding box of the printed underscore run. A real
    signature rests *on* the line with descenders crossing it, so the
    mark's baseline lands slightly below the rule's top edge, and its
    width is permitted to exceed the rule by `overhang` before being
    scaled down to fit.

    Height drives the scale; width follows from the aspect ratio and is
    never adjusted independently.
    """
    x0, y0, x1, y1 = rule
    rule_width = x1 - x0

    height = target_height
    width = height * mark.aspect
    limit = rule_width * overhang
    if width > limit:
        # Too wide even allowing overhang: shrink proportionally. Height
        # gives way, never the aspect ratio.
        width = limit
        height = width / mark.aspect

    left = x0 + rule_width * 0.04
    bottom = y1 + sit_below
    return (left, bottom - height, left + width, bottom)
