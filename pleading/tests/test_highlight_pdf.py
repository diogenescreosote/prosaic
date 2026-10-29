"""highlight_pdf.py: phrase highlights that land on the printed words.

The failure this tool answers: a scan whose OCR layer is shifted from
the picture (a deskewed ocrmypdf output) or absent altogether. A text
layer search puts the box where the layer says the words are; the
image mode puts it where the pixels are. So the checks here draw a
phrase at a known position, and ask whether the rectangle each mode
produces overlaps that position, on the born-digital PDF and on a
rasterized copy of it that has no text layer at all.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
TOOL = PLEADING_DIR / "highlight_pdf.py"
sys.path.insert(0, str(PLEADING_DIR))

fitz = pytest.importorskip("fitz")

import highlight_pdf as hp  # noqa: E402

PHRASE = "Jane Roe asked the school to enforce the order"
PAGE_W, PAGE_H = 612, 792
TEXT_X, TEXT_Y = 72, 700       # reportlab baseline, origin bottom-left


@pytest.fixture
def digital_pdf(tmp_path):
    """Three pages; the phrase sits on page 2 at a known position, and a
    decoy sentence sits on the other two."""
    from reportlab.pdfgen import canvas

    path = tmp_path / "digital.pdf"
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    for n in range(1, 4):
        c.setFont("Helvetica", 12)
        c.drawString(TEXT_X, TEXT_Y, f"Page {n} of the sample exhibit.")
        if n == 2:
            c.drawString(TEXT_X, TEXT_Y - 40, PHRASE + " on the following day.")
        else:
            c.drawString(TEXT_X, TEXT_Y - 40, "Nothing of note was said on this page.")
        c.showPage()
    c.save()
    return path


def expected_region() -> "fitz.Rect":
    """Where the phrase was drawn, in PyMuPDF's top-left coordinates."""
    top = PAGE_H - (TEXT_Y - 40) - 12
    return fitz.Rect(TEXT_X, top, TEXT_X + 260, top + 16)


def highlight_rects(pdf: Path, page_index: int = 0) -> list:
    """The yellow filled rectangles drawn into the page content. A
    highlight is never an annotation (see the module docstring of the
    tool), so this reads the content stream, not the annots."""
    with fitz.open(pdf) as doc:
        page = doc[page_index]
        assert not list(page.annots()), "a highlight must be content, not an annotation"
        return [
            d["rect"] for d in page.get_drawings()
            if d.get("fill") and tuple(round(c, 2) for c in d["fill"]) == hp.HIGHLIGHT_FILL
        ]


def run(*args):
    return subprocess.run(
        [sys.executable, str(TOOL), *map(str, args)],
        capture_output=True, text=True,
    )


def test_text_mode_highlights_where_the_text_was_drawn(digital_pdf, tmp_path):
    out = tmp_path / "out.pdf"
    proc = run(digital_pdf, out, "--phrase", PHRASE, "--mode", "text")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "page 2 (source page 2): 1 highlight (text)" in proc.stdout
    rects = highlight_rects(out, 1)
    assert len(rects) == 1
    assert rects[0].intersects(expected_region()), (rects[0], expected_region())
    assert not highlight_rects(out, 0) and not highlight_rects(out, 2)


def test_highlight_is_drawn_into_the_content_not_an_annotation(digital_pdf, tmp_path):
    """The renderer imports exhibit pages with pypdf and scales each into
    its box; an annotation does not follow that transform, so a packet
    built from an annotated excerpt had every box a line off the words.
    The highlight must therefore live in the content stream."""
    out = tmp_path / "out.pdf"
    proc = run(digital_pdf, out, "--phrase", PHRASE, "--mode", "text")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with fitz.open(out) as doc:
        page = doc[1]
        assert not list(page.annots())
        stream = page.read_contents()
        assert b" re" in stream and b"f" in stream, "no filled rectangle in the content"
        drawn = [
            d for d in page.get_drawings()
            if d.get("fill") and tuple(round(c, 2) for c in d["fill"]) == hp.HIGHLIGHT_FILL
        ]
        assert len(drawn) == 1
        assert drawn[0]["rect"].intersects(expected_region())
        assert 0 < drawn[0]["fill_opacity"] < 1, "translucent, so the words stay legible"
        # the words under the box are still there and still searchable
        assert page.search_for(PHRASE)

    # and the box survives a pypdf import with a scale-and-center
    # transform, which is what the pleading renderer does to an exhibit
    from pypdf import PdfReader, PdfWriter, Transformation

    reader = PdfReader(str(out))
    writer = PdfWriter()
    src_page = reader.pages[1]
    box = writer.add_blank_page(width=PAGE_W, height=PAGE_H)
    box.merge_transformed_page(src_page, Transformation().scale(0.8).translate(61, 79))
    scaled = tmp_path / "scaled.pdf"
    with open(scaled, "wb") as fh:
        writer.write(fh)
    with fitz.open(scaled) as doc:
        page = doc[0]
        drawn = [
            d for d in page.get_drawings()
            if d.get("fill") and tuple(round(c, 2) for c in d["fill"]) == hp.HIGHLIGHT_FILL
        ]
        assert len(drawn) == 1
        words = page.search_for(PHRASE)
        assert words and drawn[0]["rect"].intersects(words[0]), (drawn[0]["rect"], words[0])


