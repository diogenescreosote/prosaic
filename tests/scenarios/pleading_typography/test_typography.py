"""Pleading-typography scenario (spec: specs/pleading/generator.md).

Adversarial checks of the PDF renderer's typography and document
structure: em/en dash conversion (incl. edges adjacent to quotes and
numbers), smart quotes/apostrophes, section symbols, heading
auto-numbering with nesting and restarts, footnote placement and
page-bottom rendering across a multi-page document, \\declsignblock
(signed and unsigned), \\posblock expansion, pagination and footer
titles, and 28-line grid alignment on pages after the first.

Every assertion runs against the OUTPUT artifact (pdftotext / pypdf
visitor coordinates), never the engine's self-report. Sentinel tokens
(TK*) planted in the fixture sources make truncation detectable, and
the negative_control envelope proves the dash/quote alarms can fire.

xfail'd tests are real generator bugs — see
design/refactor-audit/typography_structure.md.
"""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.harness import scenario
from tests.harness.ai import assert_judgment, judge

DECL = "Declaration of Jane Roe.pdf"
POS_EMAIL = "Proof of Electronic Service.pdf"
POS_MAIL = "Proof of Service by Mail.pdf"
CONTROL = "Spaced Dash Control.pdf"
SHORT_PROBE = "Short Title Probe.pdf"

MD_PLEADING = scenario.PLEADING / "md_pleading.py"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    matter = scenario.load_scenario("pleading_typography",
                                    tmp_path_factory.mktemp("m"))
    for env in ("typography", "negative_control"):
        proc = scenario.build_envelope(matter, env)
        assert proc.returncode == 0, f"{env}: {proc.stderr[-2000:]}"
    return matter


@pytest.fixture(scope="module")
def decl_pdf(built):
    return built / "out" / "typography" / DECL


@pytest.fixture(scope="module")
def decl_text(decl_pdf):
    return scenario.pdf_text(decl_pdf)


@pytest.fixture(scope="module")
def decl_pages(decl_text):
    return decl_text.split("\f")


def _flat_body(text: str) -> str:
    """Flatten -layout text into one whitespace-normalized string with the
    margin line-number column removed, so phrase assertions can span the
    hard line wraps pdftotext introduces."""
    stripped = [re.sub(r"^\s{0,3}\d{1,2}(?:\s{2,}|\s*$)", "", ln)
                for ln in text.split("\n")]
    return " ".join(" ".join(stripped).split())


def _page_with(pages, needle: str) -> str:
    hits = [p for p in pages if needle in p]
    assert hits, f"no page contains {needle!r}"
    assert len(hits) == 1, f"{needle!r} appears on {len(hits)} pages"
    return hits[0]


# ---------------------------------------------------------------------------
# Em/en dashes, incl. edges adjacent to quotes and numbers
# ---------------------------------------------------------------------------

def test_em_dash_flush_against_words(decl_text):
    assert "January—TKEMD1a—and" in decl_text
    assert "---" not in decl_text, "raw --- leaked into the artifact"


def test_en_dash_in_date_and_number_ranges(decl_text):
    assert "January 23–March 3, 2026" in decl_text
    assert "2024–2025" in decl_text
    assert "12–14" in decl_text  # pages 12--14
    # The \fixedwidth{} tokens (TKFWD1, TKFWB1) legitimately carry verbatim
    # double hyphens — the substitution exemption is the feature under
    # test elsewhere. Everything outside them must still convert.
    outside_fixedwidth = (decl_text
                          .replace("TKFWD1_log--file", "TKFWD1_log~~file")
                          .replace("TKFWB1_lead--x.pdf", "TKFWB1_lead~~x.pdf")
                          .replace("TKBT1_tick--y.pdf", "TKBT1_tick~~y.pdf"))
    assert " -- " not in outside_fixedwidth and "--" not in outside_fixedwidth


def test_dashes_adjacent_to_quotes(decl_text):
    # Em dash inside a double-quoted span, flush against smart quotes.
    assert "“That schedule—the one we signed—is" in decl_text
    # Em dash immediately after a closing double quote.
    assert "“unworkable”—her word" in decl_text


def test_no_spaced_dashes_in_clean_source_output(decl_text):
    """The house style's compliance surface is the artifact itself."""
    assert " — " not in decl_text, "spaced em dash in output"
    assert " – " not in decl_text, "spaced en dash in output"
    assert " --- " not in decl_text and " -- " not in decl_text


