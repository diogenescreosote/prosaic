"""``\\pagebreak`` on its own line starts the next page.

A proposed order's signature page should carry an operative paragraph,
not just the signature; the drafter forces that with ``\\pagebreak``.
PDF breaks the page, DOCX inserts a page break, TXT (no pages) drops it.
At the top of a page it is a no-op, so it never makes a blank page.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

PLEADING_DIR = Path(__file__).resolve().parent.parent

FRONT = """---
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "jane.roe@example.com"
filer_role: "Respondent, In Pro Per"
court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "COUNTY OF EXAMPLE"
petitioner: "JOHN SMITH"
respondent: "JANE ROE"
caption_first_party_label: "Petitioner"
caption_second_party_label: "Respondent"
case_number: "24CV00000"
paper_title: "PROPOSED ORDER"
---

"""


def _build(tmp_path: Path, body: str, script: str, ext: str) -> Path:
    src = tmp_path / "doc.md"
    src.write_text(FRONT + body + "\n")
    out = tmp_path / f"out{ext}"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    return out


def test_pdf_pagebreak_moves_following_text_to_next_page(tmp_path):
    out = _build(tmp_path, "First paragraph.\n\n\\pagebreak\n\nSecond paragraph.",
                 "md_pleading.py", ".pdf")
    pages = [" ".join(p.extract_text().split()) for p in PdfReader(str(out)).pages]
    assert len(pages) == 2
    assert "First paragraph" in pages[0] and "Second paragraph" not in pages[0]
    assert "Second paragraph" in pages[1]


def test_pdf_consecutive_pagebreaks_make_no_blank_page(tmp_path):
    out = _build(tmp_path, "One.\n\n\\pagebreak\n\n\\pagebreak\n\nTwo.",
                 "md_pleading.py", ".pdf")
    assert len(PdfReader(str(out)).pages) == 2


@pytest.mark.parametrize("script,ext", [("md_to_docx.py", ".docx"),
                                        ("md_to_txt.py", ".txt")])
def test_other_renderers_never_print_the_macro(tmp_path, script, ext):
    out = _build(tmp_path, "One.\n\n\\pagebreak\n\nTwo.", script, ext)
    if ext == ".txt":
        assert "pagebreak" not in out.read_text()
    else:
        from docx import Document
        doc = Document(str(out))
        assert not any("pagebreak" in p.text for p in doc.paragraphs)
        assert 'w:type="page"' in doc.element.xml
