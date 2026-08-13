"""\\barcode puts a machine-readable payload on the page, and it has to
actually read back; \\fixedwidth puts verbatim text there, and it has
to stay verbatim.

The barcode property is the round trip: render the PDF, rasterize,
decode the symbol, compare bytes (ADR-0026). zbar decodes qr and
code128; PDF417 decodes through zxing-cpp (a dev dependency) and is
additionally pinned by geometry: the 3:1 aspect target and the
column-width cap. The fixedwidth property is that the typographic
pass never touches the content — an armored header whose ----- became
em dashes will never re-import into gpg from paper.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

qrencode = shutil.which("qrencode")
zint = shutil.which("zint")
zbarimg = shutil.which("zbarimg")
pdftoppm = shutil.which("pdftoppm")
pdftotext = shutil.which("pdftotext")

FRONT = """---
doctype: document
heading_numbers: false
paper_title: "Symbol Test"
---

# Article I. Body

The machine-readable material follows.

{body}
"""

ARMOR = (
    "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
    "\n"
    + "\n".join("mDMEaExampleExampleExampleExampleExampleExampleExample%02d" % i
                for i in range(6))
    + "\n=u7Lw\n-----END PGP PUBLIC KEY BLOCK-----"
)


def build(tmp_path: Path, body: str) -> Path:
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body=body))
    out = tmp_path / "doc.pdf"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    return out


def decode(pdf: Path, tmp_path: Path, symbology: str) -> str:
    subprocess.run(
        [pdftoppm, "-png", "-r", "300", str(pdf), str(tmp_path / "page")],
        check=True, capture_output=True,
    )
    for page in sorted(tmp_path.glob("page*.png")):
        proc = subprocess.run(
            [zbarimg, "--raw", "--quiet", "-Senable=0",
             f"-S{symbology}.enable=1", str(page)],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    pytest.fail(f"no page contained a decodable {symbology} symbol")


@pytest.mark.skipif(not (qrencode and zbarimg and pdftoppm),
                    reason="qrencode/zbarimg/pdftoppm not installed")
def test_qr_round_trips_byte_exact_from_a_file(tmp_path):
    (tmp_path / "key.asc").write_text(ARMOR + "\n")
    pdf = build(tmp_path, "\\barcodefile{qr}{key.asc}{The key.}")
    assert decode(pdf, tmp_path, "qrcode") == ARMOR


@pytest.mark.skipif(not (zint and zbarimg and pdftoppm),
                    reason="zint/zbarimg/pdftoppm not installed")
def test_code128_round_trips(tmp_path):
    fpr = "F15991EE7300FD42DBD2F3D0466DD18A60791844"
    pdf = build(tmp_path, "\\barcode{code128}{%s}{Fingerprint.}" % fpr)
    assert decode(pdf, tmp_path, "code128") == fpr


@pytest.mark.skipif(not (zint and pdftoppm), reason="zint/pdftoppm not installed")
def test_pdf417_round_trips_byte_exact(tmp_path):
    """The estate-instrument shape: an armored key block, decoded back
    off the rasterized page."""
    zxingcpp = pytest.importorskip("zxingcpp")
    from PIL import Image

    (tmp_path / "key.asc").write_text(ARMOR + "\n")
    pdf = build(tmp_path, "\\barcodefile{pdf417}{key.asc}{The key, as PDF417.}")
    subprocess.run(
        [pdftoppm, "-png", "-r", "300", str(pdf), str(tmp_path / "page")],
        check=True, capture_output=True,
    )
    for page in sorted(tmp_path.glob("page*.png")):
        for r in zxingcpp.read_barcodes(Image.open(page)):
            if r.format == zxingcpp.BarcodeFormat.PDF417:
                assert r.text.strip() == ARMOR
                return
    pytest.fail("no page contained a decodable PDF417 symbol")


@pytest.mark.skipif(zint is None, reason="zint not installed")
def test_pdf417_geometry_targets_three_to_one(tmp_path):
    """zbar cannot decode PDF417, so the promise pinned is geometric:
    the column search lands near the 3:1 target, at 0.5mm modules,
    never wider than the text column."""
    w, h = mp.barcode_image(
        "pdf417",
        "A payload long enough to give the column search something to "
        "work with, as an armored signature would.",
        str(tmp_path / "sym.png"),
    )
    assert 2.0 <= w / h <= 4.0, f"aspect {w / h:.2f} strays from the 3:1 target"
    assert w <= mp.LETTER_TEXT_WIDTH * 1.01


def test_unknown_format_is_a_clear_error(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body="\\barcode{aztec}{data}{caption}"))
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"),
         str(src), str(tmp_path / "doc.pdf")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode != 0
    assert "aztec" in proc.stderr


def test_missing_payload_file_fails_the_build(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body="\\barcodefile{qr}{missing.asc}{caption}"))
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"),
         str(src), str(tmp_path / "doc.pdf")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode != 0
    assert "missing.asc" in proc.stderr


@pytest.mark.skipif(pdftotext is None, reason="pdftotext not installed")
def test_fixedwidth_survives_the_typographic_pass(tmp_path):
    """The armor headers keep their ----- runs: no em dashes, no
    rewrapping, every line reproduced."""
    pdf = build(tmp_path, "\\fixedwidth{\n" + ARMOR + "\n}")
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "-----BEGIN PGP PUBLIC KEY BLOCK-----" in text
    assert "-----END PGP PUBLIC KEY BLOCK-----" in text
    assert "\u2014" not in text, "em dash crept into verbatim content"
    for line in ARMOR.splitlines():
        if line:
            assert line in text, f"verbatim line lost or altered: {line!r}"


@pytest.mark.skipif(pdftotext is None, reason="pdftotext not installed")
def test_fixedwidth_in_docx_and_txt_stay_verbatim(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body="\\fixedwidth{\n" + ARMOR + "\n}"))
    for renderer, out_name in (("md_to_txt.py", "doc.txt"),):
        proc = subprocess.run(
            [sys.executable, str(PLEADING_DIR / renderer),
             str(src), str(tmp_path / out_name)],
            capture_output=True, text=True, cwd=tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
        text = (tmp_path / out_name).read_text()
        assert "-----BEGIN PGP PUBLIC KEY BLOCK-----" in text
        assert "\u2014" not in text

    import zipfile
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_to_docx.py"),
         str(src), str(tmp_path / "doc.docx")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    xml = zipfile.ZipFile(tmp_path / "doc.docx").read("word/document.xml").decode()
    assert "-----BEGIN PGP PUBLIC KEY BLOCK-----" in xml
