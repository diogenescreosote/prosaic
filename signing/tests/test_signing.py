"""Local signing and attestation (ADR-0036).

The load-bearing test here is `test_slots_found_in_real_build`: slot
discovery reads the *printed text* of a signature block, so it is coupled
to the exact sentences `pleading/md_pleading.py` emits. Asserting against
a hand-made fixture would pass forever while the renderer drifted out
from under it, so these tests build a real pleading and read the real
output.

The gpg leg is exercised with `_clearsign` stubbed. Generating a
throwaway key needs a running gpg-agent, which is unavailable in
sandboxed CI, and a test that silently skips there would be worse than
one that is honest about what it covers: everything except the signature
over the statement.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

SIGNING_DIR = Path(__file__).resolve().parent.parent
ROOT = SIGNING_DIR.parent
sys.path.insert(0, str(ROOT))

fitz = pytest.importorskip("fitz")
PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from signing import SignRequest, SignerError, get_signer  # noqa: E402
from signing import audit, marks, slots as slots_mod, stamp, store  # noqa: E402
from signing.base import SlotRole  # noqa: E402

PLEADING = ROOT / "pleading" / "md_pleading.py"

FRONT = """---
doctype: document
heading_numbers: false
paper_title: "Signing Test"
---

# Article I. Body

Text precedes the signature.

{body}
"""


def build_pleading(tmp_path: Path, body: str) -> Path:
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body=body))
    out = tmp_path / "doc.pdf"
    proc = subprocess.run(
        [sys.executable, str(PLEADING), str(src), str(out)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    return out


def specimen(tmp_path: Path, w: int = 600, h: int = 200) -> Path:
    """A synthetic mark. Deliberately not an imitation of a signature."""
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.line([(40, h - 40), (w - 40, 40)], fill=(15, 15, 15), width=8)
    p = tmp_path / "specimen.png"
    img.save(p)
    return p


# --- slot discovery ---------------------------------------------------------


def test_slots_found_in_real_build(tmp_path):
    pdf = build_pleading(
        tmp_path,
        "\\signblock{decl}{ANDREW CONE}{Reno, Nevada}{Respondent, In Pro Per}",
    )
    found = slots_mod.discover(pdf)
    roles = [s.role for s in found]
    assert SlotRole.SIGNATURE_MARK in roles
    assert SlotRole.DAY_ORDINAL in roles
    assert SlotRole.MONTH_NAME in roles
    # Ordinal before month, matching "this ___ day of ___".
    assert roles.index(SlotRole.DAY_ORDINAL) < roles.index(SlotRole.MONTH_NAME)


def test_dated_style_takes_a_whole_date(tmp_path):
    pdf = build_pleading(
        tmp_path, "\\signblock{dated}{ANDREW CONE}{Respondent}"
    )
    roles = [s.role for s in slots_mod.discover(pdf)]
    assert SlotRole.DATE_FULL in roles
    # A whole-date blank must not be mistaken for a day/month pair.
    assert SlotRole.DAY_ORDINAL not in roles


def test_no_signature_block_means_no_slots(tmp_path):
    pdf = build_pleading(tmp_path, "Just prose, no signature block.")
    assert slots_mod.discover(pdf) == []


# --- the mark ---------------------------------------------------------------


def test_prepare_derives_alpha_and_keeps_aspect(tmp_path):
    m = marks.prepare(specimen(tmp_path, 600, 200))
    img = Image.open(io.BytesIO(m.png))
    assert img.mode == "RGBA"
    lo, hi = img.getchannel("A").getextrema()
    # Real transparency, and real ink: neither fully opaque nor blank.
    assert lo == 0 and hi == 255
    # Cropped to ink, so aspect follows the stroke, not the paper margin.
    assert m.aspect > 1.0


def test_prepare_rejects_a_blank_page(tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (400, 200), "white").save(blank)
    with pytest.raises(SignerError, match="blank"):
        marks.prepare(blank)


def test_prepare_reads_a_vector_pdf_source(tmp_path):
    """PDF is a first-class source, and the preferred one when vector.

    A tablet-captured or traced signature has no paper behind it, so
    rendering with alpha yields real transparency with nothing to key out.
    """
    pdf = tmp_path / "sig.pdf"
    doc = fitz.open()
    page = doc.new_page(width=140, height=40)
    page.draw_bezier(fitz.Point(10, 30), fitz.Point(40, 2),
                     fitz.Point(90, 38), fitz.Point(130, 10),
                     color=(0, 0, 0), width=2.5)
    doc.save(str(pdf))
    doc.close()

    m = marks.prepare(pdf, pdf_dpi=600)
    img = Image.open(io.BytesIO(m.png))
    assert img.mode == "RGBA"
    assert img.getchannel("A").getextrema() == (0, 255)
    assert m.aspect > 1.0


def test_prepare_keeps_the_colour_of_a_source_that_has_alpha(tmp_path):
    """A prepared source's ink colour is part of the signature."""
    src = tmp_path / "red.png"
    img = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(10, 50), (190, 10)], fill=(200, 0, 0, 255), width=6)
    img.save(src)

    m = marks.prepare(src, ink=(16, 24, 92))
    out = Image.open(io.BytesIO(m.png))
    opaque = [out.getpixel((x, y))[:3]
              for x in range(out.width) for y in range(out.height)
              if out.getpixel((x, y))[3] > 200]
    assert opaque, "no opaque ink found"
    assert all(px[0] > px[2] for px in opaque), "red was not preserved"


