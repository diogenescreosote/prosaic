"""Scenario runner: fixture matters in fixed starting states.

A *scenario* is an entire (fictional) matter directory checked into
``tests/scenarios/<name>/matter/``. A test copies it to a temp
location (so runs never mutate the fixture), performs operations on it
through the system under test — engine calls, envelope builds,
eventually syncs and triage — and then makes many independent checks
against the results: deterministic asserts plus optional AI judgments
(see harness/ai.py).

Specs in ``specs/`` state what each component is *for*; scenarios are
those specs made executable against a realistic project.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PLEADING = REPO / "pleading"
SCENARIOS = REPO / "tests" / "scenarios"

PYTHON = sys.executable


def load_scenario(name: str, tmp_path: Path) -> Path:
    """Copy a scenario's fixture matter into tmp and return its path."""
    src = SCENARIOS / name / "matter"
    if not src.exists():
        raise FileNotFoundError(f"scenario fixture missing: {src}")
    dest = tmp_path / name
    shutil.copytree(src, dest)
    # Matters link the shared Makefile; recreate the link in the copy.
    mk = dest / "Makefile"
    if not mk.exists():
        mk.symlink_to(PLEADING / "Makefile")
    return dest


def build_envelope(matter: Path, envelope: str) -> subprocess.CompletedProcess:
    """Run the real envelope build against a scenario matter."""
    return subprocess.run(
        [PYTHON, str(PLEADING / "build_envelope.py"), envelope, "--force"],
        cwd=matter, capture_output=True, text=True,
    )


def rasterize(pdf: Path, out_prefix: Path, dpi: int = 80,
              first: int | None = None, last: int | None = None) -> list[Path]:
    """Render a PDF to PNGs (for AI visual judgment); returns page paths."""
    cmd = ["pdftoppm", "-png", "-r", str(dpi)]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    subprocess.run(cmd + [str(pdf), str(out_prefix)], check=True)
    return sorted(out_prefix.parent.glob(f"{out_prefix.name}-*.png"))


def pdf_text(pdf: Path, layout: bool = True) -> str:
    cmd = ["pdftotext"] + (["-layout"] if layout else []) + [str(pdf), "-"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def field_values(pdf: Path) -> dict[str, str]:
    """AcroForm field /V values by fully qualified name."""
    from pypdf import PdfReader
    fields = PdfReader(str(pdf)).get_fields() or {}
    return {k: str(v.get("/V") or "") for k, v in fields.items()}


def widget_values(pdf: Path) -> list[tuple[str, str]]:
    """(qualified_name, /V) for every widget, INCLUDING pages appended by
    merge (whose fields don't appear in the root AcroForm tree that
    ``get_fields`` reads)."""
    from pypdf import PdfReader
    import form_fill
    out = []
    for _page, name, obj in form_fill.iter_widgets(PdfReader(str(pdf))):
        v = obj.get("/V")
        if v is None and obj.get("/Parent") is not None:
            v = obj["/Parent"].get_object().get("/V")
        out.append((name, "" if v is None else str(v)))
    return out
