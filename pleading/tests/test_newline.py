"""\\newline: a hard line break inside a paragraph.

A paragraph's source lines rewrap into one flow, so until now the only
way to put "GRANTED ____ DENIED ____" on its own line under a proposed
order's paragraph was a new paragraph, which inserts a blank separator
line. `\\newline` (or Markdown's two trailing spaces) ends the output
line and continues the same paragraph on the next grid line: no blank
line, no new paragraph number, the paragraph's own continuation indent.
DOCX carries it as a `w:br` run; TXT as a newline inside the block.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pymupdf

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402

FRONT = """---
doctype: document
heading_numbers: false
paper_title: "Proposed Order"
---

{body}
"""

LONG = ("The request of Petitioner Jane Roe for an order compelling the "
        "deposition of John Doe, with the costs of the reporter borne by "
        "Respondent Richard Roe, is")
FILLIN = "GRANTED ____ DENIED ____"


def build(tmp_path: Path, body: str, script: str = "md_pleading.py",
          suffix: str = ".pdf") -> Path:
    src = tmp_path / "doc.md"
    src.write_text(FRONT.format(body=body))
    out = tmp_path / f"doc{suffix}"
    proc = subprocess.run(
        [sys.executable, str(PLEADING_DIR / script), str(src), str(out)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def text_lines(pdf: Path) -> list[tuple[float, float, str]]:
    """Every text line on page 1 as (baseline y, left x, text), top down.

    Spans sharing a baseline are one line, whatever pymupdf's own
    grouping did with them.
    """
    page = pymupdf.open(pdf)[0]
    by_y: dict[float, list[tuple[float, str]]] = {}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if not span["text"].strip():
                    continue
                y = round(span["origin"][1], 1)
                by_y.setdefault(y, []).append((span["origin"][0], span["text"]))
    out = []
    for y in sorted(by_y):
        spans = sorted(by_y[y])
        text = " ".join("".join(s for _, s in spans).split())
        out.append((y, spans[0][0], text))
    return out


def body_line(lines, needle: str) -> tuple[float, float, str]:
    """The one line containing ``needle``."""
    hits = [ln for ln in lines if needle in ln[2]]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


def pitch(lines) -> float:
    """The grid pitch: the smallest gap between consecutive text lines on
    the page, which the LONG paragraph's natural wrap always supplies."""
    ys = sorted(ln[0] for ln in lines)
    return min(b - a for a, b in zip(ys, ys[1:]))


def assert_breaks_onto_next_grid_line(pdf: Path) -> None:
    lines = text_lines(pdf)
    before = body_line(lines, "Richard Roe, is")
    after = body_line(lines, FILLIN)
    assert after[2] == FILLIN, "the break starts a fresh line"
    assert abs((after[0] - before[0]) - pitch(lines)) < 0.5, (
        "the continuation sits on the very next grid line: no blank between")
    margin = body_line(lines, "The request of")[1]
    assert abs(after[1] - margin) < 0.5, "continuation starts at the margin"


def test_newline_macro_starts_the_next_grid_line(tmp_path):
    pdf = build(tmp_path, f"{LONG} \\newline {FILLIN}\n\nNext paragraph.")
    assert_breaks_onto_next_grid_line(pdf)
    lines = text_lines(pdf)
    # The paragraph that follows is still separated by its blank line.
    nxt = body_line(lines, "Next paragraph.")
    fill = body_line(lines, FILLIN)
    assert abs((nxt[0] - fill[0]) - 2 * pitch(lines)) < 0.5


def test_two_trailing_spaces_are_a_synonym(tmp_path):
    pdf = build(tmp_path, f"{LONG}  \n{FILLIN}\n\nNext paragraph.")
    assert_breaks_onto_next_grid_line(pdf)


def test_single_trailing_space_and_plain_line_ends_still_rewrap(tmp_path):
    pdf = build(tmp_path, "Short line \nalso short.\n\nAnd short\nagain.")
    lines = text_lines(pdf)
    assert body_line(lines, "Short line")[2] == "Short line also short."
    assert body_line(lines, "And short")[2] == "And short again."


def test_autonumbered_paragraph_continues_unnumbered_at_its_own_indent(tmp_path):
    pdf = build(tmp_path, f"#. {LONG} \\newline {FILLIN}\n\n#. Second request.")
    lines = text_lines(pdf)
    first = body_line(lines, "1. The request")
    fill = body_line(lines, FILLIN)
    assert fill[2] == FILLIN, "no number on the continuation"
    assert body_line(lines, "Second request")[2].startswith("2."), (
        "the counter did not advance at the break")
    # An autonumbered paragraph is an ordinary paragraph: its wrapped
    # lines start at the margin, and so does the hard-break continuation.
    wrapped = body_line(lines, "with the costs")
    assert abs(fill[1] - wrapped[1]) < 0.5 and abs(fill[1] - first[1]) < 0.5


