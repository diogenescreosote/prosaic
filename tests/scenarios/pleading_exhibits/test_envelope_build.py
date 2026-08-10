"""build_envelope.py behaviors (spec: specs/pleading/generator.md §7-10).

Same fixture matter as test_exhibits_and_variants; here the subject is
the build driver itself: --list, sent-envelope protection, dependency-
aware incremental rebuilds, --check-stale, docx: true plumbing,
envelope copies, redacted_pdf sources, and the legacy no-variant path.

Tests in the "incremental / staleness" section mutate mtimes and then
restore the built state; they rely on in-file ordering only within
that section.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from tests.scenarios.pleading_exhibits import util


@pytest.fixture(scope="module")
def matter(tmp_path_factory):
    m = util.load_matter(tmp_path_factory.mktemp("env"))
    proc = util.run_build(m, "motion_packet", "--variant", "sealed")
    assert proc.returncode == 0, proc.stderr[-2000:]
    return m


OUT = lambda m, *parts: m.joinpath("out", *parts)  # noqa: E731


# ---------------------------------------------------------------------------
# Listing and layout
# ---------------------------------------------------------------------------

def test_list_shows_envelopes_sources_and_status(matter):
    proc = util.run_build(matter, "--list")
    assert proc.returncode == 0
    out = proc.stdout
    assert "motion_packet: [draft]" in out
    assert "Proposed Order.md [+docx]" in out
    assert "sent_packet: [sent 2026-01-15]" in out
    assert "copy assets/static_notice.pdf -> notice_copy.pdf" in out
    assert ("redacted_pdf redactions/intake_redactions.json -> "
            "intake_public.pdf") in out


def test_variant_scoped_output_layout(matter):
    d = OUT(matter, "motion_packet", "sealed")
    for name in (util.DECL_PDF, util.ORDER_PDF, util.ORDER_DOCX,
                 util.MEMO_PDF, "notice_copy.pdf"):
        assert (d / name).exists(), f"missing {name} in {d}"


def test_docx_source_emits_editable_word_copy(matter):
    import re
    docx = OUT(matter, "motion_packet", "sealed", util.ORDER_DOCX)
    with zipfile.ZipFile(docx) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    # Word splits text across runs, and the caption table interleaves
    # its ")" divider column into wrapped title lines; strip tags and
    # assert on a fragment that fits one caption line.
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))
    assert "IT IS ORDERED" in flat
    assert "[PROPOSED] ORDER ON MOTION" in flat
    assert "24CV00000" in flat


def test_copies_entry_lands_byte_identical(matter):
    src = matter / "assets" / "static_notice.pdf"
    dest = OUT(matter, "motion_packet", "sealed", "notice_copy.pdf")
    assert dest.read_bytes() == src.read_bytes()


def test_unknown_envelope_errors_and_lists_available(matter):
    proc = util.run_build(matter, "nonesuch", "--variant", "sealed")
    assert proc.returncode != 0
    assert "unknown envelope" in proc.stderr
    assert "motion_packet" in proc.stderr  # tells the user what exists


# ---------------------------------------------------------------------------
# Sent-envelope protection
# ---------------------------------------------------------------------------

def test_sent_envelope_refuses_rebuild_without_force(matter):
    proc = util.run_build(matter, "sent_packet", "--variant", "sealed")
    assert proc.returncode != 0
    assert "marked sent on 2026-01-15" in proc.stderr
    assert "--force" in proc.stderr
    assert not OUT(matter, "sent_packet").exists()


def test_all_skips_sent_envelopes(matter):
    proc = util.run_build(matter, "--all", "--variant", "sealed")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "Skipping sent envelopes" in proc.stdout
    assert "sent_packet (2026-01-15)" in proc.stdout
    assert not OUT(matter, "sent_packet").exists()


def test_sent_envelope_rebuilds_with_force(matter):
    proc = util.run_build(matter, "sent_packet", "--variant", "sealed", "--force")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert OUT(matter, "sent_packet", "sealed", util.ORDER_PDF).exists()


# ---------------------------------------------------------------------------
# redacted_pdf envelope sources
# ---------------------------------------------------------------------------

def test_redacted_pdf_source_builds_and_scrubs(matter):
    """{type: redacted_pdf} sources run redact_pdf.py and copy the
    artifact into the envelope output; the redacted phrase must be gone
    from text, bytes, and streams."""
    proc = util.run_build(matter, "redacted_packet", "--variant", "public")
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = OUT(matter, "redacted_packet", "public", "intake_public.pdf")
    assert out.exists()
    assert not util.contains_text(out, util.INTAKE_UNREDACTED)
    assert "[REDACTED]" in util.pdf_text(out)
    # Second run: cached artifact is reused, not rebuilt.
    proc2 = util.run_build(matter, "redacted_packet", "--variant", "public")
    assert proc2.returncode == 0
    assert "cached artifact up to date" in proc2.stdout


def test_check_stale_covers_redacted_pdf_outputs(matter):
    """--check-stale inspects redacted_pdf entries too: current after a
    build, stale once the underlying source PDF is newer than the
    cached artifact."""
    import os
    import time
    proc = util.run_build(matter, "redacted_packet", "--variant", "public",
                          "--check-stale")
    assert proc.returncode == 0, proc.stderr[-2000:]
    src_pdf = matter / "exhibits" / "intake_form.pdf"
    stat = src_pdf.stat()
    future = time.time() + 5
    os.utime(src_pdf, (future, future))
    try:
        proc = util.run_build(matter, "redacted_packet", "--variant",
                              "public", "--check-stale")
        assert proc.returncode != 0
        assert "STALE" in proc.stderr
    finally:
        # Restore the original mtime: intake_form.pdf is also an motion_packet
        # exhibit, and the module-scoped fixture is shared with the ordered
        # staleness tests below.
        os.utime(src_pdf, (stat.st_atime, stat.st_mtime))
    proc = util.run_build(matter, "redacted_packet", "--variant", "public",
                          "--check-stale")
    assert proc.returncode == 0, proc.stderr[-2000:]


# ---------------------------------------------------------------------------
# Legacy unscoped (no --variant) path
# ---------------------------------------------------------------------------

def test_no_variant_build_warns_and_defaults_to_public(matter):
    """The unscoped path fails toward substitution: a redaction-bearing
    source built without --variant renders its PUBLIC variant (loudly),
    so the least-careful invocation never produces sealed content."""
    proc = util.run_build(matter, "motion_packet")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "WARNING: no --variant" in proc.stderr
    assert "PUBLIC" in proc.stderr
    decl = OUT(matter, "motion_packet", util.DECL_PDF)
    assert decl.exists()
    assert not util.contains_text(decl, util.SEALED_PHRASE_TOKEN), (
        "unscoped no-variant build rendered SEALED content")
    assert util.PUBLIC_PHRASE in util.stripped_text(decl)
    # And no sealed-text sidecar lands in the unscoped output dir either.
    assert not (decl.parent / (decl.name + ".redactions.json")).exists()


# ---------------------------------------------------------------------------
# Incremental rebuilds and --check-stale (ordered mutations)
# ---------------------------------------------------------------------------

def test_second_build_skips_up_to_date_sources(matter):
    before = OUT(matter, "motion_packet", "sealed", util.DECL_PDF).stat().st_mtime
    proc = util.run_build(matter, "motion_packet", "--variant", "sealed")
    assert proc.returncode == 0
    assert proc.stdout.count("is up to date") >= 3, proc.stdout
    after = OUT(matter, "motion_packet", "sealed", util.DECL_PDF).stat().st_mtime
    assert after == before, "up-to-date output was rewritten"


def test_check_stale_passes_when_current(matter):
    proc = util.run_build(matter, "motion_packet", "--variant", "sealed",
                          "--check-stale")
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_touched_exhibit_triggers_rebuild(matter):
    """The dependency set includes the exhibits selected for the variant."""
    os.utime(matter / "exhibits" / "smith_email.pdf")
    proc = util.run_build(matter, "motion_packet", "--variant", "sealed",
                          "--check-stale")
    assert proc.returncode != 0
    assert "STALE" in proc.stderr and "smith_email.pdf" in proc.stderr
    rebuild = util.run_build(matter, "motion_packet", "--variant", "sealed")
    assert rebuild.returncode == 0
    assert "rebuilding Declaration of Jane Roe.md" in rebuild.stdout


def test_touched_source_staleness_propagates_via_exhibit_source(matter):
    """Touching the declaration also staled the memo, whose \\exhibit{}
    letters come from the declaration via exhibit_source."""
    os.utime(matter / "src" / util.DECL_MD)
    proc = util.run_build(matter, "motion_packet", "--variant", "sealed",
                          "--check-stale")
    assert proc.returncode != 0
    assert util.MEMO_PDF in proc.stderr, (
        "memo not flagged stale after its exhibit_source changed:\n"
        + proc.stderr[-1500:])
    # Restore: rebuild so later runs see a current matter.
    rebuild = util.run_build(matter, "motion_packet", "--variant", "sealed")
    assert rebuild.returncode == 0
    final = util.run_build(matter, "motion_packet", "--variant", "sealed",
                           "--check-stale")
    assert final.returncode == 0


def test_public_staleness_tracks_redacted_companion(tmp_path):
    """In the public variant the dependency is the _redacted companion,
    not the canonical exhibit."""
    m = util.load_matter(tmp_path)
    proc = util.run_build(m, "motion_packet", "--variant", "public")
    assert proc.returncode == 0, proc.stderr[-2000:]
    os.utime(m / "exhibits" / "intake_form_redacted.pdf")
    stale = util.run_build(m, "motion_packet", "--variant", "public",
                           "--check-stale")
    assert stale.returncode != 0
    assert "intake_form_redacted.pdf" in stale.stderr
    # The canonical (sealed-side) file does not stale the public build.
    rebuilt = util.run_build(m, "motion_packet", "--variant", "public")
    assert rebuilt.returncode == 0
    os.utime(m / "exhibits" / "intake_form.pdf")
    check = util.run_build(m, "motion_packet", "--variant", "public",
                           "--check-stale")
    assert check.returncode == 0, (
        "public build wrongly depends on the unredacted exhibit:\n"
        + check.stderr[-1500:])
