"""Searchability is audited and repaired, never assumed (ADR-0041).

Fixtures are generated: a born-digital PDF, an image-only PDF (a
rendered page re-embedded as a raster), a PNG, and a DOCX. OCR steps are
skipped when the tool is absent; the classification and sidecar logic
are not.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import pymupdf as fitz

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "triage"))
import text_coverage as tc  # noqa: E402

SC = REPO_ROOT / "cli" / "sc"


def make_text_pdf(path: Path, pages: int = 2,
                  text: str = "The quick brown fox and the lazy dog") -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100), f"{text} page {i + 1} of {pages}. " * 4, fontsize=11)
    doc.save(str(path))
    doc.close()


def make_image_only_pdf(path: Path) -> None:
    src = fitz.open()
    page = src.new_page()
    page.insert_text((72, 100), "Handwritten note about the meeting on May 3", fontsize=14)
    pix = page.get_pixmap(dpi=120)
    src.close()
    doc = fitz.open()
    p = doc.new_page()
    p.insert_image(p.rect, pixmap=pix)
    doc.save(str(path))
    doc.close()


def make_png(path: Path) -> None:
    src = fitz.open()
    page = src.new_page()
    page.insert_text((72, 100), "A photographed exhibit", fontsize=16)
    page.get_pixmap(dpi=100).save(str(path))
    src.close()


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    m = tmp_path / "m"
    (m / "assets").mkdir(parents=True)
    (m / "out").mkdir()
    (m / "inbox").mkdir()
    (m / "matter.yaml").write_text("case:\n  name: Smith v. Roe\n")
    make_text_pdf(m / "assets" / "letter.pdf")
    make_image_only_pdf(m / "assets" / "scan.pdf")
    make_png(m / "assets" / "photo.png")
    make_text_pdf(m / "out" / "built.pdf")            # excluded
    make_text_pdf(m / "inbox" / "new.pdf")            # untriaged
    return m


def states(docs):
    return {d.path: d.state for d in docs}


def test_audit_classifies_every_document(matter: Path):
    st = states(tc.audit(matter))
    assert st["assets/letter.pdf"] == "needs-sidecar"
    assert st["assets/scan.pdf"] == "needs-ocr"
    assert st["assets/photo.png"] == "needs-ocr"
    assert st["inbox/new.pdf"] == "untriaged"
    assert "out/built.pdf" not in st


def test_ocr_sibling_alone_does_not_make_a_pdf_searchable(matter: Path):
    """The hole this module closes: rg cannot read a PDF, so an OCR'd copy
    without a text file is still unsearched. Legacy siblings are read."""
    make_text_pdf(matter / "assets" / "scan_ocr.pdf")   # a legacy sibling
    st = states(tc.audit(matter, use_cache=False))
    assert st["assets/scan.pdf"] == "needs-sidecar"
    assert "assets/scan_ocr.pdf" not in st, "siblings are audited through their original"


def test_legacy_tool_sidecar_is_recognized_and_migrated(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)
    legacy = matter / "assets" / "letter.txt"
    tc.write_pdf_sidecar(matter, matter / "assets" / "letter.pdf", matter / "assets" / "letter.pdf", legacy)
    d = {x.path: x for x in tc.audit(matter, use_cache=False)}["assets/letter.pdf"]
    assert d.state == "searchable" and "legacy location" in d.note
    (matter / "assets" / "photo.txt").write_text("a human wrote this")   # stays put
    moves = tc.migrate(matter)
    assert any("assets/letter.txt -> derived/text/assets/letter.pdf.txt" in m for m in moves)
    assert (matter / "derived" / "text" / "assets" / "letter.pdf.txt").exists()
    assert not legacy.exists()
    assert (matter / "assets" / "photo.txt").exists(), "human text files are never moved"
    assert "derived/ocr/" in (matter / ".gitignore").read_text()
    d = {x.path: x for x in tc.audit(matter, use_cache=False)}["assets/letter.pdf"]
    assert d.state == "searchable" and d.note == ""


def test_ensure_writes_page_marked_sidecars_without_ocr_tools(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)   # no ocrmypdf/tesseract/pandoc
    docs = tc.ensure(matter, jobs=1)
    st = states(docs)
    assert st["assets/letter.pdf"] == "searchable"
    side = (matter / "derived" / "text" / "assets" / "letter.pdf.txt").read_text()
    assert side.startswith(tc.HEADER_MARK)
    assert not (matter / "assets" / "letter.txt").exists(), "nothing is written beside the original"
    assert "pages: 2" in side and "[[[ page 2 of 2 ]]]" in side
    assert "quick brown fox" in side and tc.BANNER in side
    # what no tool could fix stays visible, with the reason
    assert st["assets/scan.pdf"] in ("needs-ocr", "unreadable")
    assert st["assets/photo.png"] == "needs-ocr"


def test_foreign_sidecar_is_never_overwritten(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)
    human = matter / "assets" / "letter.txt"
    human.write_text("A human wrote this transcription.")
    docs = tc.ensure(matter, jobs=1)
    assert states(docs)["assets/letter.pdf"] == "unverified-sidecar"
    assert human.read_text() == "A human wrote this transcription."


def test_stale_sidecar_is_detected_and_refreshed(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)
    tc.ensure(matter, jobs=1)
    side = matter / "derived" / "text" / "assets" / "letter.pdf.txt"
    old = side.stat().st_mtime - 100
    os.utime(side, (old, old))
    st = states(tc.audit(matter, use_cache=False))
    assert st["assets/letter.pdf"] == "stale-sidecar"
    docs = tc.ensure(matter, jobs=1)
    assert states(docs)["assets/letter.pdf"] == "searchable"


def test_cache_keys_on_size_and_mtime(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)
    tc.ensure(matter, jobs=1)
    assert (matter / ".state" / tc.CACHE_NAME).is_file()
    calls = []
    real = tc.classify_pdf
    monkeypatch.setattr(tc, "classify_pdf", lambda m, p: calls.append(p.name) or real(m, p))
    tc.audit(matter)
    assert "letter.pdf" not in calls, "unchanged documents come from the cache"
    time.sleep(0.01)
    make_text_pdf(matter / "assets" / "letter.pdf", pages=3)
    tc.audit(matter)
    assert "letter.pdf" in calls, "a changed document is re-surveyed"


@pytest.mark.skipif(not shutil.which("ocrmypdf"), reason="ocrmypdf not installed")
def test_ensure_ocrs_an_image_only_pdf(matter: Path):
    docs = tc.ensure(matter, jobs=1)
    st = states(docs)
    assert st["assets/scan.pdf"] == "searchable", [d for d in docs if d.path == "assets/scan.pdf"]
    assert (matter / "derived" / "ocr" / "assets" / "scan.pdf").exists()
    assert not (matter / "assets" / "scan_ocr.pdf").exists()
    side = (matter / "derived" / "text" / "assets" / "scan.pdf.txt").read_text().lower()
    assert "meeting" in side or "may" in side
    # the original is byte-identical
    assert fitz.open(str(matter / "assets" / "scan.pdf"))[0].get_text().strip() == ""


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_ensure_ocrs_an_image(matter: Path):
    docs = tc.ensure(matter, jobs=1)
    assert states(docs)["assets/photo.png"] == "searchable"
    side = (matter / "derived" / "text" / "assets" / "photo.png.txt").read_text()
    assert side.startswith(tc.HEADER_MARK)


def sc(*argv: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SC), *argv], cwd=cwd,
                          capture_output=True, text=True, timeout=300)


def test_sc_find_exits_2_while_anything_is_unsearchable(matter: Path, monkeypatch):
    proc = sc("find", "quick brown", "--matter-dir", str(matter), cwd=matter)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "UNSEARCHED:" in proc.stdout and "[needs-ocr] assets/scan.pdf" in proc.stdout
    assert "UNTRIAGED (inbox/" in proc.stdout


def test_find_cites_the_original_and_page_for_derived_text(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)
    tc.ensure(matter, jobs=1)
    proc = sc("find", "page 2 of 2", "--matter-dir", str(matter), cwd=matter)
    assert "- assets/letter.pdf  (text at derived/text/assets/letter.pdf.txt)" in proc.stdout
    assert "p.2 L" in proc.stdout


def test_sc_text_audit_and_brief_report_coverage(matter: Path):
    proc = sc("text", "audit", str(matter), cwd=matter)
    assert proc.returncode == 1
    assert proc.stdout.startswith("text coverage: 0/3 document(s) searchable")
    brief = sc("brief", str(matter), cwd=matter)
    assert "text coverage: 0/3" in brief.stdout


def test_symlinked_document_gets_its_own_derived_files(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)
    (matter / "processed_files").mkdir()
    make_text_pdf(matter / "processed_files" / "orig.pdf")
    os.symlink(matter / "processed_files" / "orig.pdf", matter / "assets" / "orig.pdf")
    docs = tc.ensure(matter, jobs=1)
    st = states(docs)
    assert st["assets/orig.pdf"] == "searchable" and st["processed_files/orig.pdf"] == "searchable"
    assert (matter / "derived" / "text" / "assets" / "orig.pdf.txt").exists()
    assert (matter / "derived" / "text" / "processed_files" / "orig.pdf.txt").exists()


def test_migrate_removes_a_redundant_tool_legacy_file(matter: Path, monkeypatch):
    monkeypatch.setattr(tc, "_tool", lambda name: None)
    tc.ensure(matter, jobs=1)                                     # derived text exists
    legacy = matter / "assets" / "letter.txt"
    tc.write_pdf_sidecar(matter, matter / "assets" / "letter.pdf", matter / "assets" / "letter.pdf", legacy)
    moves = tc.migrate(matter)
    assert any(m.startswith("rm assets/letter.txt (redundant") for m in moves), moves
    assert not legacy.exists()
    assert (matter / "derived" / "text" / "assets" / "letter.pdf.txt").exists()