def test_numbered_list_item_continues_at_the_hanging_indent(tmp_path):
    # A tight list is the construct with a hanging indent: the text after
    # the break aligns with the item's text, not with its number.
    pdf = build(tmp_path, f"1. {LONG} \\newline {FILLIN}\n2. Second item.")
    lines = text_lines(pdf)
    first = body_line(lines, "1. The request")
    fill = body_line(lines, FILLIN)
    assert fill[2] == FILLIN
    number_w = mp.pdfmetrics.stringWidth("1. ", mp.FONT_NAME, mp.FONT_SIZE)
    assert abs(fill[1] - (first[1] + number_w)) < 0.5, (fill[1], first[1], number_w)


def test_break_inside_a_block_quote_stays_in_the_quote(tmp_path):
    pdf = build(tmp_path, f"{LONG}.\n\n> Quoted matter, which \\newline continues "
                          "here.\n\nAfter.")
    lines = text_lines(pdf)
    a = body_line(lines, "Quoted matter")
    b = body_line(lines, "continues here")
    assert b[2] == "continues here."
    margin = body_line(lines, "The request of")[1]
    assert abs(a[1] - b[1]) < 0.5 and a[1] > margin + 30, "both lines indented as quote"
    assert abs((b[0] - a[0]) - pitch(lines)) < 0.5


def test_docx_carries_a_w_br_run(tmp_path):
    docx = build(tmp_path, f"{LONG} \\newline {FILLIN}", "md_to_docx.py", ".docx")
    with zipfile.ZipFile(docx) as z:
        xml = z.read("word/document.xml").decode()
    para = xml[xml.index("Richard Roe, is"):xml.index(FILLIN)]
    assert "<w:br/>" in para, para
    assert "</w:p>" not in para, "one paragraph, not two"
    assert "<w:t>GRANTED" in xml or '<w:t xml:space="preserve">GRANTED' in xml


def test_txt_breaks_the_line_inside_the_block(tmp_path):
    txt = build(tmp_path, f"{LONG} \\newline {FILLIN}", "md_to_txt.py", ".txt")
    assert "Richard Roe, is\nGRANTED ____ DENIED ____\n" in txt.read_text()


def test_fixedwidth_contents_are_verbatim(tmp_path):
    pdf = build(tmp_path, "Path \\fixedwidth{a\\newline b} and `c\\newline d` end.")
    lines = text_lines(pdf)
    assert body_line(lines, "Path")[2] == "Path a\\newline b and c\\newline d end."


def test_parser_does_not_glue_or_lose_words_around_the_break():
    words = mp.spans_to_styled_words(mp.parse_inline_styles("is \\newline GRANTED"))
    assert [w.text for w in words] == ["is", "", "GRANTED"]
    assert words[1].line_break and not words[2].no_space_before
    # A bare token only: \newlines is not the macro.
    spans = mp.parse_inline_styles("\\newlines")
    assert not any(s.line_break for s in spans)
    lines = mp.wrap_styled_words(words, 10_000.0)
    # The undrawn break marker closes the line it ended.
    assert [[w.text for w in ln] for ln in lines] == [["is", ""], ["GRANTED"]]
    assert lines[0][-1].line_break and not lines[0][-1].keep_with_next


def test_newline_skip_leaves_one_empty_grid_line_inside_the_paragraph(tmp_path):
    pdf = build(tmp_path, f"#. {LONG} \\newline{{skip}} {FILLIN}\n\n#. Second request.")
    lines = text_lines(pdf)
    before = body_line(lines, "Richard Roe, is")
    fill = body_line(lines, FILLIN)
    assert fill[2] == FILLIN, "no number, nothing else on the line"
    assert abs((fill[0] - before[0]) - 2 * pitch(lines)) < 0.5, "exactly one empty line"
    # Still one paragraph: the next autonumbered paragraph is 2., and it
    # sits the usual one blank line below the fill-in.
    second = body_line(lines, "Second request")
    assert second[2].startswith("2.")
    assert abs((second[0] - fill[0]) - 2 * pitch(lines)) < 0.5


