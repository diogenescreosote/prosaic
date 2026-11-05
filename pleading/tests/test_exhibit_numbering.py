"""Exhibit numbering styles and exhibits inside exhibits.

A party answering papers whose exhibits are lettered numbers its own
(`exhibit_numbering: numeric`), so "Exhibit C" can only ever mean the
other side's. Each document numbers its own list: a declaration attached
as an exhibit keeps its own scheme, because its signed text already says
"Exhibit A".

That nesting is the hazard. Inside the parent's Exhibit 1, the child's
"EXHIBIT A" tab sheet reads as the parent's Exhibit A. So each inner tab
sheet carries one line naming the parent exhibit it belongs to, "Part of
Exhibit 1: <title>": drawn by the child's own build for a markdown
exhibit, stamped on the packet's copy for a prebuilt PDF
(`inner_tab_pages`). Only tab sheets carry it.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pypdf
import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PLEADING_DIR / "md_pleading.py"
DOCX_SCRIPT = PLEADING_DIR / "md_to_docx.py"
TXT_SCRIPT = PLEADING_DIR / "md_to_txt.py"
sys.path.insert(0, str(PLEADING_DIR))

FRONT = """---
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
paper_title: "{title}"
{extra}---
{body}
"""

PART_OF = "Part of Exhibit 1: Declaration of John Smith"


def write(path: Path, *, title: str, body: str, extra: str = "") -> Path:
    """Sources live in <tmp>/src/, so bare exhibit names resolve to the
    sibling <tmp>/exhibits/ (the renderer's convention)."""
    path = path.parent / "src" / path.name
    path.parent.mkdir(exist_ok=True)
    path.write_text(FRONT.format(title=title, body=body, extra=extra))
    return path


def make_pdf(path: Path, pages: list[str]) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for text in pages:
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(306, 400, text)
        c.showPage()
    c.save()
    return path


def exhibits_yaml(*entries: tuple[str, str, str], extra: str = "") -> str:
    out = "exhibits:\n"
    for shortname, title, target in entries:
        out += f'  - shortname: "{shortname}"\n    title: "{title}"\n    path: "{target}"\n'
    return out + extra


def run(script: Path, md: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), str(md), str(out)], capture_output=True, text=True
    )


def page_texts(pdf: Path) -> list[str]:
    return [" ".join((p.extract_text() or "").split()) for p in pypdf.PdfReader(pdf).pages]


def tab_pages(pdf: Path, heading: str) -> list[str]:
    return [t for t in page_texts(pdf) if heading in t]


@pytest.fixture()
def two_exhibits(tmp_path):
    (tmp_path / "exhibits").mkdir()
    make_pdf(tmp_path / "exhibits" / "one.pdf", ["FIRST-EXHIBIT-BODY"])
    make_pdf(tmp_path / "exhibits" / "two.pdf", ["SECOND-EXHIBIT-BODY"])
    return tmp_path, exhibits_yaml(
        ("one", "First Letter", "one.pdf"), ("two", "Second Letter", "two.pdf")
    )


