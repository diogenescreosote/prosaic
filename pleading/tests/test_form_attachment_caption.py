"""An attachment to a JC form must not be captioned as a pleading.

This is the mistake that kept coming back. An "Attachment 3 to
Deposition Subpoena for Production of Business Records" continues
SUBP-010 item 3 — the form carried the attorney block, the court name
and the party caption one page earlier. Repeating them presents the
attachment as a separate paper that was separately filed, which it is
not; it has no independent existence.

It kept coming back for a specific reason, worth recording because it
was not the one anyone assumed. The sources said `plain: true`, and
**nothing in the renderer ever read that key.** The working key is
`no_caption:`. So the instruction was in the file, the file was
correct on its face, and every rebuild reprinted the caption. It
looked like an agent ignoring documentation; it was a config key wired
to nothing. prosaic's own scenario fixture had the same defect,
which is how the pattern spread by copying.

So the fix is mechanical in three places, and this file pins all
three: `plain:` is honored (and warns), the caption is suppressed in
the DOCX renderer as well as the PDF one, and a form attachment that
would print a caption fails the build instead of rendering.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import form_fill  # noqa: E402
import md_pleading as mp  # noqa: E402
from pypdf import PdfReader  # noqa: E402

BASE = """---
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
paper_title: "{title}"
{extra}---

Attachment 3 to Deposition Subpoena for Production of Business Records

Smith v. Roe, 24CV00000