# ---------------------------------------------------------------------------
# Smart quotes, apostrophes, section symbols
# ---------------------------------------------------------------------------

def test_nested_quotes_and_quote_after_comma(decl_text):
    # Single quotes nested inside doubles; closing single after a comma.
    assert "‘final,’ period.”" in decl_text
    # The \fixedwidth{} token (TKFWD1) legitimately keeps its verbatim
    # straight quotes and apostrophe; everything else must be smart.
    outside_fixedwidth = decl_text.replace('TKFWD1_log--file\'s_"raw".pdf', "TKFWD1")
    assert '"' not in outside_fixedwidth, "straight double quote survived"


def test_possessives_and_plural_possessives(decl_text):
    assert "Ms. Roe’s counsel" in decl_text
    assert "Joneses’ driveway" in decl_text
    assert "witnesses’ statements" in decl_text


def test_possessive_after_abbreviation_period(decl_text):
    assert "C.E.O.’s calendar" in decl_text


def test_section_and_pilcrow_symbols_pass_through(decl_text):
    assert "§ 2030.300" in decl_text
    assert "¶ 4" in decl_text


# ---------------------------------------------------------------------------
# Heading auto-numbering: nesting and restarts
# ---------------------------------------------------------------------------

HEADING_SEQUENCE = [
    "I. INTRODUCTION",
    "II. FACTUAL BACKGROUND",
    "A. The Records Requests",
    "1. The First Email",
    "2. The Second Email",
    "B. The Meet-and-Confer Process",
    "1. Early Calls",          # level-3 counter restarts under B.
    "III. ARGUMENT",
    "A. Legal Standard",       # level-2 counter restarts under III.
    "B. Application",
]


def test_heading_numbering_nesting_and_restarts(decl_text):
    pos = 0
    for needle in HEADING_SEQUENCE:
        idx = decl_text.find(needle, pos)
        assert idx >= 0, f"heading {needle!r} missing or out of order"
        pos = idx + len(needle)


def test_hand_numbered_heading_stacks(built):
    """Promise 3: hand-typed numerals stack on the automatic ones rather
    than replacing them — the drift the auto-numbering rule exists to
    surface."""
    text = scenario.pdf_text(built / "out" / "negative_control" / CONTROL)
    assert "I. I. HAND NUMBERED HEADING" in text


# ---------------------------------------------------------------------------
# Footnotes: numbering, same-page placement, page-bottom rendering
# ---------------------------------------------------------------------------

# (marker word as extracted with its superscript number, note sentinel)
FOOTNOTES = [
    ("here.1", "TKFN1"),
    ("period.2", "TKFN2"),
    ("size.3", "TKFN3"),
]


def test_footnote_markers_numbered_in_document_order(decl_text):
    pos = 0
    for marker, _ in FOOTNOTES:
        idx = decl_text.find(marker, pos)
        assert idx >= 0, f"superscript marker {marker!r} missing/out of order"
        pos = idx + len(marker)


@pytest.mark.parametrize("marker,note", FOOTNOTES)
def test_footnote_note_lands_on_marker_page(decl_pages, marker, note):
    page = _page_with(decl_pages, marker)
    assert note in page, f"note {note} not on the page carrying {marker!r}"


@pytest.mark.parametrize("marker,note", FOOTNOTES)
def test_footnote_note_renders_below_its_marker(decl_pages, marker, note):
    """pdftotext -layout emits top-to-bottom, so a page-bottom note must
    appear after the body line that references it."""
    page = _page_with(decl_pages, marker)
    assert page.index(note) > page.index(marker)


def test_footnotes_render_exactly_once(decl_text):
    for _, note in FOOTNOTES:
        assert decl_text.count(note) == 1, f"{note} duplicated or dropped"


def test_footnote_reservation_never_orphans_a_marker(decl_pages):
    """The paragraph carrying footnote 1 starts on page 1 but its marker
    line, forced down by the page-bottom reservation, must travel to page
    2 together with its note (fixture geometry pins this: the marker
    would otherwise land on page 1's reserved bottom lines)."""
    assert "testify competently to the" in decl_pages[0]
    assert "here.1" in decl_pages[1] and "TKFN1" in decl_pages[1]
    assert "TKFN1" not in decl_pages[0]


