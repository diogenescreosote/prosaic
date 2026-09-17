"""\\exhibit{} inline citations: when a page number is worth printing.

A `pages:` selection that pulls exactly one simple page out of a
source becomes a one-page attachment with nothing printed on it to
match a "p. X" against -- a Gmail thread export carries no page
numbers of its own. A selection naming a real range or list usually
does correspond to something visible on the attached page (the
source's own printed numbering, or a Bates stamp), so that citation
is left alone.
"""

from __future__ import annotations

from pathlib import Path

from pleading.md_pleading import Exhibit, substitute_exhibit_refs


def _exhibit(letter: str, pages: str | None) -> Exhibit:
    return Exhibit(shortname="x", title="Some Exhibit", path=Path("x.pdf"),
                   letter=letter, pages=pages)


def test_single_simple_page_has_no_pin_cite():
    body = r"See \exhibit{g}."
    cite = substitute_exhibit_refs(body, {"g": _exhibit("G", "8")})
    assert cite == "See Exhibit G."


def test_page_range_keeps_pin_cite():
    body = r"See \exhibit{d}."
    cite = substitute_exhibit_refs(body, {"d": _exhibit("D", "23-34")})
    assert cite == "See Exhibit D, pp. 23–34."


def test_page_list_keeps_pin_cite():
    body = r"See \exhibit{c}."
    cite = substitute_exhibit_refs(body, {"c": _exhibit("C", "1-2, 10")})
    assert cite == "See Exhibit C, pp. 1–2, 10."


def test_no_pages_spec_has_no_pin_cite():
    body = r"See \exhibit{b}."
    cite = substitute_exhibit_refs(body, {"b": _exhibit("B", None)})
    assert cite == "See Exhibit B."
