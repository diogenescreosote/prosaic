"""Embedded filled forms are flattened to ink.

pypdf's add_page copies widget annotations but never merges an AcroForm.
Two filled copies of the same Judicial Council form therefore land in one
packet as orphaned widgets with colliding fully-qualified names (every
filled SUBP-010 carries a FillText1). The PDF spec requires same-named
fields to share one value, so field-oriented readers unify them and one
exhibit's value silently displaces the other's -- while appearance-stream
renderers (Preview, pdftotext) still draw each widget's own ink and look
correct. The fix: any PDF attached as an exhibit has its fields baked
into page content first.
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
import pypdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from md_pleading import Exhibit, append_exhibit_attachment, flatten_form_fields


def _form_pdf(path: Path, value: str) -> None:
    """One page with a text field named FillText1 holding *value*."""
    doc = fitz.open()
    page = doc.new_page()
    w = fitz.Widget()
    w.field_name = "FillText1"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(72, 72, 400, 100)
    w.field_value = value
    page.add_widget(w)
    doc.save(str(path))
    doc.close()


def test_flatten_form_fields_bakes_value_and_drops_widgets(tmp_path=None):
    with TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "form.pdf"
        _form_pdf(src, "Deponent Alpha")
        flat = flatten_form_fields(src, tmp)
        assert flat != src, "a form PDF must be rewritten"
        doc = fitz.open(str(flat))
        assert not any(True for p in doc for _ in p.widgets()), "widgets must be gone"
        assert "Deponent Alpha" in doc[0].get_text()
        doc.close()


def test_flatten_passthrough_without_fields():
    with TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "plain.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(src))
        doc.close()
        assert flatten_form_fields(src, tmp) == src


def test_two_same_named_forms_keep_distinct_values_in_one_packet():
    """The observed failure: two filled copies of one JC form in a packet.

    Before the fix, both pages carried a live FillText1 widget and a
    field-oriented reader saw one value on both faces. After it, neither
    page has a widget and each page's text keeps its own value.
    """
    with TemporaryDirectory() as td:
        tmp = Path(td)
        a, b = tmp / "a.pdf", tmp / "b.pdf"
        _form_pdf(a, "Deponent Alpha")
        _form_pdf(b, "Deponent Bravo")
        writer = pypdf.PdfWriter()
        for letter, path in (("A", a), ("B", b)):
            ex = Exhibit(shortname=letter.lower(), title=f"Exhibit {letter}",
                         path=path, letter=letter)
            append_exhibit_attachment(writer, ex, tmp)
        out = tmp / "packet.pdf"
        with open(out, "wb") as fh:
            writer.write(fh)

        doc = fitz.open(str(out))
        assert not any(True for p in doc for _ in p.widgets()), "packet must carry no live fields"
        assert "Deponent Alpha" in doc[0].get_text()
        assert "Deponent Bravo" in doc[1].get_text()
        assert "Deponent Alpha" not in doc[1].get_text()
        # and a by-name field reader now has nothing to unify
        r = pypdf.PdfReader(str(out))
        assert not (r.get_fields() or {})
        doc.close()


if __name__ == "__main__":
    test_flatten_form_fields_bakes_value_and_drops_widgets()
    test_flatten_passthrough_without_fields()
    test_two_same_named_forms_keep_distinct_values_in_one_packet()
    print("all form-flattening tests passed")
