"""The plain-instrument layout primitives: a promissory note's grammar.

\\leftright puts two texts on ONE line, the right one flush right;
\\sigrow draws paired signature/date rules with labels beneath, one
signer per row, tagged for e-sign like any signature block.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

pdftotext = shutil.which("pdftotext")
pytestmark = pytest.mark.skipif(pdftotext is None, reason="pdftotext not installed")

FRONT = """---
doctype: document
heading_numbers: false
paper_title: "Layout Test"
esign: tags   # embedded-tag mode: half this module asserts tag text
---

{body}
"""


def build(tmp_path: Path, body: str) -> None:
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body=body))
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"),
         str(src), str(tmp_path / "doc.pdf")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr


def layout_text(tmp_path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(tmp_path / "doc.pdf"), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def test_leftright_shares_one_line_right_flush(tmp_path):
    build(tmp_path, "\\leftright{**$20,000.00**}{August 13, 2026}\n\nBody.")
    lines = layout_text(tmp_path).splitlines()
    line = next(ln for ln in lines if "$20,000.00" in ln)
    assert "August 13, 2026" in line, "left and right must share the line"
    assert line.index("$20,000.00") < line.index("August 13, 2026")
    # flush right: substantial gap, right text ends near the line's end
    assert "   " in line.split("$20,000.00", 1)[1]


def test_center_line_is_centered(tmp_path):
    build(tmp_path, "\\center{ATTACHMENT A}\n\nBody follows here.")
    lines = layout_text(tmp_path).splitlines()
    line = next(ln for ln in lines if "ATTACHMENT A" in ln)
    body = next(ln for ln in lines if "Body follows" in ln)
    assert (len(line) - len(line.lstrip())) > (len(body) - len(body.lstrip())), (
        "centered line must be indented past the left margin"
    )


def test_sigrow_labels_and_per_row_esign_roles(tmp_path):
    build(tmp_path,
          "Terms.\n\n\\sigrow{John Roe, Borrower}{Date}\n\n"
          "\\sigrow{Sue Smith, Lender\\\\Accepted and agreed}{Date}")
    text = layout_text(tmp_path)
    line = next(ln for ln in text.splitlines() if "John Roe, Borrower" in ln)
    assert "Date" in line, "label row pairs signer with Date"
    assert "Accepted and agreed" in text
    raw = " ".join(subprocess.run(
        ["pdftotext", str(tmp_path / "doc.pdf"), "-"],
        check=True, capture_output=True, text=True,
    ).stdout.split())
    assert "{{Signature 1;role=Signer 1;type=signature;width=" in raw
    assert "{{Date 1;role=Signer 1;type=date;width=" in raw
    assert "{{Signature 2;role=Signer 2;type=signature;width=" in raw


def test_sigrow_fill_in_label_gets_a_text_field_for_its_signer(tmp_path):
    """A label ending in underscores ("Name and title: ___") prints its
    text with a rule and gives that row's signer a text field, so a
    counterparty types a name instead of the label dangling unfilled."""
    build(tmp_path,
          "Terms.\n\n\\sigrow{JOHN ROE}{Date}\n\n"
          "\\sigrow{Name and title: ___\\\\For Example Co.}{Date}")
    text = layout_text(tmp_path)
    assert "Name and title:" in text and "___" not in text
    assert "For Example Co." in text
    raw = " ".join(subprocess.run(
        ["pdftotext", str(tmp_path / "doc.pdf"), "-"],
        check=True, capture_output=True, text=True,
    ).stdout.split())
    assert "{{Name and title 2;role=Signer 2;type=text;width=" in raw
    assert "role=Signer 1;type=text" not in raw