@pytest.mark.skipif(shutil.which("tesseract") is None,
                    reason="tesseract binary not installed; image mode needs it")
def test_image_mode_highlights_the_pixels_on_a_scan(digital_pdf, tmp_path):
    scan = tmp_path / "scan.pdf"
    with fitz.open(digital_pdf) as src, fitz.open() as dst:
        for page in src:
            pix = page.get_pixmap(dpi=200)
            new = dst.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, pixmap=pix)
        dst.save(scan)
    with fitz.open(scan) as doc:
        assert not doc[1].get_text().strip(), "the rasterized copy must have no text layer"

    out = tmp_path / "out.pdf"
    proc = run(scan, out, "--phrase", PHRASE, "--mode", "image")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "page 2 (source page 2): 1 highlight (image)" in proc.stdout
    rects = highlight_rects(out, 1)
    assert len(rects) == 1
    assert rects[0].intersects(expected_region()), (rects[0], expected_region())

    # auto mode reaches the same answer on a page with no text layer
    out2 = tmp_path / "out_auto.pdf"
    proc = run(scan, out2, "--phrase", PHRASE)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert highlight_rects(out2, 1)[0].intersects(expected_region())


def test_page_selection_yields_an_excerpt(digital_pdf, tmp_path):
    out = tmp_path / "excerpt.pdf"
    proc = run(digital_pdf, out, "--pages", "2-3", "--phrase", PHRASE, "--mode", "text")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with fitz.open(out) as doc:
        assert doc.page_count == 2
        assert "Page 2 of" in doc[0].get_text()
        assert "Page 3 of" in doc[1].get_text()
    assert "page 1 (source page 2): 1 highlight (text)" in proc.stdout
    assert "wrote" in proc.stdout and "2 pages" in proc.stdout
    assert highlight_rects(out, 0)


def test_unmatched_phrase_is_reported_and_exits_2(digital_pdf, tmp_path):
    out = tmp_path / "out.pdf"
    proc = run(digital_pdf, out, "--phrase", PHRASE, "--phrase", "no such words here",
               "--mode", "text")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "NOT FOUND" in proc.stdout
    assert "no such words here" in proc.stdout
    assert PHRASE not in proc.stdout.split("NOT FOUND", 1)[1]
    assert out.exists(), "the output is still written so the hits can be inspected"


def test_same_input_and_output_path_is_refused(digital_pdf):
    before = digital_pdf.read_bytes()
    proc = run(digital_pdf, digital_pdf, "--phrase", PHRASE)
    assert proc.returncode == 1
    assert "never modified" in proc.stderr
    assert digital_pdf.read_bytes() == before


def test_bad_page_spec_is_an_error(digital_pdf, tmp_path):
    proc = run(digital_pdf, tmp_path / "x.pdf", "--pages", "9", "--phrase", PHRASE)
    assert proc.returncode == 1
    assert "page 9 does not exist" in proc.stderr


# --- the matcher, on synthetic OCR output --------------------------------

def _word(t, line=("1", "1", "1"), x=0):
    return hp.Word(hp.norm(t), [(line, fitz.Rect(x, 0, x + 10, 10))])


def test_matcher_skips_interleaved_line_numbers():
    # Pleading paper: the line number "12" lands between two words of a
    # sentence that wraps, and the margin rule is read as a stray "l".
    words = [_word(t) for t in ["asked", "the", "school", "12", "l", "to", "enforce", "the", "order"]]
    hits = hp.find_phrase(words, "school to enforce the order")
    assert len(hits) == 1
    assert [w.t for w in hits[0]] == ["school", "to", "enforce", "the", "order"]


def test_matcher_does_not_skip_real_words():
    words = [_word(t) for t in ["school", "never", "to", "enforce"]]
    assert hp.find_phrase(words, "school to enforce") == []


def test_matcher_allows_prefix_on_long_tokens_only():
    assert hp.tokens_match("superintend", "superintendent")
    assert hp.tokens_match("superintendent", "superintend")
    assert not hp.tokens_match("th", "therapist")
    assert not hp.tokens_match("the", "therapist")


def test_parse_tsv_joins_a_word_hyphenated_across_lines():
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [
        header,
        "5\t1\t1\t1\t1\t1\t10\t10\t40\t10\t90\tsuper-",
        "5\t1\t1\t1\t2\t1\t10\t30\t60\t10\t90\tintendent",
        "5\t1\t1\t1\t2\t2\t80\t30\t30\t10\t90\tsaid",
    ]
    words = hp.parse_tsv("\n".join(rows), fitz.Matrix(1, 1))
    assert [w.t for w in words] == ["superintendent", "said"]
    hits = hp.find_phrase(words, "superintendent said")
    assert len(hits) == 1
    assert len(hp.line_rects(hits[0])) == 2, "one rectangle per printed line"


def test_parse_pages_follows_the_spec_syntax():
    assert hp.parse_pages(None, 5) == [0, 1, 2, 3, 4]
    assert hp.parse_pages("1,4-5", 8) == [0, 3, 4]
    assert hp.parse_pages("3-", 5) == [2, 3, 4]
    assert hp.parse_pages("-2", 5) == [0, 1]
    with pytest.raises(ValueError):
        hp.parse_pages("5-3", 8)
    with pytest.raises(ValueError):
        hp.parse_pages("0", 8)