The records requested are described below.
"""


def render(tmp_path: Path, title: str, extra: str = "", script: str = "md_pleading.py",
           suffix: str = ".pdf") -> subprocess.CompletedProcess:
    src = tmp_path / "att.md"
    src.write_text(BASE.format(title=title, extra=extra))
    return subprocess.run(
        [sys.executable, str(PLEADING_DIR / script), str(src),
         str(tmp_path / f"att{suffix}")],
        capture_output=True, text=True,
    )


def text_of(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


# --- the guard ------------------------------------------------------


def test_attachment_without_no_caption_fails_the_build(tmp_path):
    """Fails loudly rather than rendering the wrong thing.

    A warning would not have helped: the wrong output was already
    being produced and shipped, and nobody was reading stderr.
    """
    proc = render(tmp_path, "ATTACHMENT 3 TO DEPOSITION SUBPOENA")
    assert proc.returncode != 0
    assert "no_caption" in proc.stderr
    assert not (tmp_path / "att.pdf").exists(), "it must not write output"


def test_subpoena_cover_sheet_implies_attachment(tmp_path):
    """SUBP-010 item 3 says "described in Attachment 3" — so it is."""
    proc = render(tmp_path, "SOMETHING ELSE ENTIRELY", extra="cover_sheet: subp010\n")
    assert proc.returncode != 0
    assert "no_caption" in proc.stderr


def test_subp002_cover_sheet_implies_attachment():
    """SUBP-002's records demand is declaration item 2, continued on
    Attachment 2 — a source behind that cover sheet continues the form."""
    assert mp.is_form_attachment({"cover_sheet": "subp002"})


def test_a_declaration_behind_a_cover_form_is_not_an_attachment(tmp_path):
    """The rule is about form continuations, not everything behind a form.

    A declaration attached to a CIV-110 is a distinct document that
    the request incorporates, and California practice captions it
    normally. Over-broad enforcement here would be its own bug.
    """
    assert not mp.is_form_attachment(
        {"paper_title": "DECLARATION OF JANE ROE", "cover_sheet": "civ110"}
    )


# --- the rendering --------------------------------------------------


def test_attachment_renders_without_the_pleading_caption(tmp_path):
    proc = render(tmp_path, "ATTACHMENT 3 TO DEPOSITION SUBPOENA",
                  extra="no_caption: true\n")
    assert proc.returncode == 0, proc.stderr
    body = text_of(tmp_path / "att.pdf")
    first_page = body.split("\f")[0]
    for forbidden in ("SUPERIOR COURT OF THE STATE",
                      "COUNTY OF EXAMPLE",
                      "Petitioner,",
                      "123 Main Street"):
        assert forbidden not in first_page, (
            f"attachment reprints {forbidden!r} from the caption the form "
            f"already carried"
        )
    assert "Attachment 3 to Deposition Subpoena" in first_page


def test_plain_is_honored_as_the_old_spelling(tmp_path):
    """Six sources across two matters already said `plain:`, believing it worked."""
    proc = render(tmp_path, "ATTACHMENT 3 TO DEPOSITION SUBPOENA",
                  extra="plain: true\n")
    assert proc.returncode == 0, proc.stderr
    assert "SUPERIOR COURT OF THE STATE" not in text_of(tmp_path / "att.pdf")
    assert "plain" in proc.stderr and "no_caption" in proc.stderr, (
        "a key that silently did nothing for months must now say so"
    )


def test_docx_suppresses_the_caption_too(tmp_path):
    """The DOCX renderer ignored `no_caption:` entirely.

    The same source produced a correct PDF and a captioned DOCX — and
    the DOCX is the copy that goes to counsel.
    """
    docx = pytest.importorskip("docx")
    proc = render(tmp_path, "ATTACHMENT 3 TO DEPOSITION SUBPOENA",
                  extra="no_caption: true\n", script="md_to_docx.py",
                  suffix=".docx")
    assert proc.returncode == 0, proc.stderr
    doc = docx.Document(str(tmp_path / "att.docx"))
    body = "\n".join(p.text for p in doc.paragraphs)
    assert "SUPERIOR COURT OF THE STATE" not in body
    assert "Attachment 3 to Deposition Subpoena" in body


# --- cover_sheet_only: a standalone JC form with no accompanying body ----
#
# MC-050 Substitution of Attorney is the motivating case: a source that
# exists solely to fill a Judicial Council form has no declaration or
# motion text riding behind it. Before cover_sheet_only existed, an empty
# body still got a wasted, mostly-blank numbered pleading-paper page
# appended after the filled form's own pages.

MC050_ONLY = pytest.mark.skipif(
    "mc050" not in form_fill.list_forms(), reason="mc050 descriptor not present")

MC050_SOURCE = """---
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
case_number: "24CV00000"
paper_title: "SUBSTITUTION OF ATTORNEY"
notreal: "DRAFT---not filed"
{extra}---
"""


def render_mc050(tmp_path: Path, extra: str = "", name: str = "sub"
                  ) -> subprocess.CompletedProcess:
    src = tmp_path / f"{name}.md"
    src.write_text(MC050_SOURCE.format(extra=extra))
    return subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src),
         str(tmp_path / f"{name}.pdf")],
        capture_output=True, text=True,
    )


@MC050_ONLY
def test_cover_sheet_only_requires_cover_sheet(tmp_path):
    """The flag has nothing to output without a form to fill."""
    proc = render_mc050(tmp_path, extra="cover_sheet_only: true\n")
    assert proc.returncode != 0
    assert "cover_sheet_only" in proc.stderr
    assert "cover_sheet" in proc.stderr
    assert not (tmp_path / "sub.pdf").exists()


@MC050_ONLY
def test_cover_sheet_only_rejects_exhibits(tmp_path):
    """No body means no document for an exhibit appendix to attach behind."""
    proc = render_mc050(
        tmp_path,
        extra=(
            "cover_sheet: mc050\n"
            "cover_sheet_only: true\n"
            "exhibits:\n"
            "  - shortname: \"stray\"\n"
            "    title: \"Stray Exhibit\"\n"
            "    sealed: true\n"
        ),
    )
    assert proc.returncode != 0
    assert "exhibits" in proc.stderr
    assert "cover_sheet_only" in proc.stderr
    assert not (tmp_path / "sub.pdf").exists()


@MC050_ONLY
def test_cover_sheet_only_produces_only_the_forms_own_pages(tmp_path):
    """The fix: with the flag, the output is exactly the filled form."""
    proc = render_mc050(tmp_path, extra="cover_sheet: mc050\ncover_sheet_only: true\n")
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "sub.pdf"
    blank_pages = len(PdfReader(str(PLEADING_DIR / "forms" / "mc050.pdf")).pages)
    built_pages = len(PdfReader(str(out)).pages)
    assert built_pages == blank_pages, (
        f"expected exactly the {blank_pages}-page MC-050 and nothing else, "
        f"got {built_pages} pages"
    )

    pages = text_of(out).split("\f")
    pages = [p for p in pages if p.strip()]
    assert len(pages) == blank_pages
    for i, page in enumerate(pages, 1):
        assert "DRAFT" in page and "NOT FILED" in page, (
            f"page {i} carries no draft banner"
        )


@MC050_ONLY
def test_without_the_flag_a_body_page_is_still_appended(tmp_path):
    """Pins the historic bug this flag fixes: `cover_sheet:` alone, with
    an empty body, still produces a wasted extra page after the form."""
    proc = render_mc050(tmp_path, extra="cover_sheet: mc050\n")
    assert proc.returncode == 0, proc.stderr
    blank_pages = len(PdfReader(str(PLEADING_DIR / "forms" / "mc050.pdf")).pages)
    built_pages = len(PdfReader(str(tmp_path / "sub.pdf")).pages)
    assert built_pages > blank_pages, (
        "expected the wasted body page that cover_sheet_only exists to remove"
    )
