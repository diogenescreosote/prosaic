"""Exhibit + redaction/variant scenario (spec: specs/pleading/generator.md).

Fixture: a fictional Smith v. Roe matter (24CV00000) whose declaration
carries five exhibits (PDF with a page-range, image, publicly omitted,
publicly redacted, plain sealed), a ``redactions:`` name map, all three
``\\redact{}`` arities, and a ``\\highlight{}`` run. Exhibit binaries are
generated at setup with unique sentinels (see util.py).

Adversarial focus: the public/redacted variant must not contain the
sealed strings anywhere a reader — or a forensic byte scan — could find
them. Redaction here is source-level substitution, so absence is
expected; the tests prove it rather than assume it.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from tests.harness import scenario
from tests.harness.ai import assert_judgment, judge
from tests.scenarios.pleading_exhibits import util


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One matter, both variants of the motion_packet envelope built."""
    matter = util.load_matter(tmp_path_factory.mktemp("m"))
    for variant in ("sealed", "public"):
        proc = util.run_build(matter, "motion_packet", "--variant", variant, "--force")
        assert proc.returncode == 0, proc.stderr[-2000:]
    sealed = matter / "out" / "motion_packet" / "sealed" / util.DECL_PDF
    public = matter / "out" / "motion_packet" / "public" / util.DECL_PDF
    assert sealed.exists() and public.exists()
    return matter, sealed, public


def _tab_pages(pdf: Path) -> dict[str, int]:
    """Map 'EXHIBIT X' tab-sheet label -> 0-based page index."""
    out: dict[str, int] = {}
    for i, page in enumerate(util.pdf_page_texts(pdf)):
        # The fixture matter is marked `notreal:`, so every page now
        # opens with the red draft banner. Drop it before looking for
        # the tab label, which is otherwise the page's first line.
        body = "\n".join(
            ln for ln in page.split("\n") if "SCENARIO FIXTURE" not in ln
        ).lstrip("\n")
        m = re.match(r"\s*(EXHIBIT [A-Z])\b", body)
        if m and "LIST" not in body.split("\n")[0]:
            out.setdefault(m.group(1), i)
    return out


# ---------------------------------------------------------------------------
# Exhibit lettering, list page, tab sheets, attachment merging
# ---------------------------------------------------------------------------

def test_exhibit_letters_follow_list_order(built):
    _m, sealed, _p = built
    text = util.stripped_text(sealed)
    entries = [
        "Exhibit A: January 15, 2026 Email from John Smith",
        "Exhibit B: Screenshot of Text Messages Between the Parties",
        "Exhibit C: Medical Summary Prepared by Treating Physician",
        "Exhibit D: Counseling Intake Form Signed by the Parties",
        "Exhibit E: Session Notes Lodged with the Court",
    ]
    pos = -1
    for entry in entries:
        idx = text.find(entry)
        assert idx >= 0, f"exhibit list entry missing: {entry}"
        assert idx > pos, f"exhibit list out of order at: {entry}"
        pos = idx
    assert "EXHIBIT LIST" in text


def test_body_references_resolve_symbolically(built):
    """\\exhibit{} macros expand to letters assigned by YAML list order,
    re-references included; a pages spec adds an en-dashed pin cite."""
    _m, sealed, _p = built
    body = util.stripped_text(sealed)
    # smith_email is referenced twice; both must resolve to A with pin cite.
    assert body.count("Exhibit A, pp. 2–3") >= 2
    assert "Exhibit B is a true and correct screenshot" in body
    assert "attached as Exhibit C" in body
    assert "The session notes, Exhibit E," in body
    # No unexpanded macros or doubled labels.
    assert "\\exhibit" not in body
    assert "Exhibit Exhibit" not in body


def test_pages_spec_selects_only_requested_pages(built):
    _m, sealed, public = built
    for pdf in (sealed, public):
        assert util.contains_text(pdf, "SMITHMAIL-PAGE-2")
        assert util.contains_text(pdf, "SMITHMAIL-PAGE-3")
        assert not util.contains_text(pdf, "SMITHMAIL-PAGE-1"), (
            "page outside the pages: '2-3' range was attached")


