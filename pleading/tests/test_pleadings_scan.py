"""pleadings_scan: filed-looking documents, and its duplicate rules.

The scanner's promise is twofold: a court-stamped document the record
holds but pleadings/ does not gets reported, and the same document is
never reported twice for the wrong reason. Byte-identity with a
pleadings/ file suppresses; a hash a MANIFEST row cites suppresses; a
recorded human dismissal suppresses; mere text similarity does NOT --
a corrected filing with the same words and different bytes must
surface. Every fixture here is synthetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import pleadings_scan as ps  # noqa: E402


def make_doc(matter: Path, rel: str, pdf_bytes: bytes, text: str) -> None:
    orig = matter / rel
    orig.parent.mkdir(parents=True, exist_ok=True)
    orig.write_bytes(pdf_bytes)
    sidecar = matter / "derived" / "text" / (rel + ".txt")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(f"[[[ sidecar ]]]\n{text}\n")


def make_matter(tmp_path: Path) -> Path:
    matter = tmp_path / "matter"
    (matter / "pleadings").mkdir(parents=True)
    (matter / "derived" / "text").mkdir(parents=True)
    return matter


STAMP = "ELECTRONICALLY FILED\nClerk of the Court\nBy: A. Nother, Deputy Clerk"


def run(matter, capsys):
    status = ps.scan(matter)
    return status, capsys.readouterr().out


def test_stamped_attachment_is_reported(tmp_path, capsys):
    matter = make_matter(tmp_path)
    make_doc(matter, "assets/mail/attachments/t1/order.pdf", b"%PDF-A",
             f"ORDER ON REQUEST\n{STAMP}")
    status, out = run(matter, capsys)
    assert status == 1
    assert "assets/mail/attachments/t1/order.pdf" in out


def test_byte_identical_pleading_suppresses(tmp_path, capsys):
    matter = make_matter(tmp_path)
    make_doc(matter, "assets/mail/attachments/t1/order.pdf", b"%PDF-A",
             f"ORDER ON REQUEST\n{STAMP}")
    (matter / "pleadings" / "2026-01-01_order.pdf").write_bytes(b"%PDF-A")
    status, out = run(matter, capsys)
    assert status == 0


def test_manifest_cited_hash_suppresses(tmp_path, capsys):
    matter = make_matter(tmp_path)
    make_doc(matter, "assets/mail/attachments/t1/order.pdf", b"%PDF-A",
             f"ORDER ON REQUEST\n{STAMP}")
    digest = ps.sha256(matter / "assets/mail/attachments/t1/order.pdf")
    (matter / "pleadings" / "MANIFEST.md").write_text(
        f"| `x.pdf` | as-served | SHA-256 `{digest[:8]}…` | note |\n")
    status, out = run(matter, capsys)
    assert status == 0


def test_same_text_different_bytes_still_surfaces_with_hint(tmp_path, capsys):
    matter = make_matter(tmp_path)
    text = f"ORDER ON REQUEST\n{STAMP}"
    make_doc(matter, "assets/mail/attachments/t1/order_v2.pdf", b"%PDF-B",
             text)
    (matter / "pleadings" / "2026-01-01_order.pdf").write_bytes(b"%PDF-A")
    sidecar = (matter / "derived" / "text" / "pleadings"
               / "2026-01-01_order.pdf.txt")
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text(f"[[[ sidecar ]]]\n{text}\n")
    status, out = run(matter, capsys)
    assert status == 1
    assert "same text as pleadings/2026-01-01_order.pdf" in out


def test_dismissal_by_hash_suppresses(tmp_path, capsys):
    matter = make_matter(tmp_path)
    make_doc(matter, "assets/records/production.pdf", b"%PDF-C",
             f"exhibit bundle containing a MINUTE ORDER\n{STAMP}")
    digest = ps.sha256(matter / "assets/records/production.pdf")
    (matter / "pleadings" / "SCAN_DISMISSALS.md").write_text(
        f"`{digest[:12]}`  records production; merely contains an order\n")
    status, out = run(matter, capsys)
    assert status == 0


def test_identical_copies_collapse_to_one_row(tmp_path, capsys):
    matter = make_matter(tmp_path)
    text = f"ORDER GRANTING THINGS\n{STAMP}"
    make_doc(matter, "assets/mail/attachments/t1/o.pdf", b"%PDF-D", text)
    make_doc(matter, "assets/mail/attachments/t2/o.pdf", b"%PDF-D", text)
    status, out = run(matter, capsys)
    assert status == 1
    assert out.count("sha256") == 1
    assert "t1/o.pdf" in out and "t2/o.pdf" in out


def test_weak_signals_alone_do_not_flag(tmp_path, capsys):
    matter = make_matter(tmp_path)
    make_doc(matter, "assets/forms_like/blank.pdf", b"%PDF-E",
             "JUDICIAL OFFICER:\nCASE NUMBER:\n(a blank form footer)")
    make_doc(matter, "assets/mail/clerk_email.pdf", b"%PDF-F",
             "See attached receipt.\nS. Body\nDeputy Clerk")
    status, out = run(matter, capsys)
    assert status == 0


def test_acceptance_without_manifest_row_flags_filing_id(tmp_path, capsys):
    matter = make_matter(tmp_path)
    make_doc(matter, "assets/mail/acceptance.pdf", b"%PDF-G",
             "Filing ID 12345678 Accepted on 24CV00000 - Doe/Roe\n"
             "Envelope Number: 87654321")
    status, out = run(matter, capsys)
    assert status == 1
    assert "12345678" in out and "87654321" in out


def test_acceptance_cited_in_manifest_is_quiet(tmp_path, capsys):
    matter = make_matter(tmp_path)
    make_doc(matter, "assets/mail/acceptance.pdf", b"%PDF-G",
             "Filing ID 12345678 Accepted on 24CV00000 - Doe/Roe")
    (matter / "pleadings" / "MANIFEST.md").write_text(
        "| `y.pdf` | conformed | acceptance email, Filing ID 12345678 "
        "| note |\n")
    status, out = run(matter, capsys)
    assert status == 0
