"""The estate pack's protections, pinned (ADR-0025).

Legal templates rot differently from code: a later edit can soften
the witness attestation, reintroduce "irrefutable," or let the QR
drift from the printed key, and every one of those reads fine. So
the tests pin the protections rather than the prose: every template
builds and carries the TEMPLATE banner, the will's execution
language survives, the forbidden words stay out, and the QR on the
page decodes to exactly the shipped anchor key.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK = REPO_ROOT / "templates" / "estate"
RENDERER = REPO_ROOT / "pleading" / "md_pleading.py"

TEMPLATES = sorted(
    p.name
    for p in PACK.glob("*.md")
    if p.name not in ("README.md", "KEY-PROTOCOL.md", "EXECUTION.md")
)

pytestmark = pytest.mark.skipif(shutil.which("qrencode") is None, reason="qrencode not installed")


def build(name: str, tmp_path: Path) -> Path:
    out = tmp_path / f"{Path(name).stem}.pdf"
    proc = subprocess.run(
        [sys.executable, str(RENDERER), str(PACK / name), str(out)],
        capture_output=True,
        text=True,
        cwd=PACK,
    )
    assert proc.returncode == 0, f"{name}: {proc.stderr}"
    return out


def pdf_text(pdf: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_the_pack_ships_the_expected_instruments() -> None:
    assert TEMPLATES == [
        "advance-health-care-directive.md",
        "certification-of-trust.md",
        "durable-power-of-attorney.md",
        "living-trust.md",
        "will.md",
    ]


@pytest.mark.parametrize("name", TEMPLATES)
def test_every_template_builds_with_the_template_banner(name: str, tmp_path: Path) -> None:
    pdf = build(name, tmp_path)
    pages = [p for p in pdf_text(pdf).split("\f") if p.strip()]
    for i, page in enumerate(pages):
        assert "TEMPLATE—NOT EXECUTED" in page, f"{name}: banner missing from page {i + 1}"


def test_no_template_claims_conclusive_or_irrefutable_proof() -> None:
    """The protocol's core correction: a signature earns a rebuttable
    presumption; a stolen key must not inherit an 'irrefutable' clause."""
    for name in TEMPLATES:
        text = (PACK / name).read_text().lower()
        for word in ("irrefutable", "conclusive", "indefeasib"):
            assert word not in text, f"{name} contains {word!r}"


def test_the_instruments_state_a_rebuttable_presumption() -> None:
    for name in ("will.md", "living-trust.md"):
        text = " ".join((PACK / name).read_text().split())
        assert "rebutted only by clear and convincing evidence" in text, name


def test_the_will_excludes_electronic_testamentary_effect() -> None:
    will = (PACK / "will.md").read_text()
    assert "Nothing in this Article makes any electronic record a will" in will
    trust = (PACK / "living-trust.md").read_text()
    assert (
        "Nothing in this Article gives testamentary\n   effect" in trust
        or "gives testamentary" in trust
    )


def test_the_wills_witnesses_are_present_at_the_same_time() -> None:
    """Prob. Code § 6110(c)(1): both witnesses, same time. The single
    easiest thing for a later edit to water down."""
    will = (PACK / "will.md").read_text()
    assert "present at\nthe same time" in will or "present at the same time" in will.replace(
        "\n", " "
    )


@pytest.mark.skipif(
    not (shutil.which("zbarimg") and shutil.which("pdftoppm")),
    reason="zbarimg/pdftoppm not installed",
)
def test_the_printed_qr_is_exactly_the_shipped_anchor_key(tmp_path: Path) -> None:
    pdf = build("will.md", tmp_path)
    subprocess.run(
        ["pdftoppm", "-png", "-r", "200", str(pdf), str(tmp_path / "page")],
        check=True,
        capture_output=True,
    )
    decoded = ""
    for page in sorted(tmp_path.glob("page*.png")):
        proc = subprocess.run(
            ["zbarimg", "--raw", "--quiet", str(page)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            decoded = proc.stdout.strip()
            break
    expected = (PACK / "assets" / "anchor-key.asc").read_text().strip()
    assert decoded == expected, "the page's QR must be the shipped key, byte-exact"


def test_guardianship_avoids_the_forbidden_phrase() -> None:
    """The leak guard bans family-law vocabulary repo-wide; the pack
    phrases guardianship around it, and this pins the phrasing so a
    template edit fails here with a useful message instead of in the
    leak guard with a confusing one."""
    will = (PACK / "will.md").read_text()
    assert "under eighteen" in will
