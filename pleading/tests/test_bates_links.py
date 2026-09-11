"""\\bates{TOKEN}: a Bates cite is a link to the stamped page.

A letter or brief that cites a production by Bates number and attaches
the cited pages should let the reader click the cite and land on the
page. The macro renders the token in the hyperlink blue, underlined, in
the fixed-width face every other Bates token uses, and the merged PDF
carries a /GoTo annotation to the exhibit page whose stamp it is. The
exhibit declares `bates_first:` (the token on its page 1); page n of the
file carries the number advanced by n-1, whatever `pages:` selects.

A cite to a page that is not in the packet is a broken link, so the
build refuses it; a cite into an exhibit withheld in this variant is
rendered without a link rather than refused, because the public packet
must show the gap, not fail.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

FRONT = """---
doctype: letter
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
to_name: "John Smith, Esq."
to_address_lines:
  - "1 Example Plaza"
  - "Springfield, CA 90000"
date: "2026-01-02"
paper_title: "Re: the production"
exhibits:
  - shortname: prod
    title: "Excerpts from the January 2, 2026 production"
    path: "{path}"
    pages: "{pages}"
    bates_first: "ACME00001"
---

Dear Mr. Smith:

"""


def _stamped_pdf(path: Path, n: int = 5) -> Path:
    c = canvas.Canvas(str(path), pagesize=letter)
    for i in range(1, n + 1):
        c.drawString(72, 720, f"Page {i} of the production")
        c.drawString(400, 40, f"ACME{i:05d}")
        c.showPage()
    c.save()
    return path


def _build(tmp_path: Path, body: str, pages: str = "1-2,4") -> subprocess.CompletedProcess:
    prod = _stamped_pdf(tmp_path / "production.pdf")
    src = tmp_path / "Letter to Smith.md"
    src.write_text(FRONT.format(path=prod, pages=pages) + body + "\n\nSincerely,\n\nJane Roe\n",
                   encoding="utf-8")
    out = tmp_path / "out.pdf"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        capture_output=True, text=True)
    proc.out = out  # type: ignore[attr-defined]
    return proc


def _goto_targets(pdf: Path):
    """(source page index, target page index) for every /GoTo annotation."""
    reader = PdfReader(str(pdf))
    ids = {p.indirect_reference.idnum: i for i, p in enumerate(reader.pages)}
    found = []
    for i, page in enumerate(reader.pages):
        for a in (page.get("/Annots") or []):
            a = a.get_object()
            act = a.get("/A")
            if act and act.get("/S") == "/GoTo":
                dest = act["/D"][0]
                found.append((i, ids[dest.idnum]))
    return found


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_bates_span_is_mono_underlined_and_carries_the_reference():
    spans = mp.parse_inline_styles("see \\bates{ACME00017} and \\bates{ACME00001--00002}.")
    b = [s for s in spans if s.bates_ref]
    assert [s.bates_ref for s in b] == ["ACME00017", "ACME00001--00002"]
    assert all(s.mono and s.underline for s in b)
    assert b[1].text == "ACME00001\u201300002"  # range displays with an en dash


def test_link_target_is_the_first_token_of_a_range():
    words = mp.spans_to_styled_words(mp.parse_inline_styles("\\bates{ACME00001--00002}"))
    assert words[0].link_target == "bates:ACME00001"
    words = mp.spans_to_styled_words(mp.parse_inline_styles("\\bates{ACME00017}"))
    assert words[0].link_target == "bates:ACME00017"


def test_bates_is_verbatim_for_typography_and_case_name_checks():
    text = "cite \\bates{ACME00001--00002} here"
    assert mp.typographic_subs(text) == text  # the -- inside is not substituted
    raw = "---\nx: 1\n---\n\nSee \\bates{ROE00001} for Doe v. Roe.\n"
    assert [h[1].rstrip(".") for h in mp.find_unitalicized_case_names(raw)] == ["Doe v. Roe"]


def test_page_tokens_follow_the_source_page_number():
    assert mp.bates_page_tokens("ACME00001", [1, 2, 4]) == {
        "ACME00001": 1, "ACME00002": 2, "ACME00004": 4}
    assert mp.bates_page_tokens("CAP-0100", [3]) == {"CAP-0102": 3}
    with pytest.raises(ValueError):
        mp.bates_page_tokens("ACME", [1])


# ---------------------------------------------------------------------------
# The built packet
# ---------------------------------------------------------------------------

def test_bates_cites_link_to_the_stamped_pages(tmp_path):
    proc = _build(tmp_path, "The intake is at \\bates{ACME00004}; the consents at \\bates{ACME00001--00002}.")
    assert proc.returncode == 0, proc.stderr[-1500:]
    targets = _goto_targets(proc.out)
    reader = PdfReader(str(proc.out))
    texts = [p.extract_text() for p in reader.pages]
    # Exhibit pages appended after the letter and the tab sheet, in
    # selection order: source pages 1, 2, 4 carry ACME00001/2/4.
    page_of = {tok: i for i, t in enumerate(texts) for tok in ("ACME00001", "ACME00002", "ACME00004")
               if tok in t and "Page" in t}
    bates_targets = sorted(t for _, t in targets if t in page_of.values())
    assert bates_targets == sorted([page_of["ACME00004"], page_of["ACME00001"]])
    assert "ACME00001\u201300002" in texts[0].replace("\n", "")


def test_a_cite_to_a_page_not_in_the_packet_fails_the_build(tmp_path):
    proc = _build(tmp_path, "See \\bates{ACME00003}.")  # page 3 is not selected
    assert proc.returncode != 0
    assert "ACME00003" in proc.stderr and "do not land on an attached page" in proc.stderr
    assert not proc.out.exists()


def test_a_cite_to_a_withheld_exhibit_renders_without_a_link(tmp_path):
    prod = _stamped_pdf(tmp_path / "production.pdf")
    src = tmp_path / "Letter to Smith.md"
    front = FRONT.format(path=prod, pages="1-2,4").replace(
        '    bates_first: "ACME00001"\n', '    bates_first: "ACME00001"\n    sealed: true\n')
    src.write_text(front + "See \\bates{ACME00004}.\n\nSincerely,\n\nJane Roe\n", encoding="utf-8")
    out = tmp_path / "out.pdf"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert _goto_targets(out) == []
    assert "ACME00004" in PdfReader(str(out)).pages[0].extract_text()


def test_docx_and_txt_carry_the_token(tmp_path):
    prod = _stamped_pdf(tmp_path / "production.pdf")
    src = tmp_path / "Letter to Smith.md"
    src.write_text(FRONT.format(path=prod, pages="1-2,4")
                   + "See \\bates{ACME00004} and \\bates{ACME00001--00002}.\n\nSincerely,\n\nJane Roe\n",
                   encoding="utf-8")
    for script, ext in (("md_to_docx.py", ".docx"), ("md_to_txt.py", ".txt")):
        out = tmp_path / f"out{ext}"
        proc = subprocess.run(
            [sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr[-1500:]
    assert "ACME00004" in (tmp_path / "out.txt").read_text(encoding="utf-8")
    from docx import Document
    doc = Document(str(tmp_path / "out.docx"))
    runs = [r for p in doc.paragraphs for r in p.runs if r.text.startswith("ACME")]
    assert runs and all(r.underline and str(r.font.color.rgb) == "0000EE" for r in runs)
