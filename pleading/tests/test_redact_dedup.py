"""Two separate hits on one line stay two redaction boxes.

``_deduplicate_rects`` collapses the duplicate rects an OCR-layered PDF
returns for one visible phrase. It once sorted on a rounded y0 and
merged on a one-sided ``r.x0 <= cur.x1`` test, so a hit far to the
right could precede a duplicate on the left and the merged box spanned
everything between them, blanking unrelated words. Synthetic text only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fitz  # pymupdf

PLEADING_DIR = Path(__file__).resolve().parent.parent
if str(PLEADING_DIR) not in sys.path:
    sys.path.insert(0, str(PLEADING_DIR))

from redact_pdf import _deduplicate_rects  # noqa: E402


def test_two_far_apart_hits_on_one_line_stay_separate():
    left = fitz.Rect(100, 200.0, 140, 212.0)
    right = fitz.Rect(400, 200.0, 440, 212.0)
    out = _deduplicate_rects([right, left])
    assert out == [left, right]


def test_jittered_y0_does_not_bridge_the_gap():
    # The right-hand hit sits a hair higher, so a rounded-y0 sort put it
    # first; the left duplicate then "touched" it and the merge spanned
    # 100..440.
    right = fitz.Rect(400, 200.0, 440, 212.0)
    left = fitz.Rect(100, 200.2, 140, 212.2)
    left_dup = fitz.Rect(100.5, 200.0, 140.5, 212.0)
    out = _deduplicate_rects([left, right, left_dup])
    assert len(out) == 2
    assert out[0].x0 == 100 and out[0].x1 == 140.5
    assert out[1].x0 == 400 and out[1].x1 == 440
    assert all(r.width < 50 for r in out)


def test_overlapping_and_touching_duplicates_still_merge():
    a = fitz.Rect(100, 200, 140, 212)
    b = fitz.Rect(120, 200.5, 160, 212.5)   # overlaps a
    c = fitz.Rect(162, 200, 180, 212)       # within x_gap_tol of b
    out = _deduplicate_rects([c, a, b])
    assert len(out) == 1
    assert out[0].x0 == 100 and out[0].x1 == 180


def test_hits_on_different_lines_never_merge():
    top = fitz.Rect(100, 200, 140, 212)
    below = fitz.Rect(100, 230, 140, 242)
    assert _deduplicate_rects([below, top]) == [top, below]


def test_redact_clause_leaves_words_between_two_hits(tmp_path):
    """End to end: the words between two hits on one line survive."""
    src = tmp_path / "source.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 200), "alpha keep these middle words alpha",
                     fontsize=11)
    doc.save(str(src))
    doc.close()
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "source_pdf": "source.pdf",
        "output_pdf": "redacted.pdf",
        "redactions": [{
            "type": "redact_clause",
            "description": "remove both occurrences of the token",
            "search_text": "alpha",
            "label": "",
        }],
    }))
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "redact_pdf.py"), str(cfg)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "2 hits" in proc.stdout
    out = fitz.open(str(tmp_path / "redacted.pdf"))
    text = out[0].get_text()
    out.close()
    assert "alpha" not in text
    assert "keep these middle words" in text
