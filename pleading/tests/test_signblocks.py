"""Signature blocks are one macro with styles (ADR-0027).

The regression that motivated the taxonomy: a testamentary execution
clause recites its date ("...on this ___ day of ___, 20__...") and
the old \\signblock then printed a second "Dated:" line under it. The
whereof style owns the clause and the signature area as one block, so
the date appears exactly once. Also pinned here: the legacy macros
still build (deprecation warning, never a failure), and every signing
area carries DocuSeal field tags with roles numbered in document
order — the same order `sc esign send --to` assigns.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

pdftotext = shutil.which("pdftotext")
pytestmark = pytest.mark.skipif(pdftotext is None, reason="pdftotext not installed")

FRONT = """---
doctype: document
heading_numbers: false
paper_title: "Signature Test"
---

# Article I. Body

The signature areas follow.

{body}
"""


def build(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body=body))
    return subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"),
         str(src), str(tmp_path / "doc.pdf")],
        capture_output=True, text=True, cwd=tmp_path,
    )


def text_of(tmp_path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(tmp_path / "doc.pdf"), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def test_whereof_recites_the_date_exactly_once(tmp_path):
    proc = build(tmp_path,
                 "\\signblock{whereof}{ANDREW PETER CONE}{Testator}{Will}")
    assert proc.returncode == 0, proc.stderr
    text = text_of(tmp_path)
    flat = " ".join(text.split())
    assert ("IN WITNESS WHEREOF, I, ANDREW PETER CONE, sign this Will on "
            "this _____ day of") in flat
    assert ", at _________________________." in flat, "location stays blank"
    assert "Dated:" not in text, "the duplicate-date regression"
    assert "ANDREW PETER CONE" in text
    assert "Testator" in text


def test_whereof_defaults_the_instrument_word(tmp_path):
    build(tmp_path, "\\signblock{whereof}{JANE ROE}")
    assert "sign this instrument on" in " ".join(text_of(tmp_path).split())


def test_styles_map_to_their_blocks(tmp_path):
    proc = build(tmp_path, "\n\n".join([
        "\\signblock{dated}{JANE ROE}{Petitioner}",
        "\\signblock{decl}{JOHN SMITH}{Springfield, California}",
        "\\signblock{judge}{JUDGE OF THE SUPERIOR COURT}",
        "\\signblock{letter}{Jane Roe\\\\Roe & Associates}",
    ]))
    assert proc.returncode == 0, proc.stderr
    text = text_of(tmp_path)
    assert "Dated:" in text                                  # dated
    assert "Executed this" in text                           # decl
    assert "JUDGE OF THE SUPERIOR COURT" in text             # judge
    assert "Sincerely," in text                              # letter
    assert "deprecat" not in proc.stderr, "styled forms must not warn"


def test_legacy_macros_still_build_with_a_warning(tmp_path):
    proc = build(tmp_path, "\n\n".join([
        "\\signblock{JANE ROE}{Petitioner}",
        "\\declsignblock{JOHN SMITH}{Springfield, California}",
        "\\judgesignblock{JUDGE OF THE SUPERIOR COURT}",
    ]))
    assert proc.returncode == 0, "legacy forms must never fail a build"
    assert proc.stderr.count("WARNING") >= 3
    assert "\\signblock{decl}" in proc.stderr, "warning teaches the new form"
    text = text_of(tmp_path)
    assert "Dated:" in text and "Executed this" in text


def test_esign_tags_number_signers_in_document_order(tmp_path):
    """A will's shape: testator (whereof) then two witnesses. Roles
    must come out Signer 1..3 so `sc esign send --to` order maps."""
    proc = build(tmp_path,
                 "\\signblock{whereof}{JANE ROE}{Testator}{Will}\n\n"
                 "## Witness Attestation\n\nWe attest.\n\n"
                 "\\witnessattestation{First Witness\\\\Second Witness}")
    assert proc.returncode == 0, proc.stderr
    # Raw (reading-order) extraction keeps each drawn tag string whole;
    # -layout would scatter column-positioned fragments.
    raw = subprocess.run(
        ["pdftotext", str(tmp_path / "doc.pdf"), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    flat = " ".join(raw.split())
    assert "{{Signature 1;role=Signer 1;type=signature}}" in flat
    assert "{{Signature 2;role=Signer 2;type=signature}}" in flat
    assert "{{Signature 3;role=Signer 3;type=signature}}" in flat
    assert "{{Location 1;role=Signer 1;type=text}}" in flat
    assert "{{Date 2;role=Signer 2;type=date}}" in flat
    assert "{{Residence 3;role=Signer 3;type=text}}" in flat


def test_tags_do_not_disturb_printed_lines(tmp_path):
    """The tags live in the text layer but the printed lines extract
    whole — the tag is its own extraction line, never interleaved."""
    build(tmp_path, "\\signblock{decl}{JANE ROE}{Springfield, California}")
    text = text_of(tmp_path)
    import datetime
    year = datetime.date.today().year
    assert (f"Executed this _____ day of _________________, {year}, "
            f"at Springfield, California.") in text
