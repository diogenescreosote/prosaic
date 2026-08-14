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


def make_text_pdf(path: Path, pages: list[str], *, title: str = "",
                  body: list[str] | None = None) -> None:
    """Write a document-shaped PDF: heading, body paragraph lines, and
    each page's sentinel as an extractable footer reference line.

    Realistic-looking props matter: the scenario's AI judge evaluates
    the built packet as a filing, and a one-line top-left page reads
    as a rendering defect rather than an exhibit (it once cost the
    judgment two points). The sentinel stays extractable — now as a
    footer "Ref:" line — so the deterministic checks are unchanged."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    for i, sentinel in enumerate(pages):
        y = 708
        if title:
            c.setFont("Helvetica-Bold", 13)
            c.drawString(72, y, title)
            y -= 26
        c.setFont("Helvetica", 11)
        for line in (body or []):
            c.drawString(72, y, line)
            y -= 15
        c.setFont("Helvetica", 8)
        c.drawString(72, 40, f"Page {i + 1} of {len(pages)} — Ref: {sentinel}")
        c.showPage()
    c.save()


def make_image(path: Path) -> None:
    """A text-message screenshot the way a phone actually shows one:
    header bar, alternating left/right chat bubbles, timestamps in the
    range the declaration recites (January 23 – March 3, 2026)."""
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = 700, 1000
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    def font(size: int, bold: bool = False):
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        ]
        for c in candidates:
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
        try:
            return ImageFont.load_default(size)
        except TypeError:  # older Pillow: fixed-size bitmap default
            return ImageFont.load_default()

    d.rectangle([0, 0, W, 64], fill=(245, 245, 247))
    d.text((W // 2, 32), "John Smith", font=font(24), fill=(20, 20, 20),
           anchor="mm")

    messages = [
        ("Jan 23, 2026", "Can we talk about the schedule this week?", False),
        ("Jan 23, 2026", "Yes. Thursday after 5 works for me.", True),
        ("Feb 2, 2026", "Following up on the email I sent Jan 15.", False),
        ("Feb 2, 2026", "I saw it. I'll reply with the documents.", True),
        ("Feb 18, 2026", "The counselor's office confirmed Tuesday.", False),
        ("Mar 3, 2026", "Received the intake form, signing today.", True),
    ]
    y = 84
    for stamp, text, mine in messages:
        d.text((W // 2, y), stamp, font=font(14), fill=(150, 150, 150),
               anchor="mm")
        y += 24
        f = font(18)
        tw = d.textlength(text, font=f)
        pad, bh = 14, 40
        if mine:
            box = [W - 24 - tw - 2 * pad, y, W - 24, y + bh]
            fill, tcol = (0, 122, 255), (255, 255, 255)
        else:
            box = [24, y, 24 + tw + 2 * pad, y + bh]
            fill, tcol = (233, 233, 235), (20, 20, 20)
        d.rounded_rectangle(box, radius=18, fill=fill)
        d.text((box[0] + pad, y + bh // 2), text, font=f, fill=tcol,
               anchor="lm")
        y += bh + 18
    img.save(path)


def generate_binaries(matter: Path) -> None:
    """Create the exhibit/asset binaries the fixture sources reference."""
    ex = matter / "exhibits"
    make_text_pdf(
        ex / "smith_email.pdf", SMITHMAIL,
        title="Message",
        body=[
            "From:    John Smith <j.smith@example.com>",
            "To:      Jane Roe <jane.roe@example.com>",
            "Date:    January 15, 2026, 9:41 AM",
            "Subject: Schedule and counseling paperwork",
            "",
            "Jane,",
            "",
            "Confirming what we discussed: I can do Thursdays after",
            "5:00 p.m. going forward. I have asked the counselor's",
            "office to send both of us the intake paperwork, and I",
            "will bring the signed copy to the next session.",
            "",
            "Please let me know if the Thursday time stops working.",
            "",
            "John",
        ])
    make_image(ex / "roe_texts.png")
    make_text_pdf(
        ex / "medical_summary.pdf", [MEDSUM_TOKEN],
        title="Springfield Medical Group — Clinical Summary",
        body=[
            "Patient: Jane Roe          Date of report: March 10, 2026",
            "Prepared by the treating physician at counsel's request.",
            "",
            "Summary of treatment course and clinical findings for the",
            "period January through March 2026, provided for filing",
            "under seal pursuant to the protective order.",
        ])
    make_text_pdf(
        ex / "intake_form.pdf",
        [f"Intake paperwork {INTAKE_UNREDACTED} signed by parties"],
        title="Counseling Intake Form",
        body=[
            "Provider: Springfield Family Counseling",
            "Clients:  Jane Roe; John Smith",
            "Date of intake: February 24, 2026",
            "",
            "The undersigned acknowledge the practice policies and",
            "consent to joint sessions as scheduled.",
        ])
    make_text_pdf(
        ex / "intake_form_redacted.pdf",
        [f"Intake paperwork {INTAKE_REDACTED} signed by parties"],
        title="Counseling Intake Form",
        body=[
            "Provider: Springfield Family Counseling",
            "Clients:  Jane Roe; John Smith",
            "Date of intake: February 24, 2026",
            "",
            "The undersigned acknowledge the practice policies and",
            "consent to joint sessions as scheduled.",
            "",
            "[Portions redacted pursuant to protective order.]",
        ])
    make_text_pdf(
        matter / "assets" / "static_notice.pdf", [STATIC_NOTICE],
        title="Notice of Related Case",
        body=[
            "Pursuant to local rule, notice is given of a related",
            "matter pending in this court between the same parties.",
        ])


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
