"""A form and its attachment are filed as one PDF (attachment_gate.py,
filing_check.py).

A clerk rejects an envelope whose request-for-order form checks
"Attachment 9" while the attachment is uploaded as its own document. The
build gate refuses a --final envelope that leaves a checked attachment
box or an attachment-titled source unpaired; `sc filing-check` refuses a
staging folder that holds an attachment as a separate PDF.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pleading"))

import attachment_gate  # noqa: E402
import filing_check  # noqa: E402

DESC: dict[str, Any] = {
    "form": "xx100",
    "fields": {
        "facts": {"overflow_checkbox": "attachment_9"},
    },
    "checkboxes": {
        "attachment_9": {"default": True},
        "attachment_7": {"default": False},
        "other_top": {"default": True},
    },
}


def load(form_id: str) -> dict[str, Any]:
    if form_id != "xx100":
        raise FileNotFoundError(form_id)
    return DESC


def write(src: Path, name: str, front: str) -> str:
    path = src / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\n\nBody.\n", encoding="utf-8")
    return name


@pytest.fixture
def src(tmp_path: Path) -> Path:
    return tmp_path / "src"


FORM_ONLY = "cover_sheet: xx100\ncover_sheet_only: true"
ATTACHMENT = 'paper_title: "DECLARATION OF JANE ROE (ATTACHMENT 9 TO REQUEST FOR ORDER)"'


# --- the build gate ---------------------------------------------------------


def test_default_on_attachment_box_counts(src: Path) -> None:
    write(src, "rfo/form.md", FORM_ONLY)
    meta = attachment_gate.read_front_matter(src / "rfo/form.md")
    assert attachment_gate.checked_attachment_boxes(meta, load) == ["attachment_9"]


def test_split_pair_without_attachment_of_is_two_findings(src: Path) -> None:
    f = write(src, "rfo/form.md", FORM_ONLY)
    a = write(src, "rfo/decl.md", ATTACHMENT)
    problems = attachment_gate.envelope_problems([(f, None), (a, None)], src, load)
    assert len(problems) == 2
    assert "checks attachment_9" in problems[0]
    assert "never filed as its own document" in problems[1]


def test_declared_pair_passes(src: Path) -> None:
    f = write(src, "rfo/form.md", FORM_ONLY)
    a = write(src, "rfo/decl.md", ATTACHMENT)
    assert attachment_gate.envelope_problems([(f, None), (a, f)], src, load) == []


def test_attachment_with_its_form_as_cover_sheet_passes(src: Path) -> None:
    a = write(src, "rfo/decl.md", ATTACHMENT + "\ncover_sheet: xx100")
    assert attachment_gate.envelope_problems([(a, None)], src, load) == []


def test_box_set_false_needs_no_attachment(src: Path) -> None:
    f = write(src, "rfo/form.md", FORM_ONLY + "\nforms:\n  xx100:\n    attachment_9: false")
    assert attachment_gate.envelope_problems([(f, None)], src, load) == []


def test_engine_managed_overflow_box_is_not_an_orphan(src: Path) -> None:
    f = write(src, "rfo/form.md", FORM_ONLY + "\nforms:\n  xx100:\n    facts: The facts are short.")
    assert attachment_gate.envelope_problems([(f, None)], src, load) == []


def test_attachment_of_outside_the_envelope_is_a_finding(src: Path) -> None:
    a = write(src, "rfo/decl.md", ATTACHMENT)
    problems = attachment_gate.envelope_problems([(a, "rfo/form.md")], src, load)
    assert problems and "not a source in this envelope" in problems[0]


def test_attachment_of_a_non_form_is_a_finding(src: Path) -> None:
    p = write(src, "rfo/memo.md", 'paper_title: "MEMORANDUM"')
    a = write(src, "rfo/decl.md", ATTACHMENT)
    problems = attachment_gate.envelope_problems([(p, None), (a, p)], src, load)
    assert problems and "no cover_sheet form" in problems[0]


def test_ordinary_pleadings_are_untouched(src: Path) -> None:
    m = write(src, "rfo/memo.md", 'paper_title: "MEMORANDUM OF POINTS AND AUTHORITIES"')
    d = write(src, "rfo/decl.md", 'paper_title: "DECLARATION OF JANE ROE"')
    assert attachment_gate.envelope_problems([(m, None), (d, None)], src, load) == []


# --- the staging-folder check ---------------------------------------------


def _pdf(path: Path, lines: list[str], pages: int = 1) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(pages):
        y = 740
        for line in lines:
            c.drawString(72, y, line)
            y -= 14
        c.showPage()
    c.save()


FORM_PAGE = [
    "REQUEST FOR ORDER",
    "XX-100 [Rev. July 1, 2025]",
    "Form Adopted for Mandatory Use",
    "Judicial Council of California",
]
DECL_PAGE = [
    "DECLARATION OF JANE ROE",
    "(ATTACHMENT 9 TO REQUEST FOR ORDER)",
    "I, Jane Roe, declare:",
]


def test_folder_with_separate_attachment_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(filing_check, "attachment_bearing_forms", lambda: {"XX-100": 4})
    _pdf(tmp_path / "1_form.pdf", FORM_PAGE, pages=4)
    _pdf(tmp_path / "2_decl.pdf", DECL_PAGE, pages=3)
    report = filing_check.check_folder(tmp_path)
    assert len(report.errors) == 1 and "2_decl.pdf" in report.errors[0]
    assert any("1_form.pdf" in w for w in report.warnings)
    assert filing_check.main([str(tmp_path)]) == 1


def test_folder_with_joined_form_and_attachment_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(filing_check, "attachment_bearing_forms", lambda: {"XX-100": 4})
    from pypdf import PdfReader, PdfWriter

    _pdf(tmp_path / "f.pdf", FORM_PAGE, pages=4)
    _pdf(tmp_path / "d.pdf", DECL_PAGE, pages=3)
    w = PdfWriter()
    for name in ("f.pdf", "d.pdf"):
        for page in PdfReader(str(tmp_path / name)).pages:
            w.add_page(page)
    out = tmp_path / "joined"
    out.mkdir()
    with (out / "1_form_with_attachment_9.pdf").open("wb") as fh:
        w.write(fh)
    report = filing_check.check_folder(out)
    assert report.errors == [] and report.warnings == []
    assert filing_check.main([str(out)]) == 0


def test_remote_appearance_without_proposed_order_warns(tmp_path: Path) -> None:
    _pdf(
        tmp_path / "ra.pdf",
        ["NOTICE OF REMOTE APPEARANCE", "RA-010", "Form Adopted for Mandatory Use"],
    )
    report = filing_check.check_folder(tmp_path)
    assert report.errors == []
    assert any("RA-020" in w for w in report.warnings)
