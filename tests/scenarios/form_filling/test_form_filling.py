"""Form-filling scenario (spec: specs/pleading/forms/README.md).

Fixture: a fictional records-subpoena matter. Operations: direct engine
fills and a real envelope build. Checks: many and independent — field
placement, mandatory blanks, overflow behavior, cover-sheet assembly,
consumer notices — deterministic first, AI visual judgment on top.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import form_fill
from tests.harness import scenario
from tests.harness.ai import assert_judgment, judge

FIXTURE = Path(__file__).parent / "matter"

def test_registry_wide_invariants():
    """Every registered form records its verified revision and a guide."""
    for form_id in form_fill.list_forms():
        d = form_fill.load_descriptor(form_id)
        assert d.get("revision"), f"{form_id}: no verified revision recorded"
        assert len(str(d.get("agent_guide") or "").strip()) > 100, (
            f"{form_id}: agent_guide missing or perfunctory")


# ---------------------------------------------------------------------------
# Consumer notices: the envelope emits one SUBP-025 per declared recipient
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built_subpoena(tmp_path_factory):
    matter = scenario.load_scenario("form_filling", tmp_path_factory.mktemp("s"))
    proc = scenario.build_envelope(matter, "subpoena_package")
    return matter, proc, matter / "out" / "subpoena_package"


def test_subpoena_envelope_build_succeeds(built_subpoena):
    _m, proc, out_dir = built_subpoena
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert (out_dir / "Subpoena to Example Bank.pdf").exists()


def test_envelope_emits_one_notice_per_declared_consumer(built_subpoena):
    _m, _p, out_dir = built_subpoena
    notices = sorted(p.name for p in out_dir.glob("*.subp025.*.pdf"))
    assert notices == [
        "Subpoena to Example Bank.subp025.john_smith.pdf",
        "Subpoena to Example Bank.subp025.mary_major.pdf",
    ], notices


def test_each_notice_names_its_own_consumer_and_carries_the_caption(built_subpoena):
    _m, _p, out_dir = built_subpoena
    # Per recipient: who it is addressed to, and a string that belongs to
    # the OTHER notice only. (JOHN SMITH is also the petitioner, so his
    # name legitimately appears in every caption; "MARY MAJOR" does not.)
    expected = {"john_smith": ("JOHN SMITH", "MARY MAJOR"),
                "mary_major": ("MARY MAJOR", "Example Bank")}
    # The envelope build stamps a banner on these (they are drafts), which
    # scales the page content, so the checks read page text rather than
    # probing rectangles.
    for slug, (mine, foreign) in expected.items():
        pdf = out_dir / f"Subpoena to Example Bank.subp025.{slug}.pdf"
        assert scenario.has_no_form_layer(pdf), f"{pdf.name}: not flattened"
        p1, p2 = scenario.page_text(pdf, 1), scenario.page_text(pdf, 2)
        assert f"TO (name): {mine}" in " ".join(p1.split()), f"{pdf.name}: TO (name) missing {mine!r}"
        assert foreign not in p1 + p2, f"{pdf.name} carries the other notice's values"
        # Caption on both pages, from the same front matter as the subpoena.
        assert "24CV00000" in p1 and "24CV00000" in p2
        assert "NOTICE TO CONSUMER OR EMPLOYEE" in p1
        assert "September 15, 2026" in p1, "production date missing from the notice"


def test_notice_signature_and_service_blocks_stay_blank(built_subpoena):
    """The notice is signed and served by humans; the recipient owns the
    objection half and page 2's two proofs of service. Nothing on either
    may arrive pre-filled: page 2 carries no notice value at all beyond
    the caption echo, and the filer's name appears on page 1 exactly
    where it is ours — the attorney block and the (TYPE OR PRINT NAME)
    line — and nowhere else."""
    _m, _p, out_dir = built_subpoena
    filer_name = "Jane Roe"  # the scenario source's filer_name
    for pdf in out_dir.glob("*.subp025.*.pdf"):
        p1, p2 = scenario.page_text(pdf, 1), scenario.page_text(pdf, 2)
        for value in (filer_name, "September 15, 2026", "Example Bank",
                      "Example Employer", "JANE ROE, Respondent"):
            assert value not in p2, f"{pdf.name}: {value!r} on the recipient's page 2"
        assert p1.count(filer_name) == 2, f"{pdf.name}: filer name count on page 1"


def test_notice_is_a_separate_document_not_part_of_the_subpoena(built_subpoena):
    """A SUBP-025 is served on the consumer, not filed inside the
    subpoena packet — it must not have been merged into the main PDF."""
    _m, _p, out_dir = built_subpoena
    text = scenario.pdf_text(out_dir / "Subpoena to Example Bank.pdf")
    assert "SUBP-010" in text, "the subpoena cover sheet is missing"
    assert "SUBP-025" not in text, "a consumer notice was merged into the subpoena"
