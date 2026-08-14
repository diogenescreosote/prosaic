"""The \\highlight{} macro's rendering: a yellow background run.

Coverage moved here from the exhibits scenario, where the highlighted
sentinel sat inside the packet the AI judge scores for
FILING-READINESS — and per the spec's own terms (a filed version has
every highlight accepted or reverted), the judge rightly called a
visible "added by the drafting assistant" annotation disqualifying.
A review aid belongs in a unit fixture, not a filing fixture.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLEADING_DIR = Path(__file__).resolve().parent.parent

SOURCE = """---
doctype: document
heading_numbers: false
paper_title: "Highlight Test"
---

The parties agree that \\highlight{HIGHLIGHT-UNIT-TOKEN this passage
awaits counsel's review} before filing.
"""


def test_highlight_macro_renders_yellow_run(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(SOURCE)
    out = tmp_path / "doc.pdf"
    subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        check=True, capture_output=True,
    )
    from pypdf import PdfReader

    reader = PdfReader(str(out))
    text = "".join(p.extract_text() or "" for p in reader.pages)
    assert "HIGHLIGHT-UNIT-TOKEN" in text
    data = reader.pages[0].get_contents().get_data()
    assert b"1 1 0 rg" in data, "yellow highlight fill not drawn"