def test_tab_sheets_precede_their_attachments(built):
    _m, sealed, _p = built
    tabs = _tab_pages(sealed)
    pages = util.pdf_page_texts(sealed)
    assert set(tabs) >= {"EXHIBIT A", "EXHIBIT B", "EXHIBIT C", "EXHIBIT D"}
    assert "SMITHMAIL-PAGE-2" in pages[tabs["EXHIBIT A"] + 1]
    assert "SMITHMAIL-PAGE-3" in pages[tabs["EXHIBIT A"] + 2]
    assert "MEDSUM-SENTINEL-CONFIDENTIAL" in pages[tabs["EXHIBIT C"] + 1]
    # Tab titles match the exhibit list titles.
    assert "January 15, 2026 Email from John Smith" in pages[tabs["EXHIBIT A"]]


def test_sealed_exhibit_listed_but_not_attached(built):
    """sealed: true --> letter reserved, list annotated, nothing attached."""
    _m, sealed, _p = built
    text = util.stripped_text(sealed)
    assert ("Exhibit E: Session Notes Lodged with the Court "
            "[Lodged Conditionally Under Seal]") in text
    # In the sealed packet there is no EXHIBIT E tab or attachment at all.
    assert "EXHIBIT E" not in _tab_pages(sealed)


def test_public_variant_placeholder_tabs(built):
    """public_disclosure: omitted and sealed: true both keep their letter
    and get a LODGED CONDITIONALLY UNDER SEAL tab in the public packet."""
    _m, _s, public = built
    tabs = _tab_pages(public)
    pages = util.pdf_page_texts(public)
    for label in ("EXHIBIT C", "EXHIBIT E"):
        assert label in tabs, f"placeholder tab missing for {label}"
        assert "LODGED CONDITIONALLY UNDER SEAL" in pages[tabs[label]]
    # The list page annotates both withheld exhibits in the public packet.
    assert util.stripped_text(public).count("[Lodged Conditionally Under Seal]") == 2
    # And the omitted exhibit's content truly is not in the packet.
    assert not util.contains_text(public, util.MEDSUM_TOKEN)


def test_public_redacted_companion_attached(built):
    """public_disclosure: redacted swaps in the _redacted sibling file."""
    _m, sealed, public = built
    assert util.contains_text(sealed, util.INTAKE_UNREDACTED)
    assert util.contains_text(public, util.INTAKE_REDACTED)
    assert not util.contains_text(public, util.INTAKE_UNREDACTED), (
        "unredacted exhibit content leaked into the public packet")


def test_exhibit_links_are_clickable_and_resolve_to_tab_pages(built):
    """Body 'Exhibit X' citations carry /Link annotations whose GoTo
    destinations are the matching tab-sheet pages."""
    from pypdf import PdfReader
    _m, sealed, _p = built
    reader = PdfReader(str(sealed))
    tabs = _tab_pages(sealed)
    hits = []
    for pi, page in enumerate(reader.pages):
        for ref in (page.get("/Annots") or []):
            annot = ref.get_object()
            if annot.get("/Subtype") != "/Link":
                continue
            rect = [float(v) for v in annot["/Rect"]]
            assert 0 <= rect[0] < rect[2] <= 612 and 0 <= rect[1] < rect[3] <= 792, (
                f"link rect out of page bounds: {rect}")
            dest = annot["/A"]["/D"][0].get_object()
            target = next(i for i, p in enumerate(reader.pages)
                          if p.get_object() == dest)
            label = re.match(r"\s*(EXHIBIT [A-Z])",
                             reader.pages[target].extract_text() or "")
            assert label, f"link on page {pi} does not target a tab sheet"
            hits.append(label.group(1))
    # Every attached exhibit that is cited gets at least one link;
    # re-referenced Exhibit A gets more than one.
    assert hits.count("EXHIBIT A") >= 2, hits
    assert {"EXHIBIT B", "EXHIBIT C", "EXHIBIT D"} <= set(hits), hits
    # Exhibit E is sealed out of the sealed packet: no dangling links to it.
    assert "EXHIBIT E" not in set(hits)
    for label, page_idx in tabs.items():
        assert label in hits or label == "EXHIBIT E"


