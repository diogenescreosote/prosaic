"""Deposition cites need the transcript pages (Cal. Rules of Court, rule 3.1116).

A paper that cites deposition testimony attaches the cited pages: a title
page naming the deponent and the date, only the relevant pages with
their original numbering, the cited lines marked. Without them the court
has only the declarant's account of the testimony. So the build reads
the body for cites ("Doe Dep. 62:16-24, 63:5-8", and a bare
"(94:20-95:3.)" continuing one) and warns when no exhibit declares
`deposition:` for the deponent, or when an excerpt's `transcript_pages:`
leave out a cited page. A warning, never a failure. With the excerpt in
the packet, the cite links to its tab.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

PLEADING_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PLEADING_DIR / "md_pleading.py"
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

FRONT = """---
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "jane.roe@example.com"
filer_role: "Plaintiff, In Pro Per"
court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "COUNTY OF EXAMPLE"
petitioner: "JANE ROE"
respondent: "JOHN SMITH"
case_number: "24CV00000"
paper_title: "DECLARATION OF JANE ROE"
{exhibits}---

1. The witness agreed the gate was open. (Doe Dep. 62:16-24, 63:5--8.)
She later said it was closed. (94:20-95:3.)
"""

EXCERPT = """exhibits:
  - shortname: "doe_dep"
    title: "Excerpts from the Deposition of John Doe, with the cited testimony highlighted"
    path: "{path}"
    deposition: "John Doe"
{extra}"""


def _transcript_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for text in ("DEPOSITION OF JOHN DOE, January 2, 2026", "Page 62", "Page 63", "Page 94"):
        c.drawString(72, 700, text)
        c.showPage()
    c.save()
    return path


def _build(tmp_path: Path, exhibits: str = "") -> subprocess.CompletedProcess[str]:
    src = tmp_path / "decl.md"
    src.write_text(FRONT.format(exhibits=exhibits), encoding="utf-8")
    out = tmp_path / "decl.pdf"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(src), str(out)], capture_output=True, text=True
    )
    proc.out = out  # type: ignore[attr-defined]
    return proc


def _excerpt(tmp_path: Path, extra: str = "") -> str:
    return EXCERPT.format(path=_transcript_pdf(tmp_path / "doe_excerpt.pdf"), extra=extra)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_named_and_continuation_cites_are_found_and_attributed():
    raw = FRONT.format(exhibits="") + "\nSee Mary Roe Dep. 12:3-8; 14:1. (Id. at 15:2.)\n"
    cites = mp.find_deposition_cites(raw)
    assert [(c.deponent, c.refs, c.pages, c.continuation) for c in cites] == [
        ("Doe", "62:16-24, 63:5--8", [62, 63], False),
        ("Doe", "94:20-95:3", [94, 95], True),
        ("Mary Roe", "12:3-8; 14:1", [12, 14], False),
        ("Mary Roe", "15:2", [15], True),
    ]


def test_a_cross_page_range_touches_every_page_between():
    assert mp.transcript_pages_in("94:20–96:3, 62:16-24") == [94, 95, 96, 62]


def test_a_bare_reference_with_no_named_cite_before_it_is_not_attributed():
    raw = "---\nx: 1\n---\n\nThe meeting ran long. (12:3-5.)\n"
    assert mp.find_deposition_cites(raw) == []


def test_cites_in_comments_and_verbatim_text_are_not_read():
    raw = "---\nx: 1\n---\n\n<!-- Doe Dep. 1:1 -->\n\n\\fixedwidth{Doe Dep. 2:2}\n"
    assert mp.find_deposition_cites(raw) == []


def test_deponent_matching_is_by_surname():
    assert mp.deponent_matches("Doe", "John Doe")
    assert mp.deponent_matches("See John Doe", "Doe")
    assert not mp.deponent_matches("Roe", "John Doe")


def test_transcript_pages_parse_and_refuse_a_bad_spec():
    assert mp.parse_transcript_pages("21-24, 62--63, 94") == [21, 22, 23, 24, 62, 63, 94]
    with pytest.raises(ValueError):
        mp.parse_transcript_pages("24-21")
    with pytest.raises(ValueError):
        mp.parse_transcript_pages("pp. 3")


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def test_a_cite_with_no_excerpt_exhibit_warns_and_still_builds(tmp_path):
    r = _build(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "deposition testimony cited without a rule 3.1116 transcript excerpt exhibit" in (
        r.stderr
    )
    assert "Doe Dep.: Doe Dep. 62:16-24, 63:5--8 (line 17); 94:20-95:3 (line 17)" in r.stderr
    assert 'deposition: "Doe"' in r.stderr


def test_a_matching_excerpt_exhibit_silences_the_warning(tmp_path):
    r = _build(tmp_path, _excerpt(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "rule 3.1116" not in r.stderr


def test_transcript_pages_missing_a_cited_page_warns(tmp_path):
    r = _build(tmp_path, _excerpt(tmp_path, '    transcript_pages: "62-63, 94"\n'))
    assert r.returncode == 0, r.stderr
    assert "Doe Dep. cites transcript page 95 that the excerpt" in r.stderr
    assert "rule 3.1116 transcript excerpt exhibit" not in r.stderr


def test_transcript_pages_covering_every_cite_are_quiet(tmp_path):
    r = _build(tmp_path, _excerpt(tmp_path, '    transcript_pages: "62-63, 94-95"\n'))
    assert r.returncode == 0, r.stderr
    assert "rule 3.1116" not in r.stderr


def test_transcript_pages_without_deposition_is_refused(tmp_path):
    bad = _excerpt(tmp_path, '    transcript_pages: "62"\n').replace(
        '    deposition: "John Doe"\n', ""
    )
    r = _build(tmp_path, bad)
    assert r.returncode != 0
    assert "transcript_pages needs deposition" in r.stdout + r.stderr


def test_the_cite_links_to_the_excerpt_tab(tmp_path):
    r = _build(tmp_path, _excerpt(tmp_path))
    assert r.returncode == 0, r.stderr
    reader = PdfReader(str(r.out))  # type: ignore[attr-defined]
    ids = {p.indirect_reference.idnum: i for i, p in enumerate(reader.pages)}
    tab = next(i for i, p in enumerate(reader.pages) if "EXHIBIT A" in (p.extract_text() or ""))
    targets = []
    for i, page in enumerate(reader.pages[:tab]):
        for a in page.get("/Annots") or []:
            act = a.get_object().get("/A")
            if act and act.get("/S") == "/GoTo":
                targets.append((i, ids[act["/D"][0].idnum]))
    assert (0, tab) in targets
