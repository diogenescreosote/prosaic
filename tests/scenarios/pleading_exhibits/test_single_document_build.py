"""Single-document builds and mode-aware freshness (ADR-0039).

The build manifest records the render options that change the artifact —
final/draft, variant, signer, date — so a draft PDF is never "up to date"
for a --final request, and `sc build-doc` rebuilds exactly one
envelope-owned source without touching its envelope-mates.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.scenarios.pleading_exhibits import util

REPO = util.REPO
SC = REPO / "cli" / "sc"
PY = sys.executable


def run_sc(matter: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(SC), *args], cwd=matter,
                          capture_output=True, text=True)


def manifest(matter: Path, envelope: str, variant: str = "sealed") -> dict:
    return json.loads(
        (matter / "out" / envelope / variant / ".build_manifest.json")
        .read_text())


def _add_clean_envelope(m: Path, name: str = "clean_packet",
                        source: str = "Clean Memo.md") -> None:
    (m / "src" / source).write_text(
        "---\ndoctype: document\npaper_title: CLEAN MEMO\n---\n\n"
        "The motion is granted for the reasons stated.\n")
    cfg = (m / "envelopes.yaml").read_text()
    (m / "envelopes.yaml").write_text(
        cfg + f"\n  {name}:\n    sources:\n      - file: {source}\n")


def test_envelope_build_writes_mode_aware_manifest(tmp_path):
    m = util.load_matter(tmp_path)
    _add_clean_envelope(m)
    proc = util.run_build(m, "clean_packet")
    assert proc.returncode == 0, proc.stderr[-2000:]
    data = json.loads(
        (m / "out" / "clean_packet" / ".build_manifest.json").read_text())
    entry = data["documents"]["Clean Memo.md"]
    assert entry["options"] == {
        "final": False, "variant": None, "sign": None, "date": None,
    }
    assert any(d["path"].endswith("md_pleading.py") for d in entry["deps"])


def test_mode_change_rebuilds_despite_fresh_mtimes(tmp_path):
    """The ADR-0039 regression: draft build, then --final with untouched
    sources. Timestamp-only freshness calls this 'up to date' and ships a
    bannered PDF."""
    m = util.load_matter(tmp_path)
    _add_clean_envelope(m)
    pdf = m / "out" / "clean_packet" / "Clean Memo.pdf"

    proc = util.run_build(m, "clean_packet")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "DRAFT" in util.pdf_text(pdf)

    final = util.run_build(m, "clean_packet", "--final")
    assert final.returncode == 0, final.stderr[-2000:]
    assert "render options changed (final)" in final.stdout
    assert "DRAFT" not in util.pdf_text(pdf)

    # Same options again: genuinely current, nothing rebuilt.
    again = util.run_build(m, "clean_packet", "--final")
    assert again.returncode == 0
    assert "is up to date" in again.stdout
    assert "rebuilding" not in again.stdout

    # And back to draft is also a mode change, not a no-op.
    draft = util.run_build(m, "clean_packet")
    assert draft.returncode == 0
    assert "render options changed (final)" in draft.stdout
    assert "DRAFT" in util.pdf_text(pdf)


def test_build_doc_builds_only_the_named_source(tmp_path):
    m = util.load_matter(tmp_path)
    proc = run_sc(m, "build-doc", "src/Memo of Points.md", "--variant",
                  "sealed")
    assert proc.returncode == 0, proc.stderr[-2000:]
    d = m / "out" / "motion_packet" / "sealed"
    assert (d / util.MEMO_PDF).exists()
    assert not (d / util.DECL_PDF).exists(), "envelope-mate was built"
    assert "MEMORANDUM OF POINTS AND AUTHORITIES" in util.pdf_text(d / util.MEMO_PDF)


def test_build_doc_builds_configured_docx_companion(tmp_path):
    m = util.load_matter(tmp_path)
    (m / "src" / "Solo Order.md").write_text(
        "---\ndoctype: document\npaper_title: SOLO ORDER\n---\n\n"
        "IT IS ORDERED that the motion is granted.\n")
    cfg = (m / "envelopes.yaml").read_text()
    (m / "envelopes.yaml").write_text(
        cfg + "\n  solo_packet:\n    sources:\n"
              "      - file: Solo Order.md\n        docx: true\n")
    proc = run_sc(m, "build-doc", "src/Solo Order.md", "--final")
    assert proc.returncode == 0, proc.stderr[-2000:]
    d = m / "out" / "solo_packet"
    assert (d / "Solo Order.pdf").exists()
    assert (d / "Solo Order.docx").exists()
    assert "DRAFT" not in util.pdf_text(d / "Solo Order.pdf")


def test_build_doc_accepts_src_relative_and_plain_paths(tmp_path):
    m = util.load_matter(tmp_path)
    proc = run_sc(m, "build-doc", "Memo of Points.md", "--variant", "sealed")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert (m / "out" / "motion_packet" / "sealed" / util.MEMO_PDF).exists()


def test_build_doc_refuses_unknown_or_unowned_source(tmp_path):
    m = util.load_matter(tmp_path)
    missing = run_sc(m, "build-doc", "src/nonesuch.md")
    assert missing.returncode != 0
    assert "no such source" in missing.stderr

    (m / "src" / "orphan.md").write_text("---\ndoctype: document\n---\n\nBody.\n")
    orphan = run_sc(m, "build-doc", "src/orphan.md")
    assert orphan.returncode != 0
    assert "not a source in any envelope" in orphan.stderr


def test_build_doc_refuses_multi_envelope_source(tmp_path):
    """'Proposed Order.md' sits in both motion_packet and sent_packet; its
    output location would be a guess, so build-doc refuses."""
    m = util.load_matter(tmp_path)
    proc = run_sc(m, "build-doc", "src/Proposed Order.md")
    assert proc.returncode != 0
    assert "multiple envelopes" in proc.stderr


def test_build_doc_respects_notreal_and_sent_guards(tmp_path):
    m = util.load_matter(tmp_path)
    (m / "src" / "marked.md").write_text(
        "---\ndoctype: document\nnotreal: draft---not executed\n---\n\nBody.\n")
    cfg = (m / "envelopes.yaml").read_text()
    (m / "envelopes.yaml").write_text(
        cfg + '\n  marked_packet:\n    sources:\n      - file: marked.md\n')
    final = run_sc(m, "build-doc", "src/marked.md", "--final")
    assert final.returncode != 0
    assert "notreal" in final.stderr

    (m / "src" / "mailed.md").write_text(
        "---\ndoctype: document\npaper_title: MAILED NOTE\n---\n\nBody.\n")
    (m / "envelopes.yaml").write_text(
        cfg + "\n  mailed_packet:\n    sent_on: 2026-01-15\n    sources:\n"
              "      - file: mailed.md\n")
    sent = run_sc(m, "build-doc", "src/mailed.md")
    assert sent.returncode != 0
    assert "marked sent" in sent.stderr
    forced = run_sc(m, "build-doc", "src/mailed.md", "--force")
    assert forced.returncode == 0, forced.stderr[-2000:]

def test_sc_build_all_and_check_stale_replace_the_make_targets(tmp_path):
    """ADR-0039 removed the Makefile; what `make all` and `make check-stale`
    did must survive as `sc build --all` and `sc build --check-stale`."""
    m = util.load_matter(tmp_path)
    neither = run_sc(m, "build")
    assert neither.returncode != 0
    assert "exactly one envelope, or pass --all" in neither.stderr

    built = run_sc(m, "build", "--all", "--variant", "sealed")
    assert built.returncode == 0, built.stderr[-2000:]
    assert (m / "out" / "motion_packet" / "sealed" / util.MEMO_PDF).exists()
    assert "sent_packet" in built.stdout and "skipping" in built.stdout.lower()

    fresh = run_sc(m, "build", "--all", "--variant", "sealed", "--check-stale")
    assert fresh.returncode == 0, fresh.stdout + fresh.stderr
    assert "rebuilding" not in fresh.stdout

    (m / "src" / "Memo of Points.md").write_text(
        (m / "src" / "Memo of Points.md").read_text() + "\nAdded line.\n")
    stale = run_sc(m, "build", "motion_packet", "--variant", "sealed",
                   "--check-stale")
    assert stale.returncode != 0
    assert "STALE" in stale.stderr