def test_prepare_recolours_only_a_scan(tmp_path):
    """`ink` applies when alpha had to be derived from luminance."""
    m = marks.prepare(specimen(tmp_path), ink=(0, 0, 200))
    out = Image.open(io.BytesIO(m.png))
    opaque = [out.getpixel((x, y))[:3]
              for x in range(0, out.width, 3) for y in range(0, out.height, 3)
              if out.getpixel((x, y))[3] > 240]
    assert opaque
    assert all(px[2] > px[0] for px in opaque), "ink colour was not applied"


def test_place_rect_never_distorts(tmp_path):
    m = marks.prepare(specimen(tmp_path, 900, 150))
    # A wide, short rule -- the Judicial Council shape that tempts squashing.
    rule = (100.0, 400.0, 320.0, 401.0)
    x0, y0, x1, y1 = marks.place_rect(m, rule)
    drawn = (x1 - x0) / (y1 - y0)
    assert abs(drawn - m.aspect) < 0.01, "aspect ratio must be preserved"


def test_place_rect_sits_on_the_line(tmp_path):
    m = marks.prepare(specimen(tmp_path))
    rule = (100.0, 400.0, 400.0, 402.0)
    _x0, y0, _x1, y1 = marks.place_rect(m, rule)
    assert y1 > rule[3], "mark should cross the rule like a pen would"
    assert y0 < rule[1], "mark should rise above the rule"


# --- the stamp -------------------------------------------------------------


def test_nonce_looks_like_a_dms_reference():
    n = stamp.new_nonce()
    assert re.fullmatch(r"\d{4}-\d{4}-\d{4}v\d+", n), n
    # No letters: a mixed token reads as encoded data (see stamp.py).
    assert not re.search(r"[A-Za-z]", n.split("v")[0])


def test_nonces_do_not_repeat():
    assert len({stamp.new_nonce() for _ in range(200)}) == 200


def test_stamp_lands_on_a_blank_page():
    doc = fitz.open()
    doc.new_page()
    nonce = stamp.new_nonce()
    assert stamp.apply(doc, nonce) == []
    assert nonce in doc[0].get_text()


def test_stamp_skips_a_page_with_no_clear_margin():
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(0, 0, 0))
    assert stamp.apply(doc, stamp.new_nonce()) == [0]


# --- the signature store ---------------------------------------------------


def test_store_refuses_a_signature_inside_a_repo_with_a_remote(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/x.git"],
        cwd=repo, check=True,
    )
    Image.new("RGB", (200, 80), "white").save(repo / "andrew_cone.png")
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(repo))
    with pytest.raises(SignerError, match="published signature"):
        store.resolve("andrew_cone")


def test_store_rejects_a_path_as_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    with pytest.raises(SignerError, match="bare name"):
        store.resolve("../../etc/passwd")


