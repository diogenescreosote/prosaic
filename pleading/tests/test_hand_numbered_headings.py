"""A heading that carries its own outline number fails the build.

number_headings() prefixes every heading (# -> I., ## -> A., ### -> 1.),
so a typed "## I. Argument" prints as "A. I. Argument". The doubling
recurred across drafts, so the renderer refuses it in all three
renderers unless the source opts out with heading_numbers: false.
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
filer_name: Jane Roe
filer_address_lines: [1 Main St, Town, CA 90000]
filer_phone: "(555) 555-5555"
filer_role: Petitioner, In Pro Per
court_name: SUPERIOR COURT OF CALIFORNIA
court_county: COUNTY OF EXAMPLE
petitioner: JANE ROE
respondent: JOHN DOE
case_number: 24CV00000
paper_title: MEMORANDUM
---
"""


@pytest.mark.parametrize("heading", [
    "# I. Introduction", "## II. The privilege applies",
    "## A. Waiver", "### 1. The release", "### 12. Twelfth",
])
def test_hand_numbered_heading_is_found(heading):
    hits = mp.find_hand_numbered_headings(FRONT + "\n" + heading + "\n\nBody.\n")
    assert len(hits) == 1 and hits[0][1] == heading


@pytest.mark.parametrize("heading", [
    "# Introduction", "## The privilege applies", "### Article I. Scope",
    "## In re Doe controls", "## I want this heading",
])
def test_plain_heading_passes(heading):
    assert mp.find_hand_numbered_headings(FRONT + "\n" + heading + "\n") == []


def test_opt_out_allows_own_enumeration():
    src = FRONT.replace("paper_title: MEMORANDUM", "paper_title: MEMORANDUM\nheading_numbers: false")
    assert mp.find_hand_numbered_headings(src + "\n## I. Own numbering\n") == []


def test_fenced_text_ignored():
    assert mp.find_hand_numbered_headings(FRONT + "\n```\n## I. Example\n```\n") == []


def test_message_names_lines_and_fix():
    body = "\n## I. First\n\nText.\n\n## II. Second\n"
    with pytest.raises(SystemExit) as exc:
        mp.require_unnumbered_headings(FRONT + body, "mpa.md")
    msg = str(exc.value)
    assert "mpa.md: hand-numbered heading (2 place(s))" in msg
    assert "## I. First" in msg and "heading_numbers: false" in msg


@pytest.mark.parametrize("script", ["md_pleading.py", "md_to_docx.py", "md_to_txt.py"])
def test_every_renderer_refuses(tmp_path, script):
    src = tmp_path / "mpa.md"
    src.write_text(FRONT + "\n## I. Argument\n\nText.\n")
    out = tmp_path / ("out" + {"md_pleading.py": ".pdf", "md_to_docx.py": ".docx", "md_to_txt.py": ".txt"}[script])
    proc = subprocess.run([sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
                          capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode != 0
    assert "hand-numbered heading" in proc.stderr


def test_source_without_front_matter_does_not_crash():
    assert mp.find_hand_numbered_headings("## I. Notes\n") == [(1, "## I. Notes")]
