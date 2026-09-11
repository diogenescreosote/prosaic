"""Case names are italicized, or the build fails.

California style sets the name of a cited case in italics (or
underline) and nothing else about the cite. A roman "Doe v. Roe" in a
brief is a drafting error every reader notices. It kept coming back in
drafts because the only thing standing against it was that somebody
would notice, so the renderer refuses it (ADR-0047), the same way it
refuses a captioned form attachment (ADR-0018).

Three things are pinned here: the detector's judgment on the shapes a
case name takes in running text (and the shapes that are not case
names), the title-line exemption that keeps a form attachment's
"Smith v. Roe, 24CV00000" opener legal, and the fact that all three
renderers (PDF, DOCX, TXT) refuse, not just the PDF.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

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
paper_title: "DECLARATION OF JANE ROE"
# Smith v. Roe in a YAML comment is not running text.
---

"""


def hits(body: str):
    return [h[1] for h in mp.find_unitalicized_case_names(FRONT + body + "\n")]


# ---------------------------------------------------------------------------
# What is a roman case name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "In Pettus v. Cole (1996) 49 Cal.App.4th 402, the court held otherwise.",
    "(People v. Superior Court (Humberto S.) (2008) 43 Cal.4th 737, fn. 3.)",
    "As In re Lifschutz (1970) 2 Cal.3d 415 explains, the waiver is narrow.",
    "See In re Marriage of Smith (2000) 80 Cal.App.4th 1.",
    "Under Estate of Jones (1990) 1 Cal.App.4th 1 the rule is the same.",
    'She wrote that "Britt v. Superior Court (1978) 20 Cal.3d 844" controls.',
    "This action, Smith v. Roe, Example County case number 24CV00000, is pending.",
    "See *Pettus* v. *Cole*, which italicized the parties but not the name.",
    "**Bold Doe v. Roe is still roman**, bold is not italic.",
])
def test_roman_case_names_are_found(body):
    assert hits(body), body


@pytest.mark.parametrize("body", [
    "In *Pettus v. Cole* (1996) 49 Cal.App.4th 402, the court held otherwise.",
    "See ***Pettus v. Cole*** for the same point in bold italic.",
    "See <u>Pettus v. Cole</u>, underlined on a typewriter.",
    "As *In re Lifschutz* (1970) 2 Cal.3d 415 explains.",
    "See *In re Marriage of Smith* (2000) 80 Cal.App.4th 1.",
    "The marriage of the parties was dissolved in 2020.",
    "The estate of the decedent passed by intestacy.",
    "Item 2 vs. item 3 independence, verified, not assumed.",
    "the docket \\fixedwidth{Smith v. Roe} is the source",
    "the docket `Smith v. Roe` is the source",
    "<!-- Story v. Superior Court unverified -->",
    "Health & Safety Code § 123110, subd. (a); 45 C.F.R. § 164.524.",
    "The rule was reworded because of *J.M. v. Illuminate\nEducation* (2026), which held",
    "- first item citing *Doe v. Roe*\n- second item citing *In re\n  Lifschutz*",
])
def test_italic_and_non_case_text_pass(body):
    assert not hits(body), body


# ---------------------------------------------------------------------------
# Title lines are roman
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "Smith v. Roe, 24CV00000",
    "Smith v. Roe, No. 24CV00000",
    "Roe v. Smith",
    "## Smith v. Roe",
    "In re Marriage of Smith, 24CV00000",
    "People ex rel. Lockyer v. Shamrock Foods Co.",
])
def test_title_only_lines_are_exempt(body):
    assert not hits(body), body


def test_form_attachment_opener_is_legal():
    body = ("Attachment 3 to Deposition Subpoena for Production of Business Records\n\n"
            "Smith v. Roe, 24CV00000\n\n"
            "1. Every record of *Smith v. Roe* discovery.")
    assert not hits(body)


def test_front_matter_is_not_running_text():
    assert not hits("Nothing to see here.")


def test_reports_every_hit_with_line_numbers():
    body = ("In Pettus v. Cole the court held.\n\n"
            "And In re Lifschutz agrees.\n")
    found = mp.find_unitalicized_case_names(FRONT + body)
    front_lines = FRONT.count("\n")
    assert [h[0] for h in found] == [front_lines + 1, front_lines + 3]
    wrapped = "A wrapped paragraph that cites\nPettus v. Cole across the\nbreak."
    assert [h[0] for h in mp.find_unitalicized_case_names(FRONT + wrapped)] == [front_lines + 1]
    with pytest.raises(SystemExit) as exc:
        mp.require_case_names_italic(FRONT + body, "decl.md")
    msg = str(exc.value)
    assert "decl.md: case name not italicized (2 place(s))" in msg
    assert "Pettus v. Cole" in msg and "In re Lifschutz" in msg
    assert "*Doe v. Roe*" in msg  # the fix is in the message


# ---------------------------------------------------------------------------
# All three renderers refuse
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, body: str) -> Path:
    src = tmp_path / "Declaration of Jane Roe.md"
    src.write_text(FRONT + body + "\n", encoding="utf-8")
    return src


@pytest.mark.parametrize("script,ext", [
    ("md_pleading.py", ".pdf"),
    ("md_to_docx.py", ".docx"),
    ("md_to_txt.py", ".txt"),
])
def test_every_renderer_refuses_a_roman_case_name(tmp_path, script, ext):
    src = _write(tmp_path, "In Pettus v. Cole (1996) 49 Cal.App.4th 402 the court held.")
    out = tmp_path / f"out{ext}"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
        capture_output=True, text=True)
    assert proc.returncode != 0, f"{script} built a roman case name"
    assert "case name not italicized" in proc.stderr
    assert not out.exists()


@pytest.mark.parametrize("script,ext", [
    ("md_pleading.py", ".pdf"),
    ("md_to_docx.py", ".docx"),
    ("md_to_txt.py", ".txt"),
])
def test_every_renderer_builds_an_italic_case_name(tmp_path, script, ext):
    src = _write(tmp_path, "In *Pettus v. Cole* (1996) 49 Cal.App.4th 402 the court held.")
    out = tmp_path / f"out{ext}"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "case name not italicized" not in proc.stderr
    assert out.exists()
