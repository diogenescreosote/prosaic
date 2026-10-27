"""Contract checks for the exhibit/redaction helper CLIs.

Fictional inputs only. redact_pdf.py gets the adversarial treatment:
the redacted phrase must be unrecoverable from the output (true
content removal, not draw-over). timestamp.py is tested only on its
offline paths — no network calls.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.scenarios.pleading_exhibits import util

PLEADING = util.PLEADING
PY = sys.executable


def run_cli(script: str, *args: str, cwd: Path | None = None,
            env: dict[str, str] | None = None):
    merged_env = {**os.environ, **env} if env else None
    return subprocess.run([PY, str(PLEADING / script), *args],
                          capture_output=True, text=True, cwd=cwd,
                          env=merged_env)


# ---------------------------------------------------------------------------
# tsv_to_exhibit.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def tsv(tmp_path):
    f = tmp_path / "msgs.tsv"
    f.write_text(
        "Jan 05, 2026 10:00:00 AM\tme\t+15555550111\tHello TSVMSG-1 from Jane\n"
        "Feb 07, 2026 09:30:00 AM\t+15555550111\tme\tReply TSVMSG-2 from John\n"
    )
    return f


def test_tsv_to_exhibit_renders_labeled_messages(tsv, tmp_path):
    out = tmp_path / "texts.pdf"
    proc = run_cli("tsv_to_exhibit.py", str(tsv), str(out),
                   "--title", "Text Message Exhibit",
                   "--me", "Jane Roe", "--them", "John Smith")
    assert proc.returncode == 0, proc.stderr
    text = util.pdf_text(out)
    assert "Text Message Exhibit" in text
    assert "Jane Roe:" in text and "John Smith:" in text
    assert "TSVMSG-1" in text and "TSVMSG-2" in text


def test_tsv_to_exhibit_date_filters(tsv, tmp_path):
    out = tmp_path / "filtered.pdf"
    proc = run_cli("tsv_to_exhibit.py", str(tsv), str(out),
                   "--title", "T", "--after", "2026-02-01")
    assert proc.returncode == 0, proc.stderr
    text = util.pdf_text(out)
    assert "TSVMSG-2" in text
    assert "TSVMSG-1" not in text, "--after did not exclude older message"


# ---------------------------------------------------------------------------
# timestamp.py (offline paths only)
# ---------------------------------------------------------------------------

def test_timestamp_missing_file_exits_nonzero(tmp_path):
    proc = run_cli("timestamp.py", str(tmp_path / "no_such.pdf"))
    assert proc.returncode == 1
    assert "not found" in proc.stderr


def test_timestamp_skips_non_pdf(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("not a pdf")
    proc = run_cli("timestamp.py", str(f))
    assert proc.returncode == 0
    assert "skipping non-PDF" in proc.stdout


def test_timestamp_skips_when_sidecar_current(tmp_path):
    """A fresh .tsr sidecar short-circuits before any network I/O."""
    pdf = tmp_path / "doc.pdf"
    util.make_text_pdf(pdf, ["hello"])
    sidecar = pdf.with_suffix(".tsr")
    sidecar.write_bytes(b"existing-token")
    os.utime(sidecar)  # ensure sidecar mtime >= pdf mtime
    proc = run_cli("timestamp.py", str(pdf))
    assert proc.returncode == 0
    assert "already timestamped, skipping" in proc.stdout
    assert sidecar.read_bytes() == b"existing-token"


def test_timestamp_tsa_failure_exits_nonzero(tmp_path):
    """A TSA/network failure must fail the run: a batch that timestamped
    nothing must not look successful in scripts/CI. Points the TSA URL at
    a closed local port — the request fails without leaving the machine."""
    pdf = tmp_path / "doc.pdf"
    util.make_text_pdf(pdf, ["hello"])
    proc = run_cli("timestamp.py", str(pdf),
                   env={"PROSAIC_TSA_URL": "http://127.0.0.1:1/tsr"})
    assert proc.returncode != 0, "TSA failure exited 0"
    assert "ERROR" in proc.stderr
    assert not pdf.with_suffix(".tsr").exists()


# ---------------------------------------------------------------------------
# redact_pdf.py
# ---------------------------------------------------------------------------

SECRET = "SECRET-XJQ-99"


@pytest.fixture()
def redact_setup(tmp_path):
    src = tmp_path / "source.pdf"
    util.make_text_pdf(src, [
        f"Paragraph one mentions {SECRET} in a confidential clause.",
        "Page two is entirely innocuous.",
    ])
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "source_pdf": "source.pdf",
        "output_pdf": "redacted.pdf",
        "redactions": [{
            "type": "redact_clause",
            "description": "remove the secret token",
            "search_text": SECRET,
            "label": "[REDACTED-OK]",
        }],
    }))
    return cfg, tmp_path / "redacted.pdf"


def test_redact_pdf_removes_phrase_from_bytes(redact_setup):
    """CRITICAL: the phrase must be gone from extracted text, raw bytes,
    and decoded streams — a draw-over would be a privacy catastrophe."""
    cfg, out = redact_setup
    proc = run_cli("redact_pdf.py", str(cfg))
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    assert not util.contains_text(out, SECRET), (
        "redacted phrase recoverable from output PDF")
    assert "[REDACTED-OK]" in util.pdf_text(out)
    # Unredacted content survives.
    assert "entirely innocuous" in util.pdf_text(out)


def test_redact_pdf_caches_until_stale(redact_setup):
    cfg, out = redact_setup
    assert run_cli("redact_pdf.py", str(cfg)).returncode == 0
    again = run_cli("redact_pdf.py", str(cfg))
    assert again.returncode == 0
    assert "is up to date" in again.stdout
    check = run_cli("redact_pdf.py", str(cfg), "--check-stale")
    assert check.returncode == 0
    os.utime(cfg)  # config newer than output -> stale
    check2 = run_cli("redact_pdf.py", str(cfg), "--check-stale")
    assert check2.returncode == 1
    assert "STALE" in check2.stderr


def test_redact_pdf_no_match_fails_and_writes_nothing(tmp_path):
    """A redaction entry matching nothing (typo'd search_text) means the
    sensitive text is still present: the build must exit nonzero, name
    the unmatched entry on stderr, and write NO output — never a
    'successful' partially-redacted PDF."""
    src = tmp_path / "source.pdf"
    util.make_text_pdf(src, [f"The clause {SECRET} stays put."])
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "source_pdf": "source.pdf",
        "output_pdf": "redacted.pdf",
        "redactions": [{
            "type": "redact_clause",
            "search_text": "PHRASE-WITH-A-TYPO",
            "label": "[REDACTED]",
        }],
    }))
    proc = run_cli("redact_pdf.py", str(cfg))
    assert proc.returncode != 0, "no-match redaction exited 0"
    assert "no matches" in proc.stderr
    assert "PHRASE-WITH-A-TYPO" in proc.stderr, (
        "stderr does not name the unmatched entry:\n" + proc.stderr)
    assert not (tmp_path / "redacted.pdf").exists(), (
        "output written despite an unapplied redaction")


def test_redact_pdf_unknown_op_type_fails(tmp_path):
    """A typo'd operation type silently skips an entire redaction — same
    hazard as a no-match entry, same contract: fail, write nothing."""
    src = tmp_path / "source.pdf"
    util.make_text_pdf(src, [f"The clause {SECRET} stays put."])
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "source_pdf": "source.pdf",
        "output_pdf": "redacted.pdf",
        "redactions": [{
            "type": "redact_clauze",
            "search_text": SECRET,
            "label": "[REDACTED]",
        }],
    }))
    proc = run_cli("redact_pdf.py", str(cfg))
    assert proc.returncode != 0
    assert "unknown operation type" in proc.stderr
    assert not (tmp_path / "redacted.pdf").exists()


# ---------------------------------------------------------------------------
# redact_pdf.py: hyperlinked URLs in a tagged PDF
# ---------------------------------------------------------------------------

LINK_SECRET = "XQ7-SECRETPATH"
LINK_URL = f"https://files.example.com/share/{LINK_SECRET}"


def _make_tagged_link_pdf(path: Path, *, link_on_url: bool = True,
                          orphan: bool = False) -> None:
    """A one-page tagged PDF whose printed URL is also a link annotation.

    The structure tree holds a /Link element with the URL as /Alt and an
    OBJR pointing at the annotation through /StructParent: the shape a
    word processor's "export tagged PDF" produces. That reference is
    what kept a redacted URL alive in the saved file (Oct 2026).

    link_on_url=False puts the link over other text ("click here"), so
    the redaction box never touches it but its /URI still names the URL.
    orphan=True drops the annotation from the page's /Annots up front,
    leaving the structure tree as its only referrer.
    """
    import fitz  # type: ignore[import]

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Intro text before the link.")
    page.insert_text((72, 130), LINK_URL)
    page.insert_text((72, 190), "Click here for the folder.")
    if link_on_url:
        width = fitz.get_text_length(LINK_URL, fontsize=11)
        rect = fitz.Rect(72, 118, 72 + width, 134)
    else:
        rect = fitz.Rect(72, 178, 200, 194)
    page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": LINK_URL})
    page.insert_text((72, 160), "Closing text after the link.")
    doc = fitz.open("pdf", doc.tobytes())
    page = doc[0]
    annot = page.get_links()[0]["xref"]
    root, docel, linkel, ptree = (doc.get_new_xref() for _ in range(4))
    doc.update_object(ptree, f"<< /Nums [0 {linkel} 0 R] >>")
    doc.update_object(root, f"<< /Type /StructTreeRoot /K {docel} 0 R "
                            f"/ParentTree {ptree} 0 R /ParentTreeNextKey 1 >>")
    doc.update_object(docel, f"<< /Type /StructElem /S /Document "
                             f"/P {root} 0 R /K [{linkel} 0 R] >>")
    doc.update_object(linkel, (
        f"<< /Type /StructElem /S /Link /P {docel} 0 R /Pg {page.xref} 0 R "
        f"/Alt ({LINK_URL}) /K [<< /Type /OBJR /Obj {annot} 0 R "
        f"/Pg {page.xref} 0 R >>] >>"))
    doc.xref_set_key(annot, "StructParent", "0")
    if orphan:
        doc.xref_set_key(page.xref, "Annots", "[]")
    cat = doc.pdf_catalog()
    doc.xref_set_key(cat, "StructTreeRoot", f"{root} 0 R")
    doc.xref_set_key(cat, "MarkInfo", "<< /Marked true >>")
    doc.save(str(path))


@pytest.mark.parametrize("link_on_url,orphan", [
    (True, False),    # the box covers the link itself
    (False, False),   # the link sits elsewhere but targets the redacted URL
    (True, True),     # the annotation was already orphaned in the source
], ids=["covered", "elsewhere", "orphaned"])
def test_redact_pdf_strips_link_uri_under_redaction(tmp_path, link_on_url,
                                                    orphan):
    """A redacted URL must not survive as a link's /URI, a struct-tree
    /Alt, or an orphaned annotation the structure tree still references:
    verify_redactions finds nothing in raw bytes or decoded streams."""
    src = tmp_path / "source.pdf"
    _make_tagged_link_pdf(src, link_on_url=link_on_url, orphan=orphan)
    assert util.contains_text(src, LINK_SECRET)  # the fixture carries it
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "source_pdf": "source.pdf",
        "output_pdf": "redacted.pdf",
        "redactions": [{
            "type": "redact_clause",
            "description": "remove the shared-folder URL",
            "search_text": LINK_URL,
            "label": "[REDACTED-OK]",
        }],
    }))
    proc = run_cli("redact_pdf.py", str(cfg))
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "redacted.pdf"

    terms = tmp_path / "terms.txt"
    terms.write_text(f"{LINK_SECRET}\nfiles.example.com\n")
    check = run_cli("verify_redactions.py", str(out), "--terms", str(terms),
                    "--config", str(cfg))
    assert "## Raw bytes and decompressed streams: CLEAN" in check.stdout, (
        check.stdout)
    assert check.returncode == 0, check.stdout + check.stderr
    assert LINK_SECRET.encode() not in out.read_bytes()

    import fitz  # type: ignore[import]
    with fitz.open(str(out)) as doc:
        assert doc[0].get_links() == []
        text = doc[0].get_text()
    # Neighbouring content and the tagging survive.
    assert "Intro text before the link." in text
    assert "Closing text after the link." in text
    assert b"/StructTreeRoot" in out.read_bytes()
