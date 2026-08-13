"""California notarial certificates render whole, verbatim, and sealed-for.

What must never regress: the statutory wording (a certificate with
paraphrased wording is a certificate a recorder can reject), the
consumer-disclosure text the 2015 amendments require in a box, the
certificate landing on ONE page however the surrounding document
flows, and enough clear space that a stamp stays photographically
reproducible. Geometry (the boxes, the seal zone) is verified
visually and pinned here by proxy: title and (Seal) marker share a
page, and nothing else's text intrudes between them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

import shutil  # noqa: E402

pdftotext = shutil.which("pdftotext")
pytestmark = pytest.mark.skipif(pdftotext is None, reason="pdftotext not installed")

FRONT = """---
doctype: document
heading_numbers: false
paper_title: "Test Instrument"
---

# Article I. Body

{body}
"""

DISCLOSURE_START = "A notary public or other officer completing this"
ACK_PHRASE = "who proved to me on the basis of satisfactory evidence to be"
JURAT_PHRASE = "Subscribed and sworn to (or affirmed) before me"
PROOF_PHRASE = "as a witness thereto, on the oath of"


def build(tmp_path: Path, body: str) -> str:
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body=body))
    out = tmp_path / "doc.pdf"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / "md_pleading.py"), str(src), str(out)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    return subprocess.run(
        ["pdftotext", "-layout", str(out), "-"],
        check=True, capture_output=True, text=True,
    ).stdout


def test_acknowledgment_wording_is_statutory_and_complete(tmp_path):
    text = build(tmp_path, "Executed below.\n\n\\acknowledgment{JANE ROE}")
    assert DISCLOSURE_START in text
    assert "personally appeared JANE ROE" in " ".join(text.split())
    assert ACK_PHRASE in " ".join(text.split())
    assert "I certify under PENALTY OF PERJURY under the laws" in " ".join(text.split())
    assert "WITNESS my hand and official seal." in text
    assert "(Seal)" in text


def test_jurat_wording_is_statutory(tmp_path):
    text = " ".join(build(tmp_path, "\\jurat{JANE ROE}").split())
    assert JURAT_PHRASE in text
    assert "by JANE ROE, proved to me on the basis of satisfactory evidence" in text
    # A jurat is not an acknowledgment: no perjury certification block.
    assert "PENALTY OF PERJURY" not in text


def test_proof_of_execution_names_witness_and_principal(tmp_path):
    text = " ".join(
        build(tmp_path, "\\proofofexecution{JOHN SMITH}{JANE ROE}").split()
    )
    assert "personally appeared JOHN SMITH (name of subscribing witness)" in text
    assert "saw/heard JANE ROE" in text
    assert "at the request of JANE ROE" in text
    assert PROOF_PHRASE in text


def test_empty_signer_leaves_a_ruled_blank(tmp_path):
    text = " ".join(build(tmp_path, "\\acknowledgment{}").split())
    assert "personally appeared ____" in text


def test_certificate_is_never_split_across_pages(tmp_path):
    """Push the certificate to the bottom of a page; it must move to
    the next page whole rather than straddle the break."""
    filler = "\n\n".join(
        f"#. Paragraph {i} pads the page so the certificate lands near "
        f"the bottom and the keep-together logic has to act."
        for i in range(1, 26)
    )
    text = build(tmp_path, filler + "\n\n\\acknowledgment{JANE ROE}")
    pages = text.split("\f")
    holding = [p for p in pages if "ACKNOWLEDGMENT" in p]
    assert len(holding) == 1, "certificate title must appear on exactly one page"
    page = holding[0]
    # The whole certificate — title through seal line — is on that page.
    assert DISCLOSURE_START in page
    assert "(Seal)" in page
    assert "WITNESS my hand and official seal." in page


def test_witness_attestation_renders_one_grid_per_witness(tmp_path):
    text = build(
        tmp_path,
        "We attest as stated.\n\n\\witnessattestation{John Smith\\\\Mary Major}",
    )
    assert "Signature of John Smith" in text
    assert "Signature of Mary Major" in text
    assert text.count("Residing at (city and state)") == 2


def test_renderers_share_the_statutory_constants():
    """The DOCX and TXT renderers import the wording from md_pleading;
    a second copy of a statutory text is the copy that drifts."""
    docx_src = (PLEADING_DIR / "md_to_docx.py").read_text()
    txt_src = (PLEADING_DIR / "md_to_txt.py").read_text()
    for src in (docx_src, txt_src):
        assert "mp.NOTARIAL_DISCLOSURE" in src or "mp.notarial_text" in src
        assert mp.NOTARIAL_DISCLOSURE[:40] not in src, (
            "statutory text duplicated instead of imported"
        )