def test_undefined_footnote_surfaces_visibly(built):
    text = scenario.pdf_text(built / "out" / "negative_control" / CONTROL)
    assert "[^ghost]" in text


# ---------------------------------------------------------------------------
# \declsignblock: unsigned and signed variants, keep-on-one-page
# ---------------------------------------------------------------------------

def test_declsignblock_unsigned_renders_fill_in_block(decl_pages):
    year = datetime.date.today().year
    page = _page_with(
        decl_pages,
        f"Executed this _____ day of _________________, {year}, "
        "at Springfield, California.")
    assert "____________________________________" in page  # signature rule
    assert "JANE ROE" in page
    assert "Declarant, In Pro Se" in page  # third-arg role override
    # Keep-group: the signature never lands on a page without substantive
    # body text — the perjury clause travels with it.
    assert "penalty of perjury" in page


def _write_minimal_decl(path: Path, n_paragraphs: int) -> None:
    fm = "\n".join([
        "---",
        'notreal: "test-generated sweep source"',
        'filer_name: "Jane Roe"',
        "filer_address_lines:",
        '  - "123 Main Street"',
        '  - "Springfield, CA 90000"',
        'filer_phone: "(555) 555-0100"',
        'filer_email: "jane.roe@example.com"',
        'filer_role: "Respondent, In Pro Per"',
        'court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"',
        'court_county: "COUNTY OF EXAMPLE"',
        'petitioner: "JOHN SMITH"',
        'respondent: "JANE ROE"',
        'case_number: "24CV00000"',
        'paper_title: "DECLARATION OF JANE ROE"',
        "---",
    ])
    para = ("This filler paragraph exists only to push the signature "
            "block toward a page boundary; its length is two rendered "
            "lines on the grid.")
    body = "\n\n".join(f"{i + 1}. {para}" for i in range(n_paragraphs))
    tail = ("\n\nI declare under penalty of perjury under the laws of the "
            "State of California that the foregoing is true and correct."
            "\n\n\\declsignblock{JANE ROE}{Springfield, California}"
            "{Sweep Declarant}\n")
    path.write_text(fm + "\n\n" + body + tail, encoding="utf-8")


