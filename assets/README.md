# Brand assets

The wordmark is the word `prosaic.` in Courier New Bold with a blinking
terminal cursor. The blink is a hard step (SMIL `calcMode="discrete"`,
1.06s period, 50% duty) because a terminal cursor snaps; a fade would read
as a designed logo rather than a prompt.

| file | use |
| --- | --- |
| `wordmark.svg` / `wordmark-dark.svg` | animated, light and dark, used by the README `<picture>` element |
| `wordmark-static.svg` / `wordmark-static-dark.svg` | no animation, for contexts where motion is unwanted |
| `wordmark.src.svg` | editable source with a live `<text>` element |
| `social-preview.png` | 1280x640 repository social preview |

The committed SVGs carry outlined glyph paths, not text: Courier New is
missing on most Linux and Android systems, and a substituted font shifts
the advance widths so the cursor no longer sits at the end of the word.

To regenerate after editing the source design: extract the glyph outlines
of `prosaic.` from Courier New Bold at 52px with fontTools (`SVGPathPen`
through a `TransformPen` with a y-flip, advancing x by each glyph's width
plus 1px letter-spacing), place the cursor rect 4px after the final
advance, and substitute the resulting path into the `<g>` of each variant.
The PNG uses the same font at 130px via Pillow.
