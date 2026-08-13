"""A document that has not been filed or sent must say so, on the page.

`notreal:` used to be a note to whoever opened the *source*. The
rendered PDF carried no trace of it — and the rendered PDF is the
object that gets attached to an email, printed, handed across a table,
and mistaken for the real thing. A draft declaration and a filed one
look identical, and nothing about the artifact distinguishes them.

So the marker prints, in red, on every page. What is tested here is
the property that makes it worth anything:

- it appears on **every** page, not just the first, because pages get
  separated
- it appears in the PDF, the DOCX, and the TXT, because all three
  leave the building
- it says what the marker says — "not filed" and "not sent" are
  different facts — rather than a generic "DRAFT"
- it is **absent** when the marker is, since a banner on a filed
  pleading would be its own kind of disaster
- it does not disturb the 28-line grid, so removing the marker cannot
  change pagination
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PLEADING_DIR.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

pdftotext = pytest.importorskip("shutil").which("pdftotext")

SOURCE = """---
notreal: "{marker}"
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
---

I, Jane Roe, declare as follows:

#. First paragraph of a declaration that runs long enough to reach a
   second page, so the banner can be checked on more than page one.

{filler}
"""

FILLER = "\n\n".join(
    f"#. Paragraph {i} exists only to push this declaration onto a "
    f"second page so the per-page banner can be observed there."
    for i in range(2, 40)
)


def render(tmp_path: Path, marker: str | None, final: bool = False) -> str:
    """Render a source with (or without) a marker; return its PDF text."""
    front = SOURCE.format(marker=marker or "", filler=FILLER)
    if marker is None:
        front = "\n".join(
            line for line in front.splitlines() if not line.startswith("notreal:")
        )
    src = tmp_path / "decl.md"
    src.write_text(front)
    out = tmp_path / "decl.pdf"
    cmd = [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)]
    if final:
        cmd.append("--final")
    subprocess.run(cmd, check=True, capture_output=True)
    return subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def test_banner_appears_on_every_page(tmp_path):
    text = render(tmp_path, "DRAFT---not filed")
    pages = text.split("\f")
    assert len(pages) > 2, "fixture must span multiple pages to test this"
    for i, page in enumerate(pages):
        if not page.strip():
            continue  # trailing split artifact
        assert "DRAFT—NOT FILED" in page, f"banner missing from page {i + 1}"


def test_banner_says_what_the_marker_says(tmp_path):
    """"Not filed" and "not sent" are different facts about the world."""
    assert "NOT SENT" in render(tmp_path, "DRAFT---not sent")
    assert "SIMULATION" in render(tmp_path, "AI-generated simulation")


def test_default_banner_without_a_marker(tmp_path):
    """Every build is a draft until --final says otherwise: an
    unmarked pleading source gets the doctype default."""
    text = render(tmp_path, None)
    pages = [p for p in text.split("\f") if p.strip()]
    for i, page in enumerate(pages):
        assert "DRAFT—NOT FILED" in page, f"default banner missing from page {i + 1}"


def test_final_build_clears_the_banner(tmp_path):
    """The failure that would matter most: a banner on a real filing —
    now reachable only through the explicit --final flag."""
    text = render(tmp_path, None, final=True)
    for token in ("DRAFT", "NOT FILED", "NOT SENT", "SIMULATION"):
        assert token not in text.upper().replace("DECLARATION", "")


def test_a_source_cannot_finalize_itself(tmp_path):
    """_final in front matter is stripped: only the build flag clears
    the banner."""
    front = SOURCE.format(marker="", filler=FILLER)
    front = front.replace("notreal: \"\"", "_final: true")
    src = tmp_path / "decl.md"
    src.write_text(front)
    out = tmp_path / "decl.pdf"
    subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        check=True, capture_output=True,
    )
    text = subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "DRAFT—NOT FILED" in text


def test_banner_does_not_move_the_line_grid(tmp_path):
    """Clearing `notreal:` must not repaginate the document.

    If the banner took a line of the 28-line grid, the draft and the
    filed version would break pages differently — so every page and
    line citation taken against the draft would be wrong in the thing
    actually filed.
    """
    for sub in ("a", "b", "c"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    with_marker = render(tmp_path / "a", "DRAFT---not filed")
    finaled = render(tmp_path / "b", None, final=True)
    defaulted = render(tmp_path / "c", None)
    assert (len(with_marker.split("\f"))
            == len(finaled.split("\f"))
            == len(defaulted.split("\f")))


def _render_to(tmp_path: Path, script: str, suffix: str, marker: str) -> Path:
    src = tmp_path / "decl.md"
    src.write_text(SOURCE.format(marker=marker, filler=FILLER))
    out = tmp_path / f"decl{suffix}"
    subprocess.run(
        [sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
        check=True, capture_output=True,
    )
    return out


def test_docx_carries_the_banner_in_the_page_header(tmp_path):
    """The header is what makes it repeat, and what survives editing.

    A DOCX goes to counsel to be worked on. A banner in the body is
    something to delete by accident; one in the header is not part of
    the text being edited.
    """
    docx = pytest.importorskip("docx")
    out = _render_to(tmp_path, "md_to_docx.py", ".docx", "DRAFT---not sent")
    doc = docx.Document(str(out))
    header = doc.sections[0].header.paragraphs[0]
    assert "DRAFT—NOT SENT" in header.text
    run = header.runs[0]
    assert run.bold
    assert run.font.color.rgb is not None, "banner must be colored, not plain"


def test_txt_carries_the_banner(tmp_path):
    """A .txt gets pasted into email more readily than a PDF is attached."""
    out = _render_to(tmp_path, "md_to_txt.py", ".txt", "DRAFT---not filed")
    first = out.read_text().splitlines()[0]
    assert "DRAFT—NOT FILED" in first
    assert first.startswith("***"), "banner must be delimited from the document"


def test_banner_reaches_the_jc_cover_sheet_and_every_merged_page(tmp_path):
    """The stamp covers the whole packet, not just what the renderer drew.

    A deposition subpoena is a filled SUBP-010, then the attachment,
    then exhibits. Marking only the generated pages left page 1 clean —
    worse than no marking, because it reads as a statement that the
    form is final.
    """
    matter = REPO_ROOT / "tests" / "scenarios" / "form_filling" / "matter"
    src = matter / "src" / "Subpoena to Example Bank.md"
    if not src.exists():
        pytest.skip("form_filling fixture matter not present")
    out = tmp_path / "subpoena.pdf"
    subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        check=True, capture_output=True, cwd=str(matter),
    )
    pages = subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        check=True, capture_output=True, text=True,
    ).stdout.split("\f")
    pages = [p for p in pages if p.strip()]
    assert len(pages) >= 3, "fixture should be cover sheet + attachment"
    assert "SUBP-010" in pages[0], "page 1 should be the JC cover sheet"
    for i, page in enumerate(pages):
        assert "SCENARIO FIXTURE" in page, (
            f"page {i + 1} carries no banner — a packet is only marked if "
            f"every page is"
        )


def test_banner_does_not_collide_with_the_form_header(tmp_path):
    """The band is reclaimed by scaling, not drawn over the form.

    A JC form's own header starts a quarter inch from the paper edge.
    Overlaying a banner there lands on "ATTORNEY OR PARTY WITHOUT
    ATTORNEY" and makes both unreadable, which is how the first
    attempt at this failed.
    """
    matter = REPO_ROOT / "tests" / "scenarios" / "form_filling" / "matter"
    src = matter / "src" / "Subpoena to Example Bank.md"
    if not src.exists():
        pytest.skip("form_filling fixture matter not present")
    out = tmp_path / "subpoena.pdf"
    subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        check=True, capture_output=True, cwd=str(matter),
    )
    # -layout preserves vertical order: the banner must be strictly
    # above the form's first label, on its own line.
    lines = [ln for ln in subprocess.run(
        ["pdftotext", "-layout", "-f", "1", "-l", "1", str(out), "-"],
        check=True, capture_output=True, text=True,
    ).stdout.split("\n") if ln.strip()]
    assert "SCENARIO FIXTURE" in lines[0]
    assert "ATTORNEY" not in lines[0], (
        "banner shares a line with the form header — it is overlapping it"
    )


def test_a_long_marker_wraps_instead_of_running_off_the_page(tmp_path):
    """Shrink to a floor, then wrap — never draw wider than the paper.

    Real markers get long, because a useful one says what to do before
    serving. A 133-character marker shrank to the minimum size and was
    drawn anyway, overflowing both edges: the page rendered
    "RAFT—…SERVIC", losing the word that matters most at the start.
    """
    long_marker = ("DRAFT---not served as of August 8, 2026; AT&T Mobility LLC "
                   "registered-agent address must be verified against CA SOS "
                   "bizfile before service")
    lines, size = mp._banner_layout(long_marker.upper().replace("---", "—"), 612)
    assert len(lines) > 1, "an over-long marker must wrap, not overflow"
    for line in lines:
        width = mp.pdfmetrics.stringWidth(line, mp.FONT_NAME_BOLD, size)
        assert width <= 612 - 2 * mp.RIGHT_MARGIN, f"{line!r} is wider than the page"

    text = render(tmp_path, long_marker)
    first = text.split("\f")[0]
    assert "DRAFT" in first, "the leading word was clipped off the page edge"
    assert "SERVICE" in first, "the trailing word was clipped off the page edge"


def test_marker_normalized_to_the_house_dash_rule():
    """Markers were written before they were rendered; output obeys the rule."""
    banner = mp.draft_banner_text({"notreal": "DRAFT — not filed as of May 2026"})
    assert banner == "DRAFT—NOT FILED AS OF MAY 2026"
    assert " — " not in banner


def test_absent_marker_yields_the_doctype_default():
    assert mp.draft_banner_text({}) == "DRAFT—NOT FILED"
    assert mp.draft_banner_text({"doctype": "document"}) == "DRAFT—NOT EXECUTED"
    assert mp.draft_banner_text({"doctype": "letter"}) == "DRAFT—NOT SENT"
    assert mp.draft_banner_text({"_final": True}) is None
    assert mp.draft_banner_text({"_final": True, "notreal": "x"}) is None

def _mkdirs(tmp_path):
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)