def test_newline_skip_in_docx_is_two_breaks_in_one_paragraph(tmp_path):
    docx = build(tmp_path, f"{LONG} \\newline{{skip}} {FILLIN}", "md_to_docx.py", ".docx")
    with zipfile.ZipFile(docx) as z:
        xml = z.read("word/document.xml").decode()
    para = xml[xml.index("Richard Roe, is"):xml.index(FILLIN)]
    assert para.count("<w:br/>") == 2, para
    assert "</w:p>" not in para, "one paragraph, not two"


def test_trailing_spaces_never_mean_skip():
    body = mp.mark_trailing_space_breaks("is   \nGRANTED")
    assert body == "is \\newline\nGRANTED"
    spans = mp.parse_inline_styles("is \\newline{skip} GRANTED")
    assert sum(1 for s in spans if s.line_break) == 2
    assert [s.text for s in spans if not s.line_break] == ["is", "GRANTED"]


# --- {keep}: the continuation stays on the page of the line before it ---

def page_of(pdf: Path, needle: str) -> int:
    hits = [i for i, page in enumerate(pymupdf.open(pdf)) if needle in page.get_text()]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


def split_at_break_body(flags: str, fillers: int) -> str:
    """A paragraph whose line before the \\newline lands on the page's last
    grid line when preceded by ``fillers`` one-line paragraphs."""
    filler = "\n\n".join(f"Filler paragraph {i}." for i in range(fillers))
    return (f"{filler}\n\n#. Short request, \\newline which is \\newline{flags} "
            f"{FILLIN}\n\n#. Next.")


def find_split(tmp_path: Path) -> int:
    """The filler count at which plain \\newline splits across the page."""
    for n in range(8, 20):
        pdf = build(tmp_path, split_at_break_body("", n))
        if page_of(pdf, "which is") == 0 and page_of(pdf, FILLIN) == 1:
            return n
    raise AssertionError("never found a filler count that splits at the break")


def test_plain_newline_may_split_across_pages(tmp_path):
    n = find_split(tmp_path)
    pdf = build(tmp_path, split_at_break_body("{skip}", n))
    assert page_of(pdf, "which is") == 0 and page_of(pdf, FILLIN) == 1


def test_keep_moves_the_whole_paragraph_to_the_next_page(tmp_path):
    n = find_split(tmp_path)
    for flags in ("{keep}", "{skip,keep}", "{keep, skip}"):
        pdf = build(tmp_path, split_at_break_body(flags, n))
        # The whole paragraph moved: its first line too, not only the tied pair.
        assert page_of(pdf, "Short request,") == 1, flags
        assert page_of(pdf, FILLIN) == 1, flags
        assert page_of(pdf, f"Filler paragraph {n - 1}.") == 0, flags
        page2 = page_lines(pdf, 1)
        before = next(ln for ln in page2 if "which is" in ln[2])
        fill = next(ln for ln in page2 if FILLIN in ln[2])
        gap = 2 if "skip" in flags else 1
        assert abs((fill[0] - before[0]) - gap * pitch(page2)) < 0.5, flags
        assert next(ln for ln in page2 if "Next." in ln[2])[2].startswith("2.")


def page_lines(pdf: Path, index: int) -> list[tuple[float, float, str]]:
    page = pymupdf.open(pdf)[index]
    by_y: dict[float, list[tuple[float, str]]] = {}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"].strip():
                    y = round(span["origin"][1], 1)
                    by_y.setdefault(y, []).append((span["origin"][0], span["text"]))
    return [(y, sorted(v)[0][0], " ".join("".join(t for _, t in sorted(v)).split()))
            for y, v in sorted(by_y.items())]


def test_keep_in_a_paragraph_longer_than_a_page_breaks_a_line_earlier(tmp_path):
    # Plain breaks make every line's position known. Calibrate: with the
    # title and its blank on the first two grid lines, page 1 holds L
    # filler lines, so a page holds L + 2; filler index 2L + 1 is then
    # the last line of page 2. Put "is" there: the paragraph is longer
    # than a page, so it cannot move whole, and the page must turn
    # BEFORE "is" instead of after it.
    def body(n: int, flags: str) -> str:
        fill = " \\newline ".join(f"Filler line {i}" for i in range(n))
        return f"{fill} \\newline Short request, is \\newline{flags} {FILLIN}\n\nAfter."

    probe = build(tmp_path, body(80, ""))
    on_page_one = sum(1 for ln in page_lines(probe, 0) if ln[2].startswith("Filler line"))
    m = 2 * on_page_one + 1
    plain = build(tmp_path, body(m, ""))
    assert page_of(plain, "Short request, is") == 1 and page_of(plain, FILLIN) == 2, (
        "premise: the plain break splits at the page turn")
    kept = build(tmp_path, body(m, "{keep}"))
    assert page_of(kept, "Short request, is") == page_of(kept, FILLIN) == 2
    assert page_of(kept, f"Filler line {m - 1}\n") == 1, "the paragraph split a line earlier"
    assert page_of(kept, "Filler line 0\n") == 0, "and did not move whole"


