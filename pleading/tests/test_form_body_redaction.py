"""\\redact{} in a cover-sheet form field honors the build variant.

A declaration written entirely on the MC-030 body (`cover_sheet_only:`)
has no pleading body, so the redaction pass over the body never saw its
text. The macro printed literally, sealed argument and all, in the
PUBLIC variant. These tests read the drawn page of each variant.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLEADING_DIR = Path(__file__).resolve().parent.parent

SOURCE = """---
cover_sheet: mc030
cover_sheet_only: true
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
paper_title: "DECLARATION OF JANE ROE"
forms:
  mc030:
    body: |
      1. The registered owner is \\redact{SEALEDOWNERNAME}{the registered owner named in Exhibit A}.
---
"""


def _build(tmp_path: Path, variant: str) -> str:
    src = tmp_path / "decl.md"
    if not src.exists():  # rewriting would bump its mtime and mask a stale cache
        src.write_text(SOURCE)
    out = tmp_path / f"{variant}.pdf"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src),
         str(out), "--variant", variant],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return subprocess.run(["pdftotext", str(out), "-"], check=True,
                          capture_output=True, text=True).stdout


def test_public_variant_prints_the_substitute(tmp_path):
    text = _build(tmp_path, "public")
    assert "SEALEDOWNERNAME" not in text
    assert "\\redact" not in text
    assert "registered owner named in Exhibit A" in " ".join(text.split())


def test_sealed_variant_prints_the_sealed_text(tmp_path):
    text = _build(tmp_path, "sealed")
    assert "SEALEDOWNERNAME" in text
    assert "\\redact" not in text


def test_variants_built_in_turn_never_share_a_cached_fill(tmp_path):
    # Both variants of one source share a cover-sheet cache path; the
    # second build must refill, not reuse the first variant's form.
    assert "SEALEDOWNERNAME" in _build(tmp_path, "sealed")
    assert "SEALEDOWNERNAME" not in _build(tmp_path, "public")
    assert "SEALEDOWNERNAME" in _build(tmp_path, "sealed")
