"""Exhibit assembly: index, tab sheets, and the exhibit pages themselves.

Produces one PDF: a table of exhibits, then for each exhibit a slip sheet
("EXHIBIT A") followed by the cited page range of its source document.
Sources arrive as bytes keyed by document id, so assembly never touches
the filesystem and originals are never modified.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from prosaic.model import Exhibit

PAGE_WIDTH, PAGE_HEIGHT = letter


class MissingExhibitSourceError(KeyError):
    """An exhibit references a document that was not supplied."""


class ExhibitPageRangeError(ValueError):
    """An exhibit cites pages its source document does not have."""


def _index_page(exhibits: Sequence[Exhibit], counts: dict[str, int]) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=letter)
    canvas.setTitle("Table of Exhibits")
    canvas.setFont("Courier-Bold", 14)
    canvas.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 96, "TABLE OF EXHIBITS")
    canvas.setFont("Courier", 11)
    y = PAGE_HEIGHT - 140
    for exhibit in exhibits:
        pages = counts[exhibit.label]
        page_note = f"{pages} page" + ("s" if pages != 1 else "")
        canvas.drawString(90, y, f"Exhibit {exhibit.label}")
        canvas.drawString(190, y, exhibit.description[:70])
        canvas.drawRightString(PAGE_WIDTH - 72, y, page_note)
        y -= 22
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _slip_sheet(label: str) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=letter)
    canvas.setFont("Courier-Bold", 28)
    canvas.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2, f"EXHIBIT {label}")
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def assemble_exhibits(exhibits: Sequence[Exhibit], sources: Mapping[str, bytes]) -> bytes:
    """One PDF: table of exhibits, then slip sheet plus pages per exhibit."""
    selections: list[tuple[Exhibit, PdfReader, range]] = []
    for exhibit in exhibits:
        if exhibit.document_id not in sources:
            raise MissingExhibitSourceError(
                f"exhibit {exhibit.label} needs document {exhibit.document_id}"
            )
        reader = PdfReader(io.BytesIO(sources[exhibit.document_id]))
        last = exhibit.last_page if exhibit.last_page is not None else len(reader.pages)
        if last > len(reader.pages) or exhibit.first_page > len(reader.pages):
            raise ExhibitPageRangeError(
                f"exhibit {exhibit.label} cites pages {exhibit.first_page}-{last} "
                f"but {exhibit.document_id} has {len(reader.pages)}"
            )
        selections.append((exhibit, reader, range(exhibit.first_page - 1, last)))

    counts = {exhibit.label: len(pages) for exhibit, _, pages in selections}
    writer = PdfWriter()
    writer.append(io.BytesIO(_index_page(exhibits, counts)))
    for exhibit, reader, pages in selections:
        writer.append(io.BytesIO(_slip_sheet(exhibit.label)))
        for index in pages:
            writer.add_page(reader.pages[index])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
