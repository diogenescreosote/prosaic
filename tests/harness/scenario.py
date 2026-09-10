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


def page_text(pdf: Path, page_no: int) -> str:
    """pdftotext of one 1-based page, reading order."""
    return subprocess.run(
        ["pdftotext", "-f", str(page_no), "-l", str(page_no), str(pdf), "-"],
        capture_output=True, text=True).stdout


def _probe():
    """pleading/tests/probe.py: page-level inspection of a flattened
    form (ADR-0046: there are no field values to read; the page is the
    record)."""
    for p in (PLEADING, PLEADING / "tests"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import probe
    return probe


def form_field_text(pdf: Path, form_id: str, logical: str) -> str:
    """Text drawn inside the box a logical field of ``form_id`` occupies."""
    return _probe().field_text(pdf, form_id, logical)


def form_widget_text(pdf: Path, form_id: str, name_suffix: str) -> list[str]:
    """Text drawn inside every blank widget whose name ends with the
    suffix — for proving a human-owned region received nothing."""
    return _probe().widget_text(pdf, form_id, name_suffix)


def has_no_form_layer(pdf: Path) -> bool:
    return _probe().has_no_form_layer(pdf)