def test_numeric_style_numbers_cites_list_and_tabs(two_exhibits):
    tmp, ex = two_exhibits
    md = write(
        tmp / "decl.md",
        title="DECLARATION",
        body="See \\exhibit{one} and \\exhibit{two}.",
        extra="exhibit_numbering: numeric\n" + ex,
    )
    out = tmp / "decl.pdf"
    r = run(SCRIPT, md, out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = " ".join(page_texts(out))
    assert "See Exhibit 1 and Exhibit 2." in text
    assert "Exhibit 1: First Letter" in text and "Exhibit 2: Second Letter" in text
    assert tab_pages(out, "EXHIBIT 2")
    assert "EXHIBIT A" not in text and "Exhibit A" not in text
    # the cite still links to its tab sheet
    reader = pypdf.PdfReader(out)
    outline = [o.title for o in reader.outline if not isinstance(o, list)]
    assert "Exhibit 1" in outline and "Exhibit 2" in outline


def test_default_style_stays_letters(two_exhibits):
    tmp, ex = two_exhibits
    md = write(
        tmp / "decl.md",
        title="DECLARATION",
        body="See \\exhibit{one} and \\exhibit{two}.",
        extra=ex,
    )
    out = tmp / "decl.pdf"
    r = run(SCRIPT, md, out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "See Exhibit A and Exhibit B." in " ".join(page_texts(out))


def test_unknown_style_fails_the_build(two_exhibits):
    tmp, ex = two_exhibits
    md = write(
        tmp / "decl.md",
        title="DECLARATION",
        body="See \\exhibit{one}.",
        extra="exhibit_numbering: roman\n" + ex,
    )
    r = run(SCRIPT, md, tmp / "decl.pdf")
    assert r.returncode != 0
    assert "exhibit_numbering" in r.stdout + r.stderr


def test_docx_and_txt_cite_the_same_designators(two_exhibits):
    tmp, ex = two_exhibits
    md = write(
        tmp / "decl.md",
        title="DECLARATION",
        body="See \\exhibit{two} (TOKEN1).",
        extra="exhibit_numbering: numeric\n" + ex,
    )
    r = run(DOCX_SCRIPT, md, tmp / "decl.docx")
    assert r.returncode == 0, r.stdout + r.stderr
    from docx import Document

    joined = "\n".join(p.text for p in Document(str(tmp / "decl.docx")).paragraphs)
    assert "See Exhibit 2 (TOKEN1)" in joined
    r = run(TXT_SCRIPT, md, tmp / "decl.txt")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "See Exhibit 2 (TOKEN1)" in (tmp / "decl.txt").read_text()
    # an explicit alpha file gets letters in the TXT too
    md.write_text(md.read_text().replace("exhibit_numbering: numeric", "exhibit_numbering: alpha"))
    r = run(TXT_SCRIPT, md, tmp / "decl.txt")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "See Exhibit B (TOKEN1)" in (tmp / "decl.txt").read_text()


def _child_declaration(tmp: Path) -> Path:
    (tmp / "exhibits").mkdir(exist_ok=True)
    make_pdf(tmp / "exhibits" / "report.pdf", ["INNER-REPORT-BODY"])
    return write(
        tmp / "smith.md",
        title="DECLARATION OF JOHN SMITH",
        body="The report is attached as \\exhibit{report}.",
        extra=exhibits_yaml(("report", "Search Report", "report.pdf")),
    )


def test_markdown_child_tab_sheet_names_its_parent_exhibit(tmp_path):
    _child_declaration(tmp_path)
    parent = write(
        tmp_path / "roe.md",
        title="DECLARATION OF JANE ROE",
        body="Mr. Smith's declaration is \\exhibit{smith}.",
        extra="exhibit_numbering: numeric\n"
        + exhibits_yaml(("smith", "Declaration of John Smith", "smith.md")),
    )
    out = tmp_path / "roe.pdf"
    r = run(SCRIPT, parent, out)
    assert r.returncode == 0, r.stdout + r.stderr
    texts = page_texts(out)
    inner = [t for t in texts if "EXHIBIT A" in t]
    assert len(inner) == 1 and PART_OF in inner[0]
    assert "Search Report" in inner[0]
    # only that tab sheet: not the parent's own tab, not the child's pages
    assert sum(PART_OF in t for t in texts) == 1
    assert "declaration is Exhibit 1." in " ".join(texts)
    # the child keeps its own letters
    assert "The report is attached as Exhibit A." in " ".join(texts)


def test_markdown_child_built_alone_has_no_parent_line(tmp_path):
    child = _child_declaration(tmp_path)
    out = tmp_path / "smith.pdf"
    r = run(SCRIPT, child, out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not any("Part of" in t for t in page_texts(out))


def test_parent_line_names_the_immediate_parent_only(tmp_path):
    _child_declaration(tmp_path)
    write(
        tmp_path / "middle.md",
        title="DECLARATION OF JANE ROE",
        body="See \\exhibit{smith}.",
        extra="exhibit_numbering: numeric\n"
        + exhibits_yaml(("smith", "Declaration of John Smith", "smith.md")),
    )
    top = write(
        tmp_path / "top.md",
        title="MEMORANDUM",
        body="See \\exhibit{roe}.",
        extra=exhibits_yaml(("roe", "Declaration of Jane Roe", "middle.md")),
    )
    out = tmp_path / "top.pdf"
    r = run(SCRIPT, top, out)
    assert r.returncode == 0, r.stdout + r.stderr
    texts = page_texts(out)
    smith_tab = [t for t in texts if "EXHIBIT 1" in t and "Declaration of John Smith" in t]
    assert smith_tab and "Part of Exhibit A: Declaration of Jane Roe" in smith_tab[0]
    report_tab = [t for t in texts if "Search Report" in t and "EXHIBIT A" in t]
    assert report_tab and PART_OF in report_tab[0]
    assert "Jane Roe" not in report_tab[0].split("Part of")[1]


def test_prebuilt_pdf_inner_tab_page_is_stamped_on_the_copy_only(tmp_path):
    (tmp_path / "exhibits").mkdir()
    signed = make_pdf(
        tmp_path / "exhibits" / "smith_signed.pdf",
        ["SIGNED-DECLARATION-PAGE", "EXHIBIT A", "INNER-REPORT-BODY"],
    )
    before = hashlib.sha256(signed.read_bytes()).hexdigest()
    parent = write(
        tmp_path / "roe.md",
        title="DECLARATION OF JANE ROE",
        body="See \\exhibit{smith}.",
        extra="exhibit_numbering: numeric\n"
        + exhibits_yaml(
            ("smith", "Declaration of John Smith", "smith_signed.pdf"),
            extra='    inner_tab_pages: "2"\n',
        ),
    )
    out = tmp_path / "roe.pdf"
    r = run(SCRIPT, parent, out)
    assert r.returncode == 0, r.stdout + r.stderr
    texts = page_texts(out)
    stamped = [t for t in texts if PART_OF in t]
    assert len(stamped) == 1 and "EXHIBIT A" in stamped[0]
    assert hashlib.sha256(signed.read_bytes()).hexdigest() == before


def test_inner_tab_pages_respects_the_pages_selection(tmp_path):
    (tmp_path / "exhibits").mkdir()
    make_pdf(tmp_path / "exhibits" / "s.pdf", ["P1", "EXHIBIT A", "P3"])
    base = exhibits_yaml(
        ("s", "Declaration of John Smith", "s.pdf"),
        extra='    pages: "2-3"\n    inner_tab_pages: "2"\n',
    )
    parent = write(
        tmp_path / "ok.md",
        title="DECL",
        body="See \\exhibit{s}.",
        extra="exhibit_numbering: numeric\n" + base,
    )
    r = run(SCRIPT, parent, tmp_path / "ok.pdf")
    assert r.returncode == 0, r.stdout + r.stderr
    stamped = [t for t in page_texts(tmp_path / "ok.pdf") if PART_OF in t]
    assert len(stamped) == 1 and "EXHIBIT A" in stamped[0]
    bad = write(
        tmp_path / "bad.md",
        title="DECL",
        body="See \\exhibit{s}.",
        extra="exhibit_numbering: numeric\n"
        + base.replace('inner_tab_pages: "2"', 'inner_tab_pages: "1"'),
    )
    r = run(SCRIPT, bad, tmp_path / "bad.pdf")
    assert r.returncode != 0
    assert "inner_tab_pages" in r.stdout + r.stderr


def test_inner_tab_pages_on_a_markdown_exhibit_is_refused(tmp_path):
    _child_declaration(tmp_path)
    parent = write(
        tmp_path / "roe.md",
        title="DECL",
        body="See \\exhibit{smith}.",
        extra=exhibits_yaml(
            ("smith", "Declaration of John Smith", "smith.md"), extra='    inner_tab_pages: "2"\n'
        ),
    )
    r = run(SCRIPT, parent, tmp_path / "roe.pdf")
    assert r.returncode != 0
    assert "marks its own tab sheets" in r.stdout + r.stderr
