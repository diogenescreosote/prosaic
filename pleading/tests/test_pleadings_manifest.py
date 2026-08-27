"""pleadings/ manifest checker: statuses, and the two spot-checks.

The distinction under test is the one the checker exists to keep
straight. A *filed* document bears a clerk's stamp. A *signed order* bears
a judicial officer's signature and no stamp, because orders are signed
rather than stamped. Before `signed_order` existed, such an order could
only be recorded `conformed` --- asserting a stamp that is not there ---
or `unverified`, which says provenance is unknown and files the court's
own order among the substitutes.

So each status is spot-checked against the thing it actually claims, and
neither check is allowed to demand the other's evidence.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLEADING_DIR = Path(__file__).resolve().parent.parent
CHECKER = PLEADING_DIR / "pleadings_manifest.py"
sys.path.insert(0, str(PLEADING_DIR))

fitz = pytest.importorskip("fitz")

import pleadings_manifest as pm  # noqa: E402


HEADER = """# pleadings/ MANIFEST

## Documents

| File | Status | Source | Notes |
|---|---|---|---|
"""


def make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 96), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def run(matter: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), str(matter), "--json"],
        capture_output=True, text=True,
    )
    assert proc.stdout, proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    (tmp_path / "pleadings").mkdir()
    return tmp_path


def write_manifest(matter: Path, *rows: str) -> None:
    (matter / "pleadings" / "MANIFEST.md").write_text(HEADER + "\n".join(rows) + "\n")


# --- the vocabulary --------------------------------------------------------


def test_signed_order_is_a_known_status_and_not_a_substitute():
    assert "signed_order" in pm.KNOWN
    assert "signed_order" not in pm.SUBSTITUTE
    assert "signed_order" in pm.AUTHENTIC


def test_signed_order_is_held_apart_from_filed():
    """Kept out of FILED so the stamp check never runs against it."""
    assert "signed_order" not in pm.FILED


# --- the two spot-checks ---------------------------------------------------


def test_a_signed_order_is_not_asked_for_a_filing_stamp(matter):
    make_pdf(matter / "pleadings" / "2026-08-26_order.pdf",
             "DENIAL OF APPLICATION Dated: 8/26/2026 Judicial Officer:")
    write_manifest(matter,
                   "| `2026-08-26_order.pdf` | signed_order | emailed by the court |  |")
    r = run(matter)
    assert r["claims_filed_but_no_stamp_found"] == []
    assert r["claims_signed_order_but_no_signature_line"] == []
    assert r["substitutes"] == []


def test_a_signed_order_without_a_signature_line_is_reported(matter):
    """The parallel guard: the claim must match the face."""
    make_pdf(matter / "pleadings" / "2026-08-26_order.pdf",
             "Some document with no judicial signature line at all.")
    write_manifest(matter,
                   "| `2026-08-26_order.pdf` | signed_order | emailed by the court |  |")
    r = run(matter)
    assert r["claims_signed_order_but_no_signature_line"] == ["2026-08-26_order.pdf"]


def test_a_filed_document_is_still_asked_for_a_stamp(matter):
    make_pdf(matter / "pleadings" / "2026-08-25_decl.pdf",
             "A declaration with no stamp anywhere on it.")
    write_manifest(matter,
                   "| `2026-08-25_decl.pdf` | conformed | handed over the counter |  |")
    r = run(matter)
    assert r["claims_filed_but_no_stamp_found"] == ["2026-08-25_decl.pdf"]
    # and it is not misreported under the signed-order check
    assert r["claims_signed_order_but_no_signature_line"] == []


def test_a_stamped_filing_passes(matter):
    make_pdf(matter / "pleadings" / "2026-08-25_decl.pdf",
             "ELECTRONICALLY FILED 8/25/2026 Clerk of the Court")
    write_manifest(matter,
                   "| `2026-08-25_decl.pdf` | conformed | portal |  |")
    r = run(matter)
    assert r["claims_filed_but_no_stamp_found"] == []


# --- what the status does not do -------------------------------------------


def test_signed_order_says_nothing_about_provenance(matter):
    """A signed order of unknown origin is still a substitute.

    The two questions are independent: `signed_order` describes the face
    of the document, `unverified` describes what is known about how it
    arrived. An order whose provenance was never established stays a
    substitute, and marking it `signed_order` must not launder that.
    """
    make_pdf(matter / "pleadings" / "2026-05-08_order.pdf",
             "DENIAL Dated: 5/8/2026 JUDICIAL OFFICER OF THE SUPERIOR COURT")
    write_manifest(matter,
                   "| `2026-05-08_order.pdf` | unverified | how this reached us is unestablished |  |")
    r = run(matter)
    assert [s["file"] for s in r["substitutes"]] == ["2026-05-08_order.pdf"]
    # unverified is not spot-checked for either kind of evidence
    assert r["claims_signed_order_but_no_signature_line"] == []
    assert r["claims_filed_but_no_stamp_found"] == []


def test_an_invented_status_is_rejected(matter):
    make_pdf(matter / "pleadings" / "x.pdf", "text")
    write_manifest(matter, "| `x.pdf` | court_copy_probably | vibes |  |")
    r = run(matter)
    assert r["unknown_status_values"] == [["x.pdf", "court_copy_probably"]]
