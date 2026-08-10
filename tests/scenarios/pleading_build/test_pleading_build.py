"""Pleading-build scenario (spec: specs/pleading/generator.md).

Fixture: a minimal fictional matter with one declaration source.
Operation: the real envelope build. Checks: California pleading-paper
mechanics, typography conventions, and (AI) whether the output reads
and renders like competent, filing-ready work product.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness import scenario
from tests.harness.ai import assert_judgment, judge

DECL = "Declaration of Jane Roe.pdf"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    matter = scenario.load_scenario("pleading_build", tmp_path_factory.mktemp("m"))
    proc = scenario.build_envelope(matter, "declaration")
    out = matter / "out" / "declaration" / DECL
    assert proc.returncode == 0, proc.stderr[-2000:]
    return matter, out


def test_output_exists_and_paginated(built):
    _m, out = built
    from pypdf import PdfReader
    assert out.exists()
    assert 1 <= len(PdfReader(str(out)).pages) <= 3


def test_pleading_line_numbers(built):
    """California pleading paper: numbered lines 1–28 in the left margin."""
    _m, out = built
    import re
    text = scenario.pdf_text(out)
    first_page = text.split("\f")[0]
    leading = {int(m.group(1)) for m in re.finditer(r"^\s{0,3}(\d{1,2})\b", first_page, re.M)}
    present = len(leading & set(range(1, 29)))
    assert present >= 24, f"only {present}/28 margin line numbers detected"


def test_caption_and_perjury_clause(built):
    _m, out = built
    text = scenario.pdf_text(out)
    for needle in (
        "SUPERIOR COURT OF THE STATE OF CALIFORNIA",
        "COUNTY OF EXAMPLE",
        "JOHN SMITH",
        "JANE ROE",
        "24CV00000",
        "penalty of perjury",
    ):
        assert needle in text, f"missing: {needle}"


def test_typography_conventions(built):
    """The workspace's em/en dash rules, verified in the artifact."""
    _m, out = built
    text = scenario.pdf_text(out)
    assert "—" in text, "em dash (from source ---) not rendered"
    assert "–" in text, "en dash (from source --) not rendered"
    assert " --- " not in text and " -- " not in text
    assert " — " not in text, "spaced em dash in output (style violation)"


def test_no_drafting_annotations_leak(built):
    _m, out = built
    text = scenario.pdf_text(out).lower()
    for tok in ("notreal", "todo", "fixme", "[draft note", "update 20"):
        assert tok not in text, f"working annotation leaked into filing: {tok}"


@pytest.mark.ai
def test_ai_pleading_reads_as_filing_ready(built, tmp_path):
    _m, out = built
    pages = scenario.rasterize(out, tmp_path / "decl", dpi=100)
    j = judge(
        task=("An automated generator rendered a self-represented party's "
              "declaration from Markdown onto California 28-line pleading "
              "paper."),
        rubric=(
            "10/10: correct pleading-paper anatomy (line numbers, caption "
            "box with parties and case number, title, page footer); body "
            "text aligned to numbered lines; professional typography "
            "(proper em dashes without surrounding spaces, no markdown "
            "artifacts); numbered paragraphs; a proper perjury clause and "
            "signature block; and prose that reads like a competent, "
            "neutral declaration — no placeholders, no editorializing "
            "artifacts, nothing an opposing counsel would mock."),
        hard_failures=[
            "visible markdown syntax or template placeholders in the output",
            "caption, case number, or perjury clause missing",
            "body text misaligned with the numbered lines badly enough to impair citation",
        ],
        files=pages,
        threshold=7,
    )
    assert_judgment(j, "pleading filing-readiness")
