"""body_font: a per-document body typeface.

House style is Century Schoolbook (TeX Gyre Schola). A court or
counterparty that expects Times New Roman gets `body_font: times`, which
embeds Liberation Serif, a metric-compatible free clone; Cal. Rules of
Court, rule 2.105 allows either face. The key is validated (a typo must
not silently fall back to house style), and a child markdown exhibit
renders in its own subprocess, so a Times parent never bleeds into a
Schola attachment or vice versa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pymupdf

PLEADING_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PLEADING_DIR / "md_pleading.py"
DOCX_SCRIPT = PLEADING_DIR / "md_to_docx.py"

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
{extra}---
I, Jane Roe, declare that *Doe v. Roe* (2020) 1 Cal.5th 1 **governs** the
widgets dispute{body_tail}.
"""

CHILD = """---
doctype: document
paper_title: "WIDGET SUPPLY AGREEMENT"
short_title: "Agreement"
---
Acme Widgets, Inc. agrees to supply widgets to Jane Roe on the terms below.
"""

EXHIBIT_BLOCK = """exhibits:
  - shortname: agreement
    path: child.md
    title: "Widget Supply Agreement"
"""


def build(md: Path, out: Path, script: Path = SCRIPT):
    return subprocess.run([sys.executable, str(script), str(md), str(out)],
                          capture_output=True, text=True)


def fonts_by_page(pdf: Path) -> list:
    """The set of embedded font names used by text spans on each page."""
    pages = []
    for page in pymupdf.open(pdf):
        names = set()
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    names.add(span["font"])
        pages.append(names)
    return pages


def body_fonts(pdf: Path) -> set:
    names = set()
    for page in pymupdf.open(pdf):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if "widgets dispute" in span["text"] or "Doe v. Roe" in span["text"]:
                        names.add(span["font"])
    return names


def _is_schola(name: str) -> bool:
    return "Schola" in name


def _is_times(name: str) -> bool:
    return "Liberation" in name or "TimesNewRoman" in name


def test_default_body_is_century_schoolbook(tmp_path):
    md = tmp_path / "decl.md"
    md.write_text(PLEADING.format(extra="", body_tail=""))
    out = tmp_path / "decl.pdf"
    result = build(md, out)
    assert result.returncode == 0, result.stdout + result.stderr
    used = body_fonts(out)
    assert used and all(_is_schola(n) for n in used), used
    assert not any(_is_times(n) for n in fonts_by_page(out)[0])


def test_times_embeds_liberation_serif_everywhere(tmp_path):
    md = tmp_path / "decl.md"
    md.write_text(PLEADING.format(extra="body_font: times\n", body_tail=""))
    out = tmp_path / "decl.pdf"
    result = build(md, out)
    assert result.returncode == 0, result.stdout + result.stderr
    used = body_fonts(out)
    assert used and all(_is_times(n) for n in used), used
    # Caption, line numbers and footer switch with the body: no Schola
    # anywhere on the page, and the italic case name took the italic face.
    page_fonts = fonts_by_page(out)[0]
    assert not any(_is_schola(n) for n in page_fonts), page_fonts
    assert any("Italic" in n for n in page_fonts), page_fonts


def test_aliases_are_case_insensitive(tmp_path):
    for alias in ("Times New Roman", "TNR", "TIMES"):
        md = tmp_path / "decl.md"
        md.write_text(PLEADING.format(extra=f"body_font: {alias}\n", body_tail=""))
        out = tmp_path / "decl.pdf"
        result = build(md, out)
        assert result.returncode == 0, alias + result.stdout + result.stderr
        assert all(_is_times(n) for n in body_fonts(out)), alias


def test_unknown_value_fails_naming_file_and_choices(tmp_path):
    md = tmp_path / "decl.md"
    md.write_text(PLEADING.format(extra="body_font: comic sans\n", body_tail=""))
    for script in (SCRIPT, DOCX_SCRIPT):
        result = build(md, tmp_path / "decl.out", script)
        assert result.returncode != 0, script.name
        text = result.stdout + result.stderr
        assert "decl.md" in text and "body_font" in text, text
        assert "century" in text and "times" in text, text


def test_markdown_exhibit_child_keeps_its_own_face(tmp_path):
    (tmp_path / "child.md").write_text(CHILD)
    md = tmp_path / "decl.md"
    md.write_text(PLEADING.format(extra="body_font: times\n" + EXHIBIT_BLOCK,
                                  body_tail=" (see \\exhibit{agreement})"))
    out = tmp_path / "decl.pdf"
    result = build(md, out)
    assert result.returncode == 0, result.stdout + result.stderr
    pages = fonts_by_page(out)
    # Parent body page: Times only. Last page is the child, which carries
    # no body_font and so renders in house style; the parent process
    # stamps only the draft banner over it.
    assert not any(_is_schola(n) for n in pages[0]), pages[0]
    child = pages[-1]
    assert any(_is_schola(n) for n in child), child
    # The exhibit tab sheet is the parent's work and follows the parent.
    tab = pages[-2]
    assert all(_is_times(n) for n in tab), tab


def test_docx_names_times_new_roman(tmp_path):
    import zipfile
    md = tmp_path / "decl.md"
    md.write_text(PLEADING.format(extra="body_font: times\n", body_tail=""))
    out = tmp_path / "decl.docx"
    result = build(md, out, DOCX_SCRIPT)
    assert result.returncode == 0, result.stdout + result.stderr
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode() + z.read("word/styles.xml").decode()
    assert 'w:ascii="Times New Roman"' in xml