# ---------------------------------------------------------------------------
# \redact{} and variants — the adversarial core
# ---------------------------------------------------------------------------

def test_sealed_build_contains_sealed_text(built):
    """Positive control: the scanner finds the sealed strings in the
    sealed build, so the absence assertions below are meaningful."""
    _m, sealed, _p = built
    assert util.contains_text(sealed, util.SEALED_NAME)
    assert util.contains_text(sealed, util.SEALED_PHRASE_TOKEN)
    # Possessive from the redaction map (typography turns ' into ').
    assert ("Wilhelmina’s" in util.stripped_text(sealed)
            or util.contains_text(sealed, util.SEALED_POSSESSIVE))


def test_public_pdf_contains_no_sealed_text_anywhere(built):
    """CRITICAL: in the public variant the sealed strings must be absent
    from extracted text, raw bytes, decoded content streams, and
    metadata — substitution, not draw-over."""
    _m, _s, public = built
    for needle in (util.SEALED_NAME, "Wilhelmina", util.SEALED_PHRASE_TOKEN,
                   "diagnosed condition in clinical detail"):
        assert not util.contains_text(public, needle), (
            f"sealed string {needle!r} present in public PDF")
    body = util.stripped_text(public)
    assert util.PUBLIC_NAME in body
    assert util.PUBLIC_PHRASE in body


def test_variant_aware_caption_values(built):
    _m, sealed, public = built
    sealed_p1 = util.pdf_page_texts(sealed)[0]
    public_p1 = util.pdf_page_texts(public)[0]
    assert "CONDITIONALLY UNDER SEAL" in sealed_p1
    assert "PUBLIC REDACTED VERSION" in public_p1
    assert "PUBLIC REDACTED VERSION" not in sealed_p1


def test_redacttext_legacy_alias_resolves_like_redact():
    """\\redacttext{sealed}{public} is the spec'd backward-compatible
    alias for \\redact (pleading_markdown_spec.md, Legacy note). It must
    substitute — the historical bug (the shorter \\redact prefix matched
    first and passed the whole macro through literally) leaked the sealed
    argument verbatim into public builds."""
    import md_pleading as mp
    body = r"before \redacttext{SEALEDTOK}{[public]} after"
    meta: dict = {}
    assert mp.substitute_redaction_macros(body, meta, "public") == \
        "before [public] after"
    assert mp.substitute_redaction_macros(body, meta, "sealed") == \
        "before SEALEDTOK after"
    # Three-argument form logs like \redact's.
    meta = {}
    out = mp.substitute_redaction_macros(
        r"\redacttext{SEALEDTOK}{[public]}{C4: justification}", meta, "public")
    assert out == "[public]"
    assert meta["_redaction_log"] == [{
        "sealed": "SEALEDTOK", "public": "[public]",
        "justification": "C4: justification"}]
    # One-argument form: same redactions-map semantics as \redact,
    # including the unknown-key error (never a silent literal).
    meta = {"redactions": {"Jane": "[the member]"}}
    assert mp.substitute_redaction_macros(
        r"\redacttext{Jane}", meta, "public") == "[the member]"
    with pytest.raises(ValueError, match="Unknown redaction literal"):
        mp.substitute_redaction_macros(r"\redacttext{Ghost}", meta, "public")


def test_redaction_sidecar_log_written(built):
    """Three-parameter \\redact writes <output>.pdf.redactions.json."""
    import json
    _m, sealed, _p = built
    sidecar = sealed.parent / (sealed.name + ".redactions.json")
    assert sidecar.exists()
    entries = json.loads(sidecar.read_text())
    assert len(entries) == 1
    e = entries[0]
    assert util.SEALED_PHRASE_TOKEN in e["sealed"]
    assert "redacted]" in e["public"]
    assert util.JUSTIFICATION_TOKEN in e["justification"]


