"""\\doclink{https://...}{text}: a web address is a /URI link.

A \\doclink whose target begins ``http://`` or ``https://`` links to that
exact URL, fragment included, rather than to a relative file (/GoToR) or
an in-document destination (``#``). The text is set like every other
doclink: body face, dark blue, underlined. The URL is verbatim: no dash
or quote substitution, and its ``#`` fragment is not read as an
in-document jump. DOCX carries a real hyperlink; TXT prints
"text (URL)". Pleadings and letters share one PDF path; both are built.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pymupdf
from pypdf import PdfReader

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

URL = "https://example.com/d/AB--C'x\"y---z?q=1#key-one--two"

PLEADING = """---
doctype: pleading
filer_name: "Jane Roe"
filer_address_lines: ["1 Example Street", "Example City, CA 90000"]
filer_phone: "(000) 000-0000"
filer_email: "jane@example.com"
filer_role: "Plaintiff, In Pro Per"
court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "EXAMPLE"
petitioner: "Jane Roe"
respondent: "Acme Widgets, Inc."
paper_title: "DECLARATION OF JANE ROE"
case_number: "24CV00000"
---
The widget schedule is at \\doclink{%s}{the shared schedule} today.
"""

LETTER = """---
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
paper_title: "Re: the widget schedule"
---

Dear Mr. Smith:

The widget schedule is at \\doclink{%s}{the shared schedule} today.

Sincerely,

Jane Roe
"""


def _render(tmp_path: Path, template: str, script: str, suffix: str) -> Path:
    src = tmp_path / "doc.md"
    src.write_text(template % URL, encoding="utf-8")
    out = tmp_path / f"doc{suffix}"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return out


def _uri_links(pdf: Path) -> list:
    """(page index, rect, URI) for every /URI link annotation."""
    found = []
    for i, page in enumerate(PdfReader(pdf).pages):
        for a in page.get("/Annots") or []:
            o = a.get_object()
            act = o.get("/A")
            if act and act.get("/S") == "/URI":
                found.append((i, [float(v) for v in o["/Rect"]], str(act["/URI"])))
    return found


def _assert_uri_over_text(pdf: Path) -> None:
    links = _uri_links(pdf)
    assert [u for _, _, u in links] == [URL], links
    page_idx, rect, _ = links[0]
    page = pymupdf.open(pdf)[page_idx]
    # pypdf rects are bottom-left origin; pymupdf clips top-left.
    h = page.rect.height
    clip = pymupdf.Rect(rect[0], h - rect[3], rect[2], h - rect[1])
    under = " ".join(page.get_text("text", clip=clip).split())
    assert under == "the shared schedule", under
    # No relative-file or in-document action was made from the URL.
    for p in PdfReader(pdf).pages:
        for a in p.get("/Annots") or []:
            assert a.get_object()["/A"].get("/S") != "/GoToR"


def test_url_doclink_parses_to_uri_target_in_doclink_ink():
    (sp,) = [s for s in mp.parse_inline_styles(
        "See \\doclink{%s}{the shared schedule}." % URL) if s.doc_link]
    assert sp.doc_link == URL and sp.underline and not sp.mono
    target = mp._span_link_target(sp)
    assert target == "uri:" + URL
    assert mp._link_color(target) == mp.DOCLINK_COLOR_RGB
    # Whole-body typographic substitution leaves the URL alone.
    body = "a -- b \\doclink{%s}{x} \"c\"" % URL
    assert URL in mp.typographic_subs(body)


def test_pleading_pdf_carries_uri_annotation_over_link_text(tmp_path):
    _assert_uri_over_text(_render(tmp_path, PLEADING, "md_pleading.py", ".pdf"))


def test_letter_pdf_carries_uri_annotation_over_link_text(tmp_path):
    _assert_uri_over_text(_render(tmp_path, LETTER, "md_pleading.py", ".pdf"))


def test_docx_url_doclink_is_a_real_hyperlink(tmp_path):
    out = _render(tmp_path, PLEADING, "md_to_docx.py", ".docx")
    with zipfile.ZipFile(out) as z:
        doc = z.read("word/document.xml").decode()
        rels = z.read("word/_rels/document.xml.rels").decode()
    assert "<w:hyperlink" in doc and "the shared schedule" in doc
    from xml.sax.saxutils import escape
    assert 'TargetMode="External"' in rels
    assert escape(URL, {'"': "&quot;"}) in rels, rels


def test_txt_url_doclink_prints_text_then_url(tmp_path):
    out = _render(tmp_path, PLEADING, "md_to_txt.py", ".txt")
    assert f"the shared schedule ({URL})" in out.read_text(encoding="utf-8")