def test_docx_keep_sets_keeplines_only_when_asked(tmp_path):
    for flags, expected in (("{keep}", True), ("{skip,keep}", True), ("", False), ("{skip}", False)):
        docx = build(tmp_path, f"{LONG} \\newline{flags} {FILLIN}", "md_to_docx.py", ".docx")
        with zipfile.ZipFile(docx) as z:
            xml = z.read("word/document.xml").decode()
        start = xml.rfind("<w:p>", 0, xml.index("Richard Roe, is"))
        start = max(start, xml.rfind("<w:p ", 0, xml.index("Richard Roe, is")))
        para = xml[start:xml.index("</w:p>", xml.index(FILLIN))]
        assert ("<w:keepLines/>" in para) is expected, (flags, para[:300])
        assert para.count("<w:br/>") == (2 if "skip" in flags else 1), flags


def test_flag_combinations_parse_independently():
    def breaks(src: str):
        return [(s.keep_with_next) for s in mp.parse_inline_styles(src) if s.line_break]
    assert breaks("a \\newline b") == [False]
    assert breaks("a \\newline{skip} b") == [False, False]
    assert breaks("a \\newline{keep} b") == [True]
    assert breaks("a \\newline{skip,keep} b") == [True, True]
    assert breaks("a \\newline{ keep , skip } b") == [True, True]
    # An unknown flag is not swallowed: the break happens, the braces show.
    spans = mp.parse_inline_styles("a \\newline{kep} b")
    assert breaks("a \\newline{kep} b") == [False]
    assert "{kep}" in "".join(s.text for s in spans)
    assert mp.mark_trailing_space_breaks("a  \nb") == "a \\newline\nb"


def test_keep_runs_tie_the_right_lines():
    def line(text: str, brk: str | None = None):
        words = [mp.StyledWord(text)] if text else []
        if brk is not None:
            words.append(mp.StyledWord("", line_break=True, keep_with_next=brk == "keep"))
        return (words, 0.0)
    plain = [line("a", "plain"), line("b"), ([], 0.0)]
    assert mp.keep_runs(plain) == {}
    kept = [line("a", "keep"), line("b"), ([], 0.0)]
    assert mp.keep_runs(kept) == {0: 2}
    skip_keep = [line("a", "keep"), line("", "keep"), line("b"), ([], 0.0)]
    assert mp.keep_runs(skip_keep) == {0: 3}
    trailing = [line("a", "keep"), ([], 0.0)]
    assert mp.keep_runs(trailing) == {}, "the separator is never tied"


def test_keep_paragraph_starting_on_the_last_grid_line_moves_whole(tmp_path):
    # Fillers put the paragraph's FIRST line on the page's last grid line,
    # so the page would turn after it, before the break, not at it. keep
    # still moves the whole three-line paragraph to the next page.
    def body(n: int) -> str:
        # One two-line filler shifts parity so the start can hit the last line.
        filler = "\n\n".join(f"Filler paragraph {i}." for i in range(n))
        return (f"Filler lead \\newline continued.\n\n{filler}\n\n"
                f"#. Short request, \\newline which is \\newline{{keep}} "
                f"{FILLIN}\n\n#. Next.")

    for n in range(8, 24):
        plain = build(tmp_path, body(n).replace("{keep}", ""))
        if page_of(plain, "Short request,") == 0 and page_of(plain, "which is") == 1:
            break
    else:
        raise AssertionError("never placed the first line on the last grid line")
    kept = build(tmp_path, body(n))
    for needle in ("Short request,", "which is", FILLIN):
        assert page_of(kept, needle) == 1, needle
    assert page_of(kept, f"Filler paragraph {n - 1}.") == 0
    page2 = page_lines(kept, 1)
    ys = [next(ln[0] for ln in page2 if s in ln[2]) for s in ("Short request,", "which is", FILLIN)]
    assert abs((ys[1] - ys[0]) - pitch(page2)) < 0.5 and abs((ys[2] - ys[1]) - pitch(page2)) < 0.5