@pytest.mark.parametrize("n_paragraphs", [8, 9, 10, 11, 12, 13])
def test_declsignblock_never_splits_across_pages(tmp_path, n_paragraphs):
    """Sweep the signature block across the page boundary: for every
    filler count, the Executed line, signature rule, name, and role must
    share one page (and never sit on a body-free page)."""
    src = tmp_path / f"sweep_{n_paragraphs}.md"
    out = tmp_path / f"sweep_{n_paragraphs}.pdf"
    _write_minimal_decl(src, n_paragraphs)
    proc = subprocess.run(
        [sys.executable, str(MD_PLEADING), str(src), str(out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    pages = scenario.pdf_text(out).split("\f")
    sig_pages = [p for p in pages if "Executed this" in p]
    assert len(sig_pages) == 1
    page = sig_pages[0]
    assert "____________________________________" in page
    assert "JANE ROE" in page
    assert "Sweep Declarant" in page
    assert "penalty of perjury" in page, (
        "signature block stranded on a page with no substantive text")


def test_declsignblock_signed_fills_date_and_signature(built, tmp_path):
    src = built / "src" / "Declaration of Jane Roe.md"
    out = tmp_path / "signed.pdf"
    proc = subprocess.run(
        [sys.executable, str(MD_PLEADING), str(src), str(out),
         "--sign", "Jane Roe", "--date", "2026-03-16"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    text = scenario.pdf_text(out)
    assert ("Executed this 16th day of March, 2026, at Springfield, "
            "California.") in text
    assert "_____" not in text, "fill-in blanks survived a signed build"
    # The cursive signature is real: the signature font is embedded.
    from pypdf import PdfReader
    fonts = set()
    for page in PdfReader(str(out)).pages:
        for f in (page.get("/Resources", {}).get("/Font", {}) or {}).values():
            fonts.add(str(f.get_object().get("/BaseFont", "")))
    assert any("DancingScript" in f for f in fonts), fonts


# ---------------------------------------------------------------------------
# \posblock proof-of-service expansion
# ---------------------------------------------------------------------------

POS_DOCS = [
    "Declaration of Jane Roe in Support of Motion to Compel",
    "[Proposed] Order Granting Motion to Compel",
    "Separate Statement re Requests for Production",
]
POS_RECIPIENTS = [
    ("Sally Sattler", "sally@examplefirm.com"),
    ("Marcus Chen", "marcus@examplefirm.com"),
    ("Dana Whitfield", "dana@example.org"),
]


@pytest.fixture(scope="module")
def pos_email_text(built):
    return scenario.pdf_text(built / "out" / "typography" / POS_EMAIL)


def test_posblock_electronic_expansion(pos_email_text):
    # Flatten whitespace: pdftotext hard-wraps lines mid-phrase.
    flat = _flat_body(pos_email_text)
    assert "I, Jane Roe, declare as follows:" in flat
    assert ("1. I am over the age of 18 years and not a party to the "
            "within action.") in flat
    assert ("My business or residence address is 123 Main Street, "
            "Springfield, CA 90000.") in flat
    assert "2. My electronic service address is jane.roe@example.com." in flat
    # Omitted date renders as a fill-in blank.
    assert ("3. On _______________, I electronically served the following "
            "documents:") in flat
    for doc in POS_DOCS:
        assert doc in flat, f"served document missing: {doc}"
    assert "electronic transmission to the email addresses" in flat
    for name, email in POS_RECIPIENTS:
        assert name in flat and email in flat
    assert "penalty of perjury" in flat
    assert "Executed this _____ day of" in flat  # expansion's declsignblock
    assert "JANE ROE" in flat  # server name, uppercased


def test_posblock_mail_expansion(built):
    flat = _flat_body(
        scenario.pdf_text(built / "out" / "typography" / POS_MAIL))
    # Supplied date is used; numbering shifts (no electronic-address para).
    assert "2. On August 1, 2026, I served the following documents:" in flat
    assert "by U.S. Mail at the addresses indicated below" in flat
    assert "electronic service address" not in flat
    assert "1101 College Avenue, Suite 200, Example City, CA 90000" in flat
    assert "2200 Oak Street, Example City, CA 90000" in flat


def test_posblock_output_obeys_the_dash_rule(pos_email_text):
    assert " — " not in pos_email_text


# ---------------------------------------------------------------------------
# Pagination, footer titles, 28-line grid on multi-page documents
# ---------------------------------------------------------------------------

FOOTER_NUM_RE = re.compile(r"^\s{20,}(\d+)\s*$", re.M)


def test_pages_numbered_consecutively_from_one(decl_pages):
    pages = [p for p in decl_pages if p.strip()]
    assert len(pages) >= 4, "fixture must span 4+ pages to stress pagination"
    for i, page in enumerate(pages, start=1):
        nums = [int(m) for m in FOOTER_NUM_RE.findall(page)]
        assert i in nums, f"footer page number {i} missing (found {nums})"


def test_footer_title_on_every_page(decl_pages):
    title = "DECLARATION OF JANE ROE IN SUPPORT OF MOTION TO COMPEL"
    for i, page in enumerate(pages := [p for p in decl_pages if p.strip()],
                             start=1):
        assert title in page, f"footer title missing on page {i}"
    # Pages 2+ have no caption, so the hit there can only be the footer.
    assert len(pages) >= 2


def test_footer_ignores_undocumented_short_title(built):
    """The footer always carries paper_title (spec: pleading_markdown_spec.md
    schema, generator.md promise 1). `short_title` is a JC cover-form key and
    must never leak into the footer."""
    text = scenario.pdf_text(built / "out" / "negative_control" / SHORT_PROBE)
    assert "TKSHORTPROBE" not in text


def test_all_pages_carry_line_numbers_1_to_28(decl_pages):
    for i, page in enumerate([p for p in decl_pages if p.strip()], start=1):
        nums = {int(m.group(1))
                for m in re.finditer(r"^\s{0,3}(\d{1,2})\b", page, re.M)}
        present = len(nums & set(range(1, 29)))
        assert present >= 24, (
            f"page {i}: only {present}/28 margin line numbers detected")


def test_body_baselines_align_to_grid_on_later_pages(decl_pdf):
    """Every body text op on pages 2+ must sit on one of the 28 numbered
    baselines (superscript footnote markers are the only sanctioned
    exception — they are deliberately raised)."""
    from pypdf import PdfReader
    reader = PdfReader(str(decl_pdf))
    for page_no, page in enumerate(reader.pages[1:], start=2):
        items = []

        def visit(text, cm, tm, font_dict, font_size, _acc=items):
            if text.strip():
                _acc.append((tm[4], tm[5], text.strip()))

        page.extract_text(visitor_text=visit)
        line_ys = sorted({y for x, y, t in items if x < 80 and t.isdigit()})
        assert len(line_ys) == 28, f"page {page_no}: {len(line_ys)} line ys"
        # The margin band above the top numbered line is exempt: the
        # NOTREAL banner is stamped there, off-grid by design.
        body = [(x, y, t) for x, y, t in items
                if x > 95 and 70 < y <= max(line_ys) + 0.5]
        assert body, f"page {page_no}: no body text found"
        off_grid = [
            (x, y, t) for x, y, t in body
            if min(abs(y - ly) for ly in line_ys) > 0.5
        ]
        # Sanctioned exceptions: raised superscript digits (footnote
        # refs), and DocuSeal field tags -- white, invisible metadata
        # deliberately placed in the inter-line gap (ADR-0027).
        bad = [
            it for it in off_grid
            if not (it[2].isdigit() and len(it[2]) <= 2)
            and not it[2].startswith("{{")
        ]
        assert not bad, f"page {page_no}: text off the 28-line grid: {bad[:5]}"


# ---------------------------------------------------------------------------
# Block quotes
# ---------------------------------------------------------------------------

def _lines_by_baseline(pdf_path):
    """Map every page's text ops to {y: (min_x, joined_text)}, so a wrapped
    block's left edge can be measured against the body margin."""
    from pypdf import PdfReader
    pages = []
    for page in PdfReader(str(pdf_path)).pages:
        items = []

        def visit(text, cm, tm, font_dict, font_size, _acc=items):
            if text.strip():
                _acc.append((round(tm[5], 1), tm[4], text))

        page.extract_text(visitor_text=visit)
        lines = {}
        for y, x, text in items:
            if x < 95:          # margin line-number column
                continue
            min_x, chunks = lines.get(y, (x, []))
            lines[y] = (min(min_x, x), chunks + [(x, text)])
        # Words arrive as separate ops; join on single spaces so phrase
        # matches and length measurements mean what they look like.
        pages.append({
            y: (min_x,
                " ".join("".join(t for _, t in sorted(chunks)).split()))
            for y, (min_x, chunks) in lines.items()
        })
    return pages


def test_block_quote_renders_indented_without_quote_marks(decl_pdf, decl_text):
    """Consecutive `>` lines merge into one block indented 36 pt from the
    body margin, with no bullet, no `>` glyph, and no quotation marks added
    (spec: pleading/pleading_markdown_spec.md, "Block quotes")."""
    flat = _flat_body(decl_text)
    for tk in ("TKBQ1", "TKBQ2", "TKBQ3"):
        assert tk in flat, f"{tk} missing — block quote truncated"
    assert ">" not in decl_text, "raw '>' marker leaked into the artifact"

    # The generator must not wrap the extract in quotation marks.
    assert '“On receipt of a response' not in flat
    assert 'without merit or too general (TKBQ2).”' not in flat

    quote_x, body_x = [], []
    for lines in _lines_by_baseline(decl_pdf):
        for _, (min_x, text) in lines.items():
            if "On receipt of a response" in text or "TKBQ2" in text:
                quote_x.append(min_x)
            if "TKBQ3" in text or "statute's text governs" in text:
                body_x.append(min_x)
    assert quote_x, "no block-quote lines located in the artifact"
    assert body_x, "no adjacent body lines located in the artifact"

    indent = min(quote_x) - min(body_x)
    assert 30 <= indent <= 42, (
        f"block quote indent was {indent:.1f} pt, expected ~36 "
        f"(quote left edge {min(quote_x):.1f}, body {min(body_x):.1f})")


def test_block_quote_merges_consecutive_source_lines(decl_pdf, built):
    """Consecutive `>` lines are one block, not one block per line. The
    fixture deliberately breaks the extract at ~28 characters; if the
    renderer honored those breaks the rendered lines would be just as short,
    so a rendered line materially longer than the longest source line is the
    falsifiable proof that the block was merged and rewrapped."""
    src = (built / "src" / "Declaration of Jane Roe.md").read_text()
    quoted = [ln[1:].strip() for ln in src.splitlines() if ln.startswith(">")]
    assert quoted, "fixture lost its block quote"
    longest_source = max(len(ln) for ln in quoted)

    rendered = []
    for lines in _lines_by_baseline(decl_pdf):
        for _, (min_x, text) in lines.items():
            if min_x > 130 and any(ln and ln in text for ln in quoted):
                rendered.append(len(text))
    assert rendered, "no block-quote lines located in the artifact"
    assert max(rendered) > longest_source + 10, (
        f"longest rendered block-quote line was {max(rendered)} chars vs "
        f"{longest_source} in the source — the block was not rewrapped")


# ---------------------------------------------------------------------------
# Negative control: the alarms above can actually fire
# ---------------------------------------------------------------------------

def test_spaced_em_dashes_are_normalized_and_warned(built, tmp_path):
    """The em-dash rule is enforced, not suggested: a source that
    writes ' --- ' still builds, but the ARTIFACT carries the glued
    glyph — the house style no longer depends on the author. The
    stderr warning still fires so the source itself gets fixed.
    Spaced EN dashes stay literal (ranges are the author's problem),
    keeping this module's clean-output assertions falsifiable."""
    proc_text = scenario.pdf_text(built / "out" / "negative_control" / CONTROL)
    assert " — " not in proc_text, "spaced em dash escaped enforcement"
    assert "—" in proc_text, "em dash lost entirely"
    assert " – " in proc_text, "spaced en dash control did not fire"
    assert "TKNEG1" in proc_text
    src = built / "src" / "Spaced Dash Control.md"
    proc = subprocess.run(
        [sys.executable, str(MD_PLEADING), str(src), str(tmp_path / "c.pdf")],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]  # warning, not failure
    assert "WARNING: spaced dash" in proc.stderr


def test_clean_source_builds_without_spaced_dash_warning(built, tmp_path):
    """The warning must not cry wolf: a style-clean source builds silently."""
    src = built / "src" / "Declaration of Jane Roe.md"
    proc = subprocess.run(
        [sys.executable, str(MD_PLEADING), str(src), str(tmp_path / "d.pdf")],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    assert "spaced dash" not in proc.stderr


# ---------------------------------------------------------------------------
# AI-judged: layout properties only judgment can see
# ---------------------------------------------------------------------------

@pytest.mark.ai
def test_ai_footnote_page_layout(decl_pdf, tmp_path):
    # Pages 2 and 3 carry footnotes at the bottom of a full body.
    pages = scenario.rasterize(decl_pdf, tmp_path / "fn", dpi=100,
                               first=2, last=3)
    j = judge(
        task=("A Markdown-to-pleading generator rendered a multi-page "
              "declaration with footnotes onto California 28-line pleading "
              "paper; these are two interior pages that each carry one "
              "footnote."),
        rubric=(
            "10/10: each footnote sits at the bottom of the page below a "
            "short horizontal separator rule; the note text is visibly "
            "smaller than the body; the in-text reference is a raised "
            "superscript number matching the note's number; the note stays "
            "above the footer rule / page number without touching them; "
            "body text above remains aligned to the numbered lines."),
        hard_failures=[
            "a footnote overlaps or collides with the footer rule, page "
            "number, or footer title",
            "a footnote number in the note area has no matching "
            "superscript reference on the same page",
            "footnote text at full body size or floating mid-page",
        ],
        files=pages,
        threshold=7,
    )
    assert_judgment(j, "footnote page-bottom layout")


@pytest.mark.ai
def test_ai_signed_signature_block(built, tmp_path):
    src = built / "src" / "Declaration of Jane Roe.md"
    out = tmp_path / "signed.pdf"
    subprocess.run(
        [sys.executable, str(MD_PLEADING), str(src), str(out),
         "--sign", "Jane Roe", "--date", "2026-03-16"],
        capture_output=True, text=True, check=True)
    pages = scenario.rasterize(out, tmp_path / "sig", dpi=100, first=5)
    j = judge(
        task=("The generator rendered the final page of a declaration "
              "with --sign 'Jane Roe' --date 2026-03-16: the signature "
              "block should read as an executed declaration."),
        rubric=(
            "10/10: the execution line reads 'Executed this 16th day of "
            "March, 2026, at Springfield, California.' with no leftover "
            "blank underscores; a cursive signature sits on a signature "
            "line; the printed name JANE ROE and role appear beneath; the "
            "whole block sits on one page with body text above it."),
        hard_failures=[
            "fill-in blanks (underscore runs) remain anywhere in the "
            "signature block",
            "the cursive signature is missing or not on the signature line",
            "the signature block is split across pages or sits on an "
            "otherwise-empty page",
        ],
        files=pages,
        threshold=7,
    )
    assert_judgment(j, "signed declaration signature block")


# ---------------------------------------------------------------------------
# Inline \fixedwidth{...}: verbatim monospace, exempt from substitutions
# ---------------------------------------------------------------------------


def test_inline_fixedwidth_content_is_verbatim(decl_text):
    """The token inside \\fixedwidth{} keeps its double hyphen and straight
    quotes and apostrophe -- no em/en dash or smart-quote substitution --
    while the em dash outside the macro on the same line still converts."""
    body = _flat_body(decl_text)
    assert 'TKFWD1_log--file\'s_"raw".pdf' in body
    assert "plain—TKFWD2—in" in body


def test_inline_fixedwidth_macro_not_rendered_literally(decl_text):
    """Neither the macro name nor its braces reach the output."""
    assert "fixedwidth" not in decl_text
    assert "TKFWD1" in decl_text  # the content does


def test_inline_fixedwidth_renders_in_courier(decl_pdf):
    """The fixedwidth token is set in Courier; the surrounding prose is not."""
    from pypdf import PdfReader
    fonts_by_text: list[tuple[str, str]] = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip() and font_dict is not None:
            fonts_by_text.append((text, str(font_dict.get("/BaseFont", ""))))

    for page in PdfReader(decl_pdf).pages:
        page.extract_text(visitor_text=visit)
    hits = [f for t, f in fonts_by_text if "TKFWD1" in t]
    assert hits, "fixedwidth token not found in text runs"
    assert all("Courier" in f for f in hits), hits
    prose = [f for t, f in fonts_by_text if "alteration" in t]
    assert prose and all("Courier" not in f for f in prose), prose


def test_bullet_lead_word_keeps_fixedwidth(decl_text, decl_pdf):
    """The first word of a bullet keeps its \\fixedwidth styling: verbatim
    double hyphen in the text, Courier in the font runs (the bullet-prefix
    merge used to drop every flag but bold/italic)."""
    assert "TKFWB1_lead--x.pdf" in decl_text
    from pypdf import PdfReader
    fonts = []
    def visit(text, cm, tm, font_dict, font_size):
        if text.strip() and font_dict is not None:
            fonts.append((text, str(font_dict.get("/BaseFont", ""))))
    for page in PdfReader(decl_pdf).pages:
        page.extract_text(visitor_text=visit)
    hits = [f for t, f in fonts if "TKFWB1" in t]
    assert hits and all("Courier" in f for f in hits), hits


def test_backtick_is_fixedwidth_synonym(decl_text, decl_pdf):
    """Backticked spans render as verbatim monospace, identically to
    \\fixedwidth: content verbatim (double hyphen survives), no backtick
    glyphs in the artifact, Courier in the font runs."""
    assert "TKBT1_tick--y.pdf" in decl_text
    assert "`" not in decl_text, "backtick glyph leaked into the artifact"
    from pypdf import PdfReader
    fonts = []
    def visit(text, cm, tm, font_dict, font_size):
        if text.strip() and font_dict is not None:
            fonts.append((text, str(font_dict.get("/BaseFont", ""))))
    for page in PdfReader(decl_pdf).pages:
        page.extract_text(visitor_text=visit)
    hits = [f for t, f in fonts if "TKBT1" in t]
    assert hits and all("Courier" in f for f in hits), hits


def test_filelink_renders_display_text_and_gotor_annotation(decl_text, decl_pdf):
    """\\filelink{path}{text} shows the display text (mono) and carries a
    /GoToR link annotation whose file spec is the RELATIVE path, so the
    link resolves against the PDF's own location."""
    body = _flat_body(decl_text)
    assert "TKFL1 linked copy" in body
    assert "records/TKFL1_target.pdf" not in body  # path not rendered
    assert "here—TKFL2—for" in body  # em dash still enforced outside
    from pypdf import PdfReader
    targets = []
    for page in PdfReader(decl_pdf).pages:
        for a in (page.get("/Annots") or []):
            o = a.get_object()
            act = o.get("/A")
            if act and act.get("/S") == "/GoToR":
                targets.append(str(act.get("/F")))
    assert "records/TKFL1_target.pdf" in targets, targets