def test_store_prefers_a_vector_source(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    (tmp_path / "andrew_cone.pdf").write_bytes(b"%PDF-1.4\n")
    Image.new("RGB", (10, 10), "white").save(tmp_path / "andrew_cone.png")
    assert store.resolve("andrew_cone").suffix == ".pdf"


def test_sidecar_binds_a_mark_to_a_name_and_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    (tmp_path / "andrew_cone.meta.yaml").write_text(
        "name: Andrew Cone\ngpg_key: F15991EE7300FD42DBD2F3D0466DD18A60791844\n"
    )
    meta = store.metadata("andrew_cone")
    assert meta["name"] == "Andrew Cone"
    assert meta["gpg_key"].startswith("F15991EE")


@pytest.mark.parametrize("body", ["", "just a string", "- a\n- list\n", "{{{"])
def test_a_missing_or_malformed_sidecar_is_simply_absent(tmp_path, monkeypatch, body):
    """Degrades to "supply --name and --gpg-key", never to a crash.

    A wrong sidecar is the dangerous case and no parsing strictness
    catches that, so strictness here would buy nothing and cost a
    usable failure mode.
    """
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    if body:
        (tmp_path / "x.meta.yaml").write_text(body)
    assert store.metadata("x") == {}


# --- signing end to end (gpg stubbed) --------------------------------------


@pytest.fixture
def stub_gpg(monkeypatch):
    def fake(statement: Path, gpg_key):
        out = statement.with_name(statement.name + ".asc")
        out.write_text("-----BEGIN PGP SIGNED MESSAGE-----\nstub\n")
        return out

    monkeypatch.setattr(audit, "_clearsign", fake)


def test_apply_signs_stamps_and_attests(tmp_path, monkeypatch, stub_gpg):
    pdf = build_pleading(
        tmp_path,
        "\\signblock{decl}{ANDREW CONE}{Reno, Nevada}{Respondent, In Pro Per}",
    )
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    specimen(tmp_path).rename(tmp_path / "andrew_cone.png")

    out = tmp_path / "signed" / "doc_SIGNED.pdf"
    result = get_signer("local").request(
        SignRequest(
            pdf=pdf,
            signer_key="andrew_cone",
            signer_name="Andrew Cone",
            date=dt.date(2026, 8, 25),
            audit_root=tmp_path / "audit_log",
            output=out,
            timestamp=False,
        )
    )

    assert out.is_file()
    assert result.reference in fitz.open(out)[-1].get_text()
    text = fitz.open(out)[-1].get_text()
    assert "25th" in text and "August" in text

    directory = result.attestation_dir
    assert directory is not None
    assert (directory / "attestation.json").is_file()
    assert (directory / out.name).is_file(), "attested bytes must be retained"
    statement = (directory / "statement.txt").read_text()
    assert "intend to be bound" in statement
    assert result.reference in statement

    # The digests check out. The signature is reported as UNCHECKED rather
    # than clean, because no pinned key was supplied --- verify() must not
    # say VERIFIED about something it did not verify.
    problems = audit.verify(directory)
    assert not any("SHA" in p for p in problems), problems
    assert any("not checked" in p for p in problems), problems


def test_verify_notices_altered_bytes(tmp_path, monkeypatch, stub_gpg):
    pdf = build_pleading(
        tmp_path, "\\signblock{dated}{ANDREW CONE}{Respondent}"
    )
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    specimen(tmp_path).rename(tmp_path / "andrew_cone.png")
    result = get_signer("local").request(
        SignRequest(
            pdf=pdf, signer_key="andrew_cone", signer_name="Andrew Cone",
            audit_root=tmp_path / "audit_log",
            output=tmp_path / "signed.pdf", timestamp=False,
        )
    )
    retained = result.attestation_dir / "signed.pdf"
    retained.write_bytes(retained.read_bytes() + b"\n% tampered\n")
    problems = audit.verify(result.attestation_dir)
    assert any("SHA-256" in p for p in problems)
    assert any("SHA3-512" in p for p in problems)


def test_refuses_to_write_into_a_build_directory(tmp_path, monkeypatch, stub_gpg):
    pdf = build_pleading(
        tmp_path, "\\signblock{dated}{ANDREW CONE}{Respondent}"
    )
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    specimen(tmp_path).rename(tmp_path / "andrew_cone.png")
    with pytest.raises(SignerError, match="build directory"):
        get_signer("local").request(
            SignRequest(
                pdf=pdf, signer_key="andrew_cone", signer_name="Andrew Cone",
                audit_root=tmp_path / "audit_log",
                output=tmp_path / "out" / "signed.pdf", timestamp=False,
            )
        )


def test_refuses_to_sign_in_place(tmp_path, monkeypatch, stub_gpg):
    pdf = build_pleading(
        tmp_path, "\\signblock{dated}{ANDREW CONE}{Respondent}"
    )
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    specimen(tmp_path).rename(tmp_path / "andrew_cone.png")
    with pytest.raises(SignerError, match="in place"):
        get_signer("local").request(
            SignRequest(
                pdf=pdf, signer_key="andrew_cone", signer_name="Andrew Cone",
                audit_root=tmp_path / "audit_log", output=pdf, timestamp=False,
            )
        )


def test_unsigned_document_offers_nothing_to_sign(tmp_path, monkeypatch, stub_gpg):
    pdf = build_pleading(tmp_path, "Prose with no signature block.")
    monkeypatch.setenv("PROSAIC_SIGNATURE_DIR", str(tmp_path))
    specimen(tmp_path).rename(tmp_path / "andrew_cone.png")
    with pytest.raises(SignerError, match="no signature line"):
        get_signer("local").request(
            SignRequest(
                pdf=pdf, signer_key="andrew_cone", signer_name="Andrew Cone",
                audit_root=tmp_path / "audit_log",
                output=tmp_path / "s.pdf", timestamp=False,
            )
        )


# --- the interface ---------------------------------------------------------


def test_backends_declare_whether_they_attest_locally():
    assert get_signer("local").produces_local_attestation is True
    assert get_signer("docuseal").produces_local_attestation is False


def test_synchronous_backend_has_nothing_to_poll():
    with pytest.raises(SignerError, match="nothing to poll"):
        get_signer("local").poll("4823-9012-3391v1")


def test_unknown_backend_names_the_ones_that_exist():
    with pytest.raises(SignerError, match="local, docuseal"):
        get_signer("carrier-pigeon")
