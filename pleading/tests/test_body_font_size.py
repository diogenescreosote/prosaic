"""body_font_size: a per-document body point size.

Exists for documents a statute requires to be LARGER than house style:
Civil Code section 56.11(c) voids a CMIA medical-records authorization
"in a typeface no smaller than 14-point" unless handwritten. The knob is
bounded (8-18) so a typo cannot render confetti or posters, and a child
markdown exhibit renders in its own subprocess, so a 14-point parent
never bleeds into a 12-point attachment or vice versa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fitz

PLEADING_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PLEADING_DIR / "md_pleading.py"

DOC = """---
doctype: document
paper_title: "AUTHORIZATION FOR RELEASE OF RECORDS INFORMATION"
short_title: "Authorization"
{extra}---
I authorize the disclosure described below, revocable in writing at any time.
"""


def build(md: Path, out: Path):
    return subprocess.run([sys.executable, str(SCRIPT), str(md), str(out)],
                          capture_output=True, text=True)


def body_sizes(pdf: Path) -> set:
    sizes = set()
    for page in fitz.open(pdf):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if "authorize the disclosure" in span["text"]:
                        sizes.add(round(span["size"]))
    return sizes


def test_default_body_is_house_size(tmp_path):
    md = tmp_path / "doc.md"; md.write_text(DOC.format(extra=""))
    out = tmp_path / "doc.pdf"
    assert build(md, out).returncode == 0
    assert body_sizes(out) == {12}


def test_fourteen_point_body(tmp_path):
    md = tmp_path / "doc.md"; md.write_text(DOC.format(extra="body_font_size: 14\n"))
    out = tmp_path / "doc.pdf"
    result = build(md, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert body_sizes(out) == {14}


def test_out_of_range_refused(tmp_path):
    md = tmp_path / "doc.md"; md.write_text(DOC.format(extra="body_font_size: 72\n"))
    result = build(md, tmp_path / "doc.pdf")
    assert result.returncode != 0
    assert "out of range" in (result.stdout + result.stderr)
