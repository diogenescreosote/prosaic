"""Helpers for the pleading_exhibits scenario.

Exhibit binaries are generated at test setup (not checked in) so the
fixture stays text-only. Every generated artifact carries a unique
sentinel string so tests can prove presence/absence in built output.

The leak-scan helper is deliberately paranoid: a redaction that merely
*draws over* text would still leave the string extractable, so absence
is checked in extracted text, raw file bytes, and every decoded
content stream.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
PLEADING = REPO / "pleading"
PYTHON = sys.executable

# Sentinels planted in the fixture sources / generated exhibits.
SEALED_NAME = "Wilhelmina Quixote"
SEALED_POSSESSIVE = "Wilhelmina's"
PUBLIC_NAME = "W.Q."
SEALED_PHRASE_TOKEN = "QQSEALED"
PUBLIC_PHRASE = "[medical information redacted]"
JUSTIFICATION_TOKEN = "JUSTIF-99"
SMITHMAIL = ["SMITHMAIL-PAGE-1", "SMITHMAIL-PAGE-2", "SMITHMAIL-PAGE-3"]
MEDSUM_TOKEN = "MEDSUM-SENTINEL-CONFIDENTIAL"
INTAKE_UNREDACTED = "SENTINEL-INTAKE-UNREDACTED"
INTAKE_REDACTED = "SENTINEL-INTAKE-REDACTEDVER"
STATIC_NOTICE = "STATIC-NOTICE-SENTINEL"

DECL_MD = "Declaration of Jane Roe.md"
DECL_PDF = "Declaration of Jane Roe.pdf"
MEMO_PDF = "Memo of Points.pdf"
ORDER_PDF = "Proposed Order.pdf"
ORDER_DOCX = "Proposed Order.docx"


def make_text_pdf(path: Path, pages: list[str]) -> None:
    """Write a tiny PDF with one text line per page (Helvetica, extractable)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    for text in pages:
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, text)
        c.showPage()
    c.save()


def make_image(path: Path) -> None:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (320, 240), (200, 220, 240))
    img.save(path)


def generate_binaries(matter: Path) -> None:
    """Create the exhibit/asset binaries the fixture sources reference."""
    ex = matter / "exhibits"
    make_text_pdf(ex / "smith_email.pdf", SMITHMAIL)
    make_image(ex / "roe_texts.png")
    make_text_pdf(ex / "medical_summary.pdf", [MEDSUM_TOKEN])
    make_text_pdf(ex / "intake_form.pdf",
                  [f"Intake paperwork {INTAKE_UNREDACTED} signed by parties"])
    make_text_pdf(ex / "intake_form_redacted.pdf",
                  [f"Intake paperwork {INTAKE_REDACTED} signed by parties"])
    make_text_pdf(matter / "assets" / "static_notice.pdf", [STATIC_NOTICE])


def load_matter(tmp_path: Path) -> Path:
    from tests.harness import scenario
    matter = scenario.load_scenario("pleading_exhibits", tmp_path)
    generate_binaries(matter)
    return matter


def run_build(matter: Path, *args: str) -> subprocess.CompletedProcess:
    """Run build_envelope.py in a matter directory with explicit args."""
    return subprocess.run(
        [PYTHON, str(PLEADING / "build_envelope.py"), *args],
        cwd=matter, capture_output=True, text=True,
    )


def run_md_pleading(input_md: Path, output_pdf: Path,
                    *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, str(PLEADING / "md_pleading.py"),
         str(input_md), str(output_pdf), *args],
        capture_output=True, text=True,
    )


def pdf_text(pdf: Path, layout: bool = True) -> str:
    from tests.harness import scenario
    return scenario.pdf_text(pdf, layout=layout)


def pdf_page_texts(pdf: Path) -> list[str]:
    return pdf_text(pdf).split("\f")


def normalized_text(pdf: Path) -> str:
    import re
    return re.sub(r"\s+", " ", pdf_text(pdf))


def stripped_text(pdf: Path) -> str:
    """Whitespace-normalized text with the pleading line-number margin
    removed, so multi-word needles survive line wraps (the 28-line
    margin numbers otherwise interleave into extracted sentences)."""
    import re
    out = []
    for ln in pdf_text(pdf).splitlines():
        out.append(re.sub(r"^\s*\d{1,2}(?=\s{2,}|\s*$)", "", ln))
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def decoded_streams(pdf: Path) -> bytes:
    """Concatenate every decodable stream in the PDF (content, XObjects...)."""
    from pypdf import PdfReader
    out = []
    reader = PdfReader(str(pdf))
    for page in reader.pages:
        contents = page.get_contents()
        if contents is not None:
            try:
                out.append(contents.get_data())
            except Exception:
                pass
        resources = page.get("/Resources")
        if resources:
            xobjects = resources.get_object().get("/XObject")
            if xobjects:
                for x in xobjects.get_object().values():
                    try:
                        out.append(x.get_object().get_data())
                    except Exception:
                        pass
    return b"\n".join(out)


def contains_text(pdf: Path, needle: str) -> bool:
    """True if needle appears in extracted text, raw bytes, or any
    decoded stream of the PDF. Used symmetrically: positive controls
    assert True on sealed builds; leak checks assert False on public."""
    if needle in normalized_text(pdf) or needle in stripped_text(pdf):
        return True
    raw = pdf.read_bytes()
    nb = needle.encode("utf-8", "replace")
    if nb in raw:
        return True
    if nb in decoded_streams(pdf):
        return True
    # Document info / metadata values.
    from pypdf import PdfReader
    reader = PdfReader(str(pdf))
    meta = reader.metadata or {}
    for v in meta.values():
        if needle in str(v):
            return True
    return False