def test_stale_sidecar_removed_on_rebuild(built, tmp_path):
    """A sealed-build sidecar left at an output path is deleted when a
    later build of the same path no longer warrants one — a stale
    sidecar next to a current PDF is a disclosure hazard."""
    import subprocess
    matter, _s, _p = built
    src = matter / "src" / util.DECL_MD
    out = tmp_path / "decl.pdf"
    cmd = [util.PYTHON, str(util.PLEADING / "md_pleading.py"),
           str(src), str(out)]
    proc = subprocess.run(cmd + ["--variant", "sealed"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    sidecar = out.parent / (out.name + ".redactions.json")
    assert sidecar.exists(), "positive control: sealed build writes sidecar"
    proc = subprocess.run(cmd + ["--variant", "public"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    assert not sidecar.exists(), (
        "stale sealed sidecar left next to the public output")


def test_public_output_directory_free_of_sealed_bytes(built):
    """CRITICAL: the whole public output directory — not just the PDF —
    must be free of sealed bytes, since it ships as "the public packet".
    In particular the .redactions.json sidecar (verbatim sealed text) is
    written only alongside the sealed variant, never the public one."""
    matter, _s, public = built
    public_dir = matter / "out" / "motion_packet" / "public"
    leaks = []
    for f in sorted(public_dir.rglob("*")):
        if f.is_file() and util.SEALED_PHRASE_TOKEN.encode() in f.read_bytes():
            leaks.append(f.name)
    assert not leaks, f"sealed text present in public output files: {leaks}"
    assert not (public.parent / (public.name + ".redactions.json")).exists(), (
        "redaction sidecar written into the public output directory")


# ---------------------------------------------------------------------------
# Cross-file exhibit references (exhibit_source)
# ---------------------------------------------------------------------------

def test_memo_resolves_letters_from_declaration_without_attaching(built):
    matter, _s, _p = built
    from pypdf import PdfReader
    memo = matter / "out" / "motion_packet" / "sealed" / util.MEMO_PDF
    text = util.stripped_text(memo)
    assert "Exhibit B corroborate" in text or "Exhibit B" in text
    assert "Exhibit A, pp. 2–3" in text
    assert "EXHIBIT LIST" not in text, "external exhibits must not re-attach"
    assert len(PdfReader(str(memo)).pages) == 1


# ---------------------------------------------------------------------------
# Negative controls: broken inputs must fail the build, loudly
# ---------------------------------------------------------------------------

@pytest.fixture()
def mini_matter(tmp_path):
    """A throwaway copy for source-mutation tests."""
    matter = util.load_matter(tmp_path)
    return matter, (matter / "src" / util.DECL_MD).read_text()


def _run_mutated(matter: Path, text: str, *args: str):
    src = matter / "src" / "mutated.md"
    src.write_text(text)
    return util.run_md_pleading(src, matter / "out_mutated.pdf", *args)


@pytest.mark.parametrize("mutate, expect", [
    (lambda t: t.replace(r"\exhibit{roe_texts}", r"\exhibit{roe_textz}"),
     "Unknown exhibit shortname"),
    (lambda t: t.replace("smith_email.pdf", "no_such_file.pdf"),
     "Exhibit file not found"),
    (lambda t: t.replace('shortname: "roe_texts"', 'shortname: "smith_email"'),
     "Duplicate exhibit shortname"),
    (lambda t: t + "\n\nAlso \\redact{Unmapped Literal} appears.\n",
     "Unknown redaction literal"),
], ids=["typo_shortname", "missing_exhibit_file", "duplicate_shortname",
        "unmapped_redact_literal"])
def test_broken_input_fails_build(mini_matter, mutate, expect):
    matter, base = mini_matter
    proc = _run_mutated(matter, mutate(base))
    assert proc.returncode != 0, "build must fail on broken input"
    assert expect in proc.stderr, proc.stderr[-1500:]
    assert not (matter / "out_mutated.pdf").exists()


def test_missing_variant_branch_fails_public_build(mini_matter):
    """Public builds fail toward substitution: a variant mapping without
    the requested branch is an error, not a silent passthrough."""
    matter, base = mini_matter
    mutated = base.replace('  public: "PUBLIC REDACTED VERSION"\n', "")
    proc = _run_mutated(matter, mutated, "--variant", "public")
    assert proc.returncode != 0
    assert "missing key 'public'" in proc.stderr


@pytest.mark.parametrize("bad_spec", ["2-9", "0", "5-3"],
                         ids=["end_past_last_page", "page_zero", "reversed_range"])
def test_out_of_range_pages_spec_fails(mini_matter, bad_spec):
    matter, base = mini_matter
    mutated = base.replace('pages: "2-3"', f'pages: "{bad_spec}"')
    proc = _run_mutated(matter, mutated)
    assert proc.returncode != 0, (
        "out-of-range pages spec built successfully (silently truncated)")
    assert "pages spec" in proc.stderr, proc.stderr[-1500:]
    assert not (matter / "out_mutated.pdf").exists()


def _with_redaction_log(base: str, sources_yaml: str) -> str:
    """Give the fixture declaration a redaction_log_sources list and a
    \\redactionlog expansion point."""
    mutated = base.replace("redactions:\n",
                           f"redaction_log_sources:\n{sources_yaml}redactions:\n")
    assert mutated != base
    return mutated + "\n\nThe following log identifies each redaction: \\redactionlog\n"


def test_redactionlog_renders_justifications_without_sealed_text(mini_matter):
    matter, base = mini_matter
    mutated = _with_redaction_log(base, '  - "Declaration of Jane Roe.md"\n')
    proc = _run_mutated(matter, mutated, "--variant", "public")
    assert proc.returncode == 0, proc.stderr[-1500:]
    text = util.stripped_text(matter / "out_mutated.pdf")
    # One entry from the listed source, one from the current file itself.
    assert util.JUSTIFICATION_TOKEN in text
    assert "Declaration Of Jane Roe" in text
    assert "\\redactionlog" not in text
    # The public log renders justifications only — never the sealed excerpt.
    assert not util.contains_text(matter / "out_mutated.pdf",
                                  util.SEALED_PHRASE_TOKEN)


def test_redactionlog_missing_source_fails_build(mini_matter):
    """A typo'd redaction_log_sources filename must fail the build, not
    silently shorten a log whose purpose is completeness before a court."""
    matter, base = mini_matter
    mutated = _with_redaction_log(base, '  - "no_such_declaration.md"\n')
    proc = _run_mutated(matter, mutated, "--variant", "sealed")
    assert proc.returncode != 0, "missing redaction_log_sources entry built anyway"
    assert "redaction_log_sources entry not found" in proc.stderr, proc.stderr[-1500:]
    assert not (matter / "out_mutated.pdf").exists()


# ---------------------------------------------------------------------------
# AI judgment (the one judged check for this scenario)
# ---------------------------------------------------------------------------

@pytest.mark.ai
def test_ai_public_packet_reads_as_proper_redacted_filing(built, tmp_path):
    _m, _s, public = built
    pages = scenario.rasterize(public, tmp_path / "pub", dpi=90)
    j = judge(
        task=("An automated generator produced the PUBLIC (redacted) "
              "variant of a declaration packet with exhibits. Some "
              "exhibits are withheld under seal and represented only by "
              "placeholder tab sheets."),
        rubric=(
            "10/10: a coherent, filing-ready public packet — pleading "
            "body with clean substituted initials instead of a child's "
            "name; an exhibit list whose lettered entries match the tab "
            "sheets; withheld exhibits clearly marked LODGED "
            "CONDITIONALLY UNDER SEAL with no leaked content behind "
            "them; attached exhibits legible and centered on Letter "
            "pages; nothing that looks like an accidental disclosure."),
        hard_failures=[
            "any visibly sealed/medical content on a page that should be withheld",
            "an exhibit letter on the list with no corresponding tab sheet",
            "unexpanded \\exhibit or \\redact macro text visible",
        ],
        files=pages,
        threshold=7,
    )
    assert_judgment(j, "public redacted packet coherence")
