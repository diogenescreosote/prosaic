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

import md_pleading as mp  # noqa: E402

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
