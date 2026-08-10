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
    for slug, (mine, foreign) in expected.items():
        pdf = out_dir / f"Subpoena to Example Bank.subp025.{slug}.pdf"
        vals = scenario.widget_values(pdf)
        addressed = [v for n, v in vals if n.endswith("SubTitle1[0].FillText1[0]")]
        assert addressed == [mine], f"{pdf.name}: TO (name) = {addressed}"
        assert foreign not in " ".join(v for _n, v in vals), (
            f"{pdf.name} carries the other notice's values")
        # Caption on both pages, from the same front matter as the subpoena.
        assert sum(1 for _n, v in vals if v == "24CV00000") == 2
        text = scenario.pdf_text(pdf)
        assert "NOTICE TO CONSUMER OR EMPLOYEE" in text
        assert "September 15, 2026" in text, "production date missing from the notice"


def test_notice_signature_and_service_blocks_stay_blank(built_subpoena):
    """The notice is signed and served by humans; the recipient owns the
    objection half. Nothing on either may arrive pre-filled."""
    _m, _p, out_dir = built_subpoena
    for pdf in out_dir.glob("*.subp025.*.pdf"):
        for name, value in scenario.widget_values(pdf):
            if any(tok in name for tok in ("Date1[0]", "Sign2[0]", "Sign3[0]",
                                           "Sign4[0]", "TextField6[0]",
                                           "TextField7[0]")):
                assert not value.strip(), f"{pdf.name}: {name} = {value!r}"


def test_notice_is_a_separate_document_not_part_of_the_subpoena(built_subpoena):
    """A SUBP-025 is served on the consumer, not filed inside the
    subpoena packet — it must not have been merged into the main PDF."""
    _m, _p, out_dir = built_subpoena
    text = scenario.pdf_text(out_dir / "Subpoena to Example Bank.pdf")
    assert "SUBP-010" in text, "the subpoena cover sheet is missing"
    assert "SUBP-025" not in text, "a consumer notice was merged into the subpoena"
