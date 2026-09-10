"""Adversarial form-filler tests (specs/pleading/forms/README.md).

Principles: assert against the OUTPUT ARTIFACT (the text drawn on the
page, where it was drawn, page counts), never against the engine's
self-reported success; plant unique sentinels so truncation anywhere is
detected; include negative controls proving the alarms can actually
fire. A fill is flattened ink (ADR-0046), so every probe reads the page.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import form_fill  # noqa: E402
import probe  # noqa: E402
from probe import page_text  # noqa: E402
from pypdf import PdfReader  # noqa: E402

FORMS = form_fill.list_forms()

RICH_META = {
    "filer_name": "Alexandra Featherstone-Ramachandran, Esq.",
    "filer_bar_number": "234567",
    "filer_address_lines": [
        "Featherstone Litigation Group LLP",
        "12345 South Grand Boulevard, Suite 2400",
        "San Buenaventura, CA 93001",
    ],
    "filer_phone": "(805) 555-0142",
    "filer_fax": "(805) 555-0143",
    "filer_email": "alexandra.featherstone@featherstonelitigation.example.com",
    "filer_role": "Attorney for Respondent JANE ROE",
    "court_county": "COUNTY OF SAN BERNARDINO",
    "court_street_address": "247 West Third Street",
    "court_mailing_address": "247 West Third Street",
    "court_city_zip": "San Bernardino, CA 92415-0210",
    "court_branch": "San Bernardino District — Civil Division",
    "petitioner": "JONATHAN ALEXANDER SMITH-WORTHINGTON",
    "respondent": "JANE ELIZABETH ROE",
    "case_number": "24CV000123",
    "paper_title": "DECLARATION OF JANE ELIZABETH ROE",
}


# ---------------------------------------------------------------------------
# Own-name landing: every fillable field, in its own box, no collisions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form_id", FORMS)
def test_every_field_lands_in_its_own_box(form_id, tmp_path):
    desc = form_fill.load_descriptor(form_id)
    fields = desc.get("fields") or {}
    # Tokens must be SHORT: on dense table forms (an income/expense
    # grid packs sidewise neighbors a few points apart) a long token
    # overflows its box across the neighbor's, the two overprint, and
    # poppler drops the mangled glyphs — the token is then "absent"
    # even though the draw landed exactly where the map said. A short
    # token fits inside any real box, so what this test proves stays
    # exactly what it claims: each field draws inside its own rectangle
    # on its own page. Z{i}J is substring-safe: the index is delimited
    # on both sides, so no token contains another.
    tokens = {name: f"Z{i}J" for i, name in enumerate(fields)}
    out = tmp_path / f"{form_id}.pdf"
    form_fill.fill(form_id, out, meta={}, data=dict(tokens))

    problems = []
    for name, spec in fields.items():
        token = tokens[name]
        try:
            drawn = probe.field_text(out, form_id, name)
        except KeyError as exc:
            problems.append(str(exc))
            continue
        if token not in drawn.split():
            problems.append(f"{name}: expected own token in its box, found {drawn!r}")
    assert not problems, f"{form_id}: {problems}"


@pytest.mark.parametrize("form_id", FORMS)
def test_no_two_fields_share_a_widget(form_id):
    desc = form_fill.load_descriptor(form_id)
    seen: dict[str, str] = {}
    for name, spec in (desc.get("fields") or {}).items():
        if not spec.get("map"):
            continue
        if spec["map"] in seen:
            pytest.fail(f"{form_id}: '{name}' and '{seen[spec['map']]}' both map {spec['map']}")
        seen[spec["map"]] = name


# ---------------------------------------------------------------------------
# Mandatory blanks, registry-wide (and the sweep must not be vacuous)
# ---------------------------------------------------------------------------

BLANK_RE = re.compile(r"leave[- ]?blank|left blank|stays? blank|blank for", re.I)


def _blank_marked(desc):
    return [n for n, s in (desc.get("fields") or {}).items()
            if BLANK_RE.search(str(s.get("doc", "")))]


def test_blank_sweep_is_not_vacuous():
    total = sum(len(_blank_marked(form_fill.load_descriptor(f))) for f in FORMS)
    assert total >= 8, (
        f"only {total} LEAVE-BLANK fields marked across the registry — "
        "either descriptors lost their blank markers or this sweep is dead")


@pytest.mark.parametrize("form_id", FORMS)
def test_mandatory_blanks_survive_a_rich_fill(form_id, tmp_path):
    """The richest plausible caption metadata must never leak into
    signature/date/court-owned fields on ANY form."""
    desc = form_fill.load_descriptor(form_id)
    out = tmp_path / f"{form_id}.pdf"
    form_fill.fill(form_id, out, meta=dict(RICH_META))
    leaks = []
    for name in _blank_marked(desc):
        v = probe.field_text(out, form_id, name)
        if v.strip():
            leaks.append(f"{name} = {v!r}")
    assert not leaks, f"{form_id}: machine filled human/court-owned fields: {leaks}"


# ---------------------------------------------------------------------------
# Flattening and stress
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form_id", FORMS)
def test_output_carries_no_form_layer(form_id, tmp_path):
    """The blank's LiveCycle/XFA packet, its widgets, and its form
    dictionary are all gone from a fill (ADR-0046): what remains renders
    the same in every viewer because nothing is left for a viewer to
    interpret."""
    out = tmp_path / f"{form_id}.pdf"
    form_fill.fill(form_id, out, meta=dict(RICH_META))
    assert probe.has_no_form_layer(out), f"{form_id}: form machinery survived the fill"


@pytest.mark.parametrize("form_id", FORMS)
def test_long_realistic_caption_never_overflows_silently(form_id, tmp_path):
    res = form_fill.fill(form_id, tmp_path / f"{form_id}.pdf", meta=dict(RICH_META))
    bad = [w for w in res.warnings if "overflows its box" in w]
    assert not bad, f"{form_id}: unhandled overflow on realistic-long caption: {bad}"


# ---------------------------------------------------------------------------
# MC-025 chunking: sentinels end-to-end, or it didn't happen
# ---------------------------------------------------------------------------

def test_multipage_overflow_preserves_every_sentence(tmp_path):
    sentinels = [f"SENTINEL{i:04d}" for i in range(40)]
    text = " ".join(
        f"Paragraph {i}: {sentinels[i]} " + ("relevant factual detail. " * 30)
        for i in range(40))
    out = tmp_path / "big.pdf"
    res = form_fill.fill("mc030", out, meta=dict(RICH_META), data={"body": text})
    assert res.overflows
    reader = PdfReader(str(out))
    assert len(reader.pages) >= 4, "multi-page overflow did not span multiple MC-025s"
    joined = probe.all_text(out).replace("\n", " ")
    missing = [s for s in sentinels if s not in joined]
    assert not missing, f"overflow text truncated — missing sentinels: {missing[:5]}..."
    # Page N of M must be filled on multi-page attachments: the second
    # MC-025 (page 3 of the output, after MC-030's two) says "2".
    assert "2" in probe.field_text(out, "mc025", "page_number").split() or any(
        "2" in probe.text_in_rect(out, i, probe.rect_of("mc025", "page_number")[1]).split()
        for i in range(2, len(reader.pages))), "page_number not filled"


# ---------------------------------------------------------------------------
# Negative control: prove the drift alarm can actually fire
# ---------------------------------------------------------------------------

def test_negative_control_bogus_map_is_loudly_reported(tmp_path):
    bogus = form_fill.REGISTRY_DIR / "_negcontrol.yaml"
    bogus.write_text(
        "form: _negcontrol\nblank: mc040.pdf\ntechnology: overlay\n"
        "fields:\n  ghost:\n    map: NoSuchWidget999\n    doc: negative control\n"
        "agent_guide: negative control\n")
    try:
        res = form_fill.fill("_negcontrol", tmp_path / "x.pdf", meta={},
                             data={"ghost": "value"})
        # Technology-agnostic on purpose. The AcroForm path words this as
        # "not found — revision drift?" and the overlay path as "needs a
        # rect, or a map naming a widget in <blank> — form revision
        # drift?". What must hold either way is that the field is named
        # and the drift is called drift; since ADR-0037 the overlay
        # wording is the one that will survive.
        assert any("drift" in w and "ghost" in w for w in res.warnings), (
            "a field mapped to a nonexistent widget produced no drift warning — "
            "the revision alarm is decorative")
    finally:
        bogus.unlink()


# ---------------------------------------------------------------------------
# Consumer/employee notices: one SUBP-025 per recipient, or the subpoena
# is invalid (specs/pleading/forms/subp025.md)
# ---------------------------------------------------------------------------

@pytest.mark.skipif("subp025" not in FORMS, reason="subp025 descriptor not present")
class TestConsumerNotices:
    """The list is data; the emission is mechanical. Assert against the
    PDFs actually written, and prove the failure paths are loud — a
    silently skipped notice is an unserved consumer."""

    NOTICES = [
        {"consumer": "JOHN SMITH"},
        {"consumer": "MARY MAJOR", "slug": "mary_major",
         "witness": "Custodian of Records, Example Employer, Inc."},
    ]
    SHARED = {
        "requesting_party": "JANE ELIZABETH ROE, Respondent",
        "production_date": "September 15, 2026",
        "witness": "Custodian of Records, Example Bank, N.A.",
    }

    def _meta(self, notices=None):
        meta = dict(RICH_META)
        meta["forms"] = {"subp025": dict(self.SHARED)}
        meta["consumer_notices"] = self.NOTICES if notices is None else notices
        return meta

    def _emit(self, tmp_path, notices=None):
        import md_pleading
        return md_pleading.emit_consumer_notices(
            self._meta(notices), tmp_path / "Subpoena to Example Bank.pdf")

    def test_one_notice_per_recipient_named_for_that_recipient(self, tmp_path):
        paths = self._emit(tmp_path)
        assert [p.name for p in paths] == [
            "Subpoena to Example Bank.subp025.john_smith.pdf",
            "Subpoena to Example Bank.subp025.mary_major.pdf",
        ]
        assert all(p.exists() and p.stat().st_size > 1000 for p in paths)

    # SUBP-025 is overlay-filled and flattened (ADR-0037), so the served
    # copy has no widgets to read back; these assertions look at the
    # page text a viewer would show, which is the only thing that matters.

    def test_each_notice_addresses_only_its_own_consumer(self, tmp_path):
        smith, major = self._emit(tmp_path)
        for path, mine, theirs in ((smith, "JOHN SMITH", "MARY MAJOR"),
                                   (major, "MARY MAJOR", "JOHN SMITH")):
            p1 = page_text(path, 1)
            assert mine in p1, f"{path.name}: TO (name) missing {mine!r}"
            # The other recipient's name must appear nowhere in the file:
            # notices are served separately and disclose each other's
            # subjects otherwise.
            assert theirs not in p1 + page_text(path, 2)

    def test_shared_block_fills_and_the_entry_overrides_it(self, tmp_path):
        smith, major = self._emit(tmp_path)
        smith_p1 = page_text(smith, 1)
        assert "JANE ELIZABETH ROE, Respondent" in smith_p1
        assert "September 15, 2026" in smith_p1
        assert "Example Bank" in smith_p1
        major_p1 = page_text(major, 1)
        assert "Example Employer" in major_p1, "entry did not override witness"
        assert "Example Bank" not in major_p1

    def test_both_notices_carry_the_caption_on_both_pages(self, tmp_path):
        for path in self._emit(tmp_path):
            for page_no in (1, 2):
                text = page_text(path, page_no)
                assert RICH_META["case_number"] in text, (
                    f"{path.name}: case number missing from page {page_no}'s caption")
                assert RICH_META["petitioner"] in text

    def test_notices_leave_the_recipients_half_of_the_form_blank(self, tmp_path):
        """Objection block and both proofs of service belong to other
        people; nothing in the metadata may leak into them. Page 2 is
        entirely theirs but for the caption echo, so no notice value may
        appear on it; and the objection half of page 1 has no fields we
        fill, so the notice values appear on page 1 exactly once each."""
        for path in self._emit(tmp_path):
            p1, p2 = page_text(path, 1), page_text(path, 2)
            for value in (self.SHARED["requesting_party"], self.SHARED["production_date"],
                          RICH_META["filer_name"]):
                assert value not in p2, f"{path.name}: {value!r} leaked onto page 2"
            for value in (self.SHARED["requesting_party"], self.SHARED["production_date"]):
                assert p1.count(value) == 1, f"{path.name}: {value!r} appears {p1.count(value)}x on page 1"
            # The filer's name is ours twice on page 1 — the attorney
            # block and the (TYPE OR PRINT NAME) line under the notice
            # signature — and nowhere else.
            assert p1.count(RICH_META["filer_name"]) == 2, path.name

    def test_no_notices_declared_writes_nothing(self, tmp_path):
        import md_pleading
        assert md_pleading.emit_consumer_notices(dict(RICH_META), tmp_path / "x.pdf") == []
        assert not list(tmp_path.iterdir())

    def test_missing_consumer_fails_the_build(self, tmp_path):
        with pytest.raises(ValueError, match="consumer"):
            self._emit(tmp_path, [{"witness": "Example Bank"}])

    def test_colliding_slugs_fail_rather_than_overwrite(self, tmp_path):
        with pytest.raises(ValueError, match="slug"):
            self._emit(tmp_path, [{"consumer": "JOHN SMITH"},
                                  {"consumer": "John  Smith"}])

    def test_unknown_entry_key_fails_the_build(self, tmp_path):
        with pytest.raises(ValueError, match="unknown field"):
            self._emit(tmp_path, [{"consumer": "JOHN SMITH",
                                   "wittness": "typo'd key"}])

    def test_non_list_value_fails_the_build(self, tmp_path):
        with pytest.raises(ValueError, match="list of mappings"):
            self._emit(tmp_path, "JOHN SMITH")


def test_sbn_not_printed_twice_when_name_carries_it():
    """Real captions often put the SBN in filer_name AND set
    filer_bar_number; the attorney block must print it once."""
    import jc_common
    line1 = jc_common.attorney_block_lines({
        "filer_name": "Sally Sattler, Esq. SBN 123456",
        "filer_bar_number": "123456",
        "filer_address_lines": ["1 Main St", "Springfield, CA 90000"],
    })[0]
    assert line1.count("123456") == 1, f"bar number duplicated: {line1!r}"
    assert line1 == "Sally Sattler, Esq. (SBN 123456)", line1
