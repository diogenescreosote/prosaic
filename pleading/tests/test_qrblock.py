"""\\qrblock puts a machine-readable payload on the page, and it has to
actually read back.

The point of a QR block (a verification URL, an armored public key, a
detached signature) is that a phone camera recovers the exact payload
without OCR errors. So the property tested is the round trip: render
the PDF, rasterize the page, decode the symbol, compare bytes. A QR
that renders beautifully but decodes to a corrupted key block is worse
than no QR at all.

Decoding needs zbarimg and rasterizing needs pdftoppm (both in
system-dependencies.yaml); the round-trip tests skip without them,
but the structural checks (caption text, build failures, the TXT
fallback) run everywhere qrencode exists.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

qrencode = shutil.which("qrencode")
zbarimg = shutil.which("zbarimg")
pdftoppm = shutil.which("pdftoppm")
pdftotext = shutil.which("pdftotext")

pytestmark = pytest.mark.skipif(
    qrencode is None, reason="qrencode not installed")

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
---

I, Jane Roe, declare as follows:

#. The following code verifies this declaration.

{qr_lines}
"""

# A payload with the shape that matters in practice: multi-line,
# base64-ish, long enough to force a dense symbol.
KEYISH_PAYLOAD = (
    "-----BEGIN EXAMPLE KEY BLOCK-----\n"
    + "\n".join("mDMEaExampleExampleExampleExampleExampleExampleExample%02d" % i
                for i in range(10))
    + "\n-----END EXAMPLE KEY BLOCK-----"
)


def build(tmp_path: Path, qr_lines: str, renderer: str = "md_pleading.py",
          out_name: str = "out.pdf") -> subprocess.CompletedProcess:
    src = tmp_path / "decl.md"
    src.write_text(FRONT.format(qr_lines=qr_lines))
    out = tmp_path / out_name
    return subprocess.run(
        [sys.executable, str(PLEADING_DIR / renderer), str(src), str(out)],
        capture_output=True, text=True, cwd=tmp_path,
    )


def decode_qr(pdf: Path, tmp_path: Path) -> str:
    subprocess.run(
        [pdftoppm, "-png", "-r", "200", str(pdf), str(tmp_path / "page")],
        check=True, capture_output=True,
    )
    pages = sorted(tmp_path.glob("page*.png"))
    assert pages, "pdftoppm produced no pages"
    for page in pages:
        proc = subprocess.run(
            [zbarimg, "--raw", "--quiet", str(page)],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    pytest.fail("no page contained a decodable QR symbol")


@pytest.mark.skipif(not (zbarimg and pdftoppm),
                    reason="zbarimg/pdftoppm not installed")
def test_inline_payload_round_trips(tmp_path):
    proc = build(tmp_path, "\\qrblock{https://example.com/verify/24CV00000}{Scan to verify.}")
    assert proc.returncode == 0, proc.stderr
    assert decode_qr(tmp_path / "out.pdf", tmp_path) == "https://example.com/verify/24CV00000"


@pytest.mark.skipif(not (zbarimg and pdftoppm),
                    reason="zbarimg/pdftoppm not installed")
def test_file_payload_round_trips_byte_exact(tmp_path):
    """The estate-planning shape: an armored key block from a file.

    Byte-exact matters — one flipped character in a key block and the
    signature it anchors verifies against nothing.
    """
    (tmp_path / "key.asc").write_text(KEYISH_PAYLOAD + "\n")
    proc = build(tmp_path, "\\qrblockfile{key.asc}{Public key, machine-readable.}")
    assert proc.returncode == 0, proc.stderr
    assert decode_qr(tmp_path / "out.pdf", tmp_path) == KEYISH_PAYLOAD


@pytest.mark.skipif(pdftotext is None, reason="pdftotext not installed")
def test_caption_prints_under_the_symbol(tmp_path):
    proc = build(tmp_path, "\\qrblock{payload}{Scan to verify.}")
    assert proc.returncode == 0, proc.stderr
    text = subprocess.run(
        ["pdftotext", "-layout", str(tmp_path / "out.pdf"), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Scan to verify." in text


def test_missing_payload_file_fails_the_build(tmp_path):
    proc = build(tmp_path, "\\qrblockfile{no_such_file.asc}{caption}")
    assert proc.returncode != 0
    assert "no_such_file.asc" in proc.stderr


def test_txt_renderer_prints_the_payload_itself(tmp_path):
    (tmp_path / "key.asc").write_text(KEYISH_PAYLOAD)
    proc = build(tmp_path, "\\qrblockfile{key.asc}{Public key.}",
                 renderer="md_to_txt.py", out_name="out.txt")
    assert proc.returncode == 0, proc.stderr
    text = (tmp_path / "out.txt").read_text()
    assert "[QR code: Public key.]" in text
    assert "-----BEGIN EXAMPLE KEY BLOCK-----" in text


def test_docx_embeds_an_image(tmp_path):
    proc = build(tmp_path, "\\qrblock{https://example.com/verify}{Scan.}",
                 renderer="md_to_docx.py", out_name="out.docx")
    assert proc.returncode == 0, proc.stderr
    with zipfile.ZipFile(tmp_path / "out.docx") as z:
        media = [n for n in z.namelist() if n.startswith("word/media/")]
    assert media, "DOCX contains no embedded image for the QR block"
