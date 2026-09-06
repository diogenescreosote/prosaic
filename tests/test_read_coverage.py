"""triage/read_coverage.py: every page of a PDF is classified, and a page the
text layer cannot speak for is reported rather than silently skipped.

The failure this guards against is a catalog row written after a partial
read. The tool's promise is mechanical: the table names every page that
needs OCR or eyes, the exit status says whether any did, and the ``--text``
dump emits every page with a marker so the reader can prove coverage.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "triage" / "read_coverage.py"

PROSE = "|".join([
    "The parties met on the fourth of March and agreed to the schedule",
    "set out in the attached order. Nothing in this paragraph is",
    "remarkable, and that is the point of it.",
] * 3)

# Long enough to clear the garbled threshold, and free of every function
# word the heuristic looks for: what a nonstandard font encoding yields.
GARBLED = "|".join(["_;\\5&^;HZ55aT2Z[^ 9QX7 KJHG%%$ ZZQ ] 8YT4 ;;LKJ 0POI"] * 8)


def _pdf(path: Path, pages: list[str]) -> Path:
    """One page per entry: ``"text:<lines joined by |>"``, ``"image"``,
    ``"header-over-image"``, or ``"blank"``."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image

    c = canvas.Canvas(str(path), pagesize=letter)
    for spec in pages:
        if spec.startswith("text:"):
            y = 700
            for line in spec[5:].split("|"):
                c.setFont("Helvetica", 11)
                c.drawString(72, y, line)
                y -= 14
        elif spec == "image":
            img = Image.new("RGB", (600, 800), (120, 120, 120))
            c.drawImage(ImageReader(img), 36, 36, width=540, height=720)
        elif spec == "header-over-image":
            c.setFont("Helvetica", 11)
            c.drawString(72, 750, "From: Jane Roe  To: John Smith  Subject: the "
                                  "screenshot of the thread is below for you")
            img = Image.new("RGB", (600, 700), (120, 120, 120))
            c.drawImage(ImageReader(img), 36, 36, width=540, height=650)
        elif spec == "blank":
            pass
        else:
            raise ValueError(spec)
        c.showPage()
    c.save()
    return path


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True)


@pytest.fixture
def mixed(tmp_path: Path) -> Path:
    return _pdf(tmp_path / "mixed.pdf", [
        f"text:{PROSE}", "image", "blank", "text:Exhibit A",
        "header-over-image", f"text:{GARBLED}",
    ])


def test_every_page_is_classified(mixed: Path) -> None:
    proc = run("--json", str(mixed))
    (survey,) = json.loads(proc.stdout)
    kinds = [d["kind"] for d in survey["detail"]]
    assert kinds == ["text", "image-only", "blank", "sparse",
                     "image-bodied", "garbled"], kinds
    assert survey["pages"] == 6


def test_exit_status_flags_uncovered_pages(mixed: Path, tmp_path: Path) -> None:
    assert run(str(mixed)).returncode == 1
    clean = _pdf(tmp_path / "clean.pdf", [f"text:{PROSE}", f"text:{PROSE}"])
    proc = run(str(clean))
    assert proc.returncode == 0, proc.stdout
    assert "needs OCR or eyes" not in proc.stdout


def test_table_names_the_pages_that_need_eyes(mixed: Path) -> None:
    proc = run(str(mixed))
    line = next(l for l in proc.stdout.splitlines() if "needs OCR or eyes" in l)
    for token in ("2(image-only)", "4(sparse)", "5(image-bodied)", "6(garbled)"):
        assert token in line, line
    assert "3(" not in line, "a blank page needs no OCR"


def test_text_dump_marks_every_page_and_names_the_unread(mixed: Path) -> None:
    proc = run("--text", str(mixed))
    for k in range(1, 7):
        assert f"[[[ page {k} of 6 ]]]" in proc.stdout
    assert "6 page(s) emitted ]]]" in proc.stdout
    assert "NO TEXT LAYER (image-only)" in proc.stdout
    assert "NO TEXT LAYER (blank)" in proc.stdout
    assert "<< SPARSE" in proc.stdout
    assert "<< IMAGE-BODIED" in proc.stdout
    assert "<< GARBLED" in proc.stdout
    assert "pages NOT covered by this dump: 2, 4, 5, 6" in proc.stdout
    assert proc.returncode == 1
    assert PROSE.split("|")[0] in proc.stdout, "readable text is emitted in full"


def test_text_dump_of_a_covered_document_is_clean(tmp_path: Path) -> None:
    clean = _pdf(tmp_path / "clean.pdf", [f"text:{PROSE}"])
    proc = run("--text", str(clean))
    assert proc.returncode == 0
    assert "NOT covered" not in proc.stdout
    assert "[[[ page 1 of 1 ]]]" in proc.stdout
