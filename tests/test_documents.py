"""Pleading paper and exhibit assembly, verified by reading the PDFs back."""

from __future__ import annotations

import datetime
import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from prosaic.documents import (
    ExhibitPageRangeError,
    MissingExhibitSourceError,
    Pleading,
    assemble_exhibits,
    render_pleading,
)
from prosaic.model import Exhibit


def sample_pleading(paragraphs: int = 3) -> Pleading:
    return Pleading(
        title="Declaration of Jane Doe in Support of Motion to Compel",
        attorney_block=("Jane Doe", "123 Example Lane", "Oakland, CA 94601", "Self-represented"),
        court_name="Superior Court of California, County of Alameda",
        plaintiff_caption="Jane Doe",
        defendant_caption="Roe Logistics, Inc.",
        case_number="26CV012345",
        paragraphs=tuple(
            f"This is paragraph {n}, reciting facts about the services agreement "
            "and the deliveries that never arrived."
            for n in range(1, paragraphs + 1)
        ),
        signature_name="Jane Doe",
        signed_on=datetime.date(2026, 3, 2),
    )


def _page_texts(pdf: bytes) -> list[str]:
    return [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]


def test_pleading_first_page_carries_the_full_caption() -> None:
    pages = _page_texts(render_pleading(sample_pleading()))
    first, last = pages[0], pages[-1]
    assert "SUPERIOR COURT OF CALIFORNIA, COUNTY OF SAN FRANCISCO" in first
    assert "Case No. 26CV012345" in first
    assert "JANE DOE," in first
    assert "ROE LOGISTICS, INC.," in first
    assert "This is paragraph 1" in first
    assert "Dated: March 2, 2026" in last


def test_pleading_pages_are_numbered_with_a_title_footer() -> None:
    pages = _page_texts(render_pleading(sample_pleading(paragraphs=30)))
    assert len(pages) > 1
    for number, text in enumerate(pages, start=1):
        assert f"- {number} -" in text
        assert "DECLARATION OF JANE DOE" in text
        assert "28" in text  # every sheet shows all 28 line numbers


def test_pleading_rejects_a_blank_title() -> None:
    with pytest.raises(ValueError, match="title"):
        Pleading(
            title="  ",
            attorney_block=("Jane Doe",),
            court_name="Superior Court of California, County of Alameda",
            plaintiff_caption="Jane Doe",
            defendant_caption="Roe Logistics, Inc.",
            case_number="26CV012345",
            paragraphs=("Denied.",),
            signature_name="Jane Doe",
            signed_on=datetime.date(2026, 3, 2),
        )


def test_pleading_rejects_an_oversized_attorney_block() -> None:
    with pytest.raises(ValueError, match="lines 1 through 7"):
        Pleading(
            title="Answer",
            attorney_block=tuple(f"line {n}" for n in range(8)),
            court_name="Superior Court of California, County of Alameda",
            plaintiff_caption="Jane Doe",
            defendant_caption="Roe Logistics, Inc.",
            case_number="26CV012345",
            paragraphs=("Denied.",),
            signature_name="Jane Doe",
            signed_on=datetime.date(2026, 3, 2),
        )


def _little_pdf(pages: int, label: str) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=letter)
    for number in range(1, pages + 1):
        canvas.setFont("Helvetica", 30)
        canvas.drawCentredString(306, 400, f"{label} page {number}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


EXHIBITS = [
    Exhibit(
        label="A",
        description="Services agreement dated January 5, 2026",
        document_id="doc-agreement",
        first_page=2,
        last_page=3,
    ),
    Exhibit(label="B", description="Demand letter", document_id="doc-letter"),
]


def test_exhibit_packet_has_index_slip_sheets_and_cited_pages() -> None:
    packet = assemble_exhibits(
        EXHIBITS,
        {"doc-agreement": _little_pdf(4, "AGREEMENT"), "doc-letter": _little_pdf(2, "LETTER")},
    )
    texts = _page_texts(packet)
    assert len(texts) == 7  # index + (slip + 2) + (slip + 2)
    assert "TABLE OF EXHIBITS" in texts[0]
    assert "EXHIBIT A" in texts[1]
    assert "AGREEMENT page 2" in texts[2]  # range starts at cited page, not page 1
    assert "AGREEMENT page 3" in texts[3]
    assert "EXHIBIT B" in texts[4]
    assert "LETTER page 1" in texts[5]


def test_exhibit_assembly_requires_every_source() -> None:
    with pytest.raises(MissingExhibitSourceError, match="doc-letter"):
        assemble_exhibits(EXHIBITS, {"doc-agreement": _little_pdf(4, "AGREEMENT")})


def test_exhibit_assembly_rejects_pages_beyond_the_source() -> None:
    with pytest.raises(ExhibitPageRangeError, match="exhibit A"):
        assemble_exhibits(
            EXHIBITS,
            {"doc-agreement": _little_pdf(2, "AGREEMENT"), "doc-letter": _little_pdf(2, "LETTER")},
        )
