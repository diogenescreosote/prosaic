"""Markdown exhibits: an exhibit may be another prosaic source file.

A stipulation that authorizes subpoenas should carry them, and the old
practice — build the subpoena, then hand-reference the built PDF in a
second pass — meant the attached copy silently drifted from its source.
An exhibit whose path ends in .md is instead rendered through the same
pipeline at build time and attached, like any PDF exhibit.

Mutually-referential exhibits would recurse forever, so the render
chain travels in PROSAIC_EXHIBIT_RENDER_STACK and a document appearing
twice in its own ancestry is a hard error naming the cycle.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pypdf

PLEADING_DIR = Path(__file__).resolve().parent.parent
SCRIPT = PLEADING_DIR / "md_pleading.py"
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


def write(path: Path, *, title: str, body: str, extra: str = "") -> Path:
    path.write_text(FRONT.format(title=title, body=body, extra=extra))
    return path


def build(md: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(md), str(out)],
        capture_output=True, text=True,
    )


def exhibit_yaml(shortname: str, target: str) -> str:
    return (
        "exhibits:\n"
        f"  - shortname: \"{shortname}\"\n"
        "    title: \"Form of Attached Instrument\"\n"
        f"    path: \"{target}\"\n"
    )


def test_markdown_exhibit_renders_and_attaches(tmp_path):
    child = write(tmp_path / "child.md", title="PROPOSED INSTRUMENT",
                  body="The quick brown fox exhibit body.")
    parent = write(tmp_path / "parent.md", title="STIPULATION",
                   body="The parties stipulate per the form attached as \\exhibit{form}.",
                   extra=exhibit_yaml("form", "child.md"))
    out = tmp_path / "parent.pdf"
    result = build(parent, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.exists()
    text = " ".join(
        " ".join(page.extract_text().split())
        for page in pypdf.PdfReader(out).pages
    )
    # parent body, tab sheet letter, and the child's rendered content
    assert "form attached as Exhibit A" in text
    assert "quick brown fox" in text
    # bare .md names resolve beside the referencing file, not exhibits/
    assert not (tmp_path.parent / "exhibits").exists()


def test_two_way_cycle_is_refused_with_the_chain_named(tmp_path):
    write(tmp_path / "a.md", title="DOC A", body="See \\exhibit{b}.",
          extra=exhibit_yaml("b", "b.md"))
    write(tmp_path / "b.md", title="DOC B", body="See \\exhibit{a}.",
          extra=exhibit_yaml("a", "a.md"))
    result = build(tmp_path / "a.md", tmp_path / "a.pdf")
    assert result.returncode != 0
    err = result.stdout + result.stderr
    assert "cycle" in err
    assert "a.md" in err and "b.md" in err
    assert not (tmp_path / "a.pdf").exists()


def test_self_reference_is_refused(tmp_path):
    write(tmp_path / "solo.md", title="DOC", body="See \\exhibit{me}.",
          extra=exhibit_yaml("me", "solo.md"))
    result = build(tmp_path / "solo.md", tmp_path / "solo.pdf")
    assert result.returncode != 0
    assert "cycle" in (result.stdout + result.stderr)


def test_dependency_info_lists_md_exhibit_and_its_deps_without_rendering(tmp_path):
    grandchild = write(tmp_path / "grandchild.md", title="LEAF", body="Leaf body.")
    child = write(tmp_path / "child.md", title="MIDDLE", body="See \\exhibit{leaf}.",
                  extra=exhibit_yaml("leaf", "grandchild.md"))
    parent = write(tmp_path / "parent.md", title="ROOT", body="See \\exhibit{mid}.",
                   extra=exhibit_yaml("mid", "child.md"))
    import md_pleading
    deps = md_pleading.dependency_info(parent)["deps"]
    assert str(child.resolve()) in deps
    assert str(grandchild.resolve()) in deps


def test_dependency_info_survives_a_cycle_without_hanging(tmp_path):
    write(tmp_path / "a.md", title="DOC A", body="See \\exhibit{b}.",
          extra=exhibit_yaml("b", "b.md"))
    write(tmp_path / "b.md", title="DOC B", body="See \\exhibit{a}.",
          extra=exhibit_yaml("a", "a.md"))
    import md_pleading
    deps = md_pleading.dependency_info(tmp_path / "a.md")["deps"]
    assert str((tmp_path / "b.md").resolve()) in deps


def test_letter_size_pdf_exhibit_attaches_at_native_size(tmp_path):
    """The old 7.5x10in inset shrank every letter exhibit ~12%, which
    silently defeated statutes that regulate an instrument's typeface
    (Civ. Code 56.11(c): a CMIA authorization must be >= 14-point). A
    letter page must attach unscaled.

    Asserted on a --final build: a draft build's banner legitimately
    reclaims its strip by scaling every page a few percent, and that
    scaling disappears with the banner. The executed instrument is by
    definition a final build, so final is where the statute's floor
    must hold."""
    child = write(tmp_path / "child.md", title="AUTHORIZATION",
                  body="I authorize the disclosure of the described records information.",
                  extra="body_font_size: 14\ndoctype: document\n")
    # doctype document has different required fields; rebuild front matter minimally
    child.write_text("""---
doctype: document
body_font_size: 14
paper_title: "AUTHORIZATION"
short_title: "Authorization"
---
I authorize the disclosure of the described records information.
""")
    parent = write(tmp_path / "parent.md", title="STIPULATION",
                   body="Per the authorization attached as \\exhibit{auth}.",
                   extra=exhibit_yaml("auth", "child.md"))
    out = tmp_path / "parent.pdf"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(parent), str(out), "--final"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    import fitz
    doc = fitz.open(out)
    sizes = set()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if "authorize the disclosure" in span["text"]:
                        sizes.add(round(span["size"], 1))
    assert sizes == {14.0}, sizes
