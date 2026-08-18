"""`no_exhibit_list: true` skips the standalone "EXHIBIT LIST" index page.

A single-exhibit filing that already names the exhibit in its own body
text doesn't need a whole extra page just to say so again. Tab sheets
and the attached exhibit itself are a different concern (they mark
where the exhibit begins and carry its content) and must be unaffected.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

BASE = """---
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "jane.roe@example.com"
filer_role: "Petitioner, In Pro Per"
court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "COUNTY OF EXAMPLE"
petitioner: "JANE ROE"
respondent: "JOHN SMITH"
case_number: "24CV00000"
paper_title: "STIPULATION FOR DISMISSAL"
exhibits:
  - shortname: "form"
    title: "Some Attached Form"
    path: "exhibits/exhibit.pdf"
{extra}---
The parties stipulate as follows, per the form attached as \\exhibit{{form}}.
"""


def _make_exhibit_pdf(path: Path) -> None:
    # A minimal one-page PDF is enough; content is irrelevant here.
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    c.drawString(72, 700, "exhibit")
    c.showPage()
    c.save()


def render(tmp_path: Path, extra: str = "") -> Path:
    (tmp_path / "exhibits").mkdir(exist_ok=True)
    _make_exhibit_pdf(tmp_path / "exhibits" / "exhibit.pdf")
    src = tmp_path / "stip.md"
    src.write_text(BASE.format(extra=extra))
    out = tmp_path / "stip.pdf"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return out


def text_of(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def test_exhibit_list_appears_by_default(tmp_path):
    out = render(tmp_path)
    text = text_of(out)
    assert "EXHIBIT LIST" in text
    assert "EXHIBIT A" in text  # the tab sheet is unrelated and still present


def test_no_exhibit_list_suppresses_the_index_page(tmp_path):
    out = render(tmp_path, extra="no_exhibit_list: true\n")
    text = text_of(out)
    assert "EXHIBIT LIST" not in text
    assert "EXHIBIT A" in text  # tab sheet and exhibit itself still attach
    assert "exhibit" in text.lower()  # the exhibit's own drawn content
