"""Adversarial form-filler tests (specs/pleading/forms/README.md).

Principles: assert against the OUTPUT ARTIFACT (widget values, page
text, page counts), never against the engine's self-reported success;
plant unique sentinels so truncation anywhere is detected; include
negative controls proving the alarms can actually fire.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))

import form_fill  # noqa: E402
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


def out_widget_values(pdf: Path) -> list[tuple[str, str]]:
    """(name, /V) tuples — a LIST, because merged attachment pages reuse
    field names and a dict silently drops all but the last page."""
    vals = []
    for _p, name, obj in form_fill.iter_widgets(PdfReader(str(pdf))):
        v = obj.get("/V")
        if v is None and obj.get("/Parent") is not None:
            v = obj["/Parent"].get_object().get("/V")
        vals.append((name, "" if v is None else str(v)))
    return vals


def page_text(pdf: Path, page_no: int) -> str:
    return subprocess.run(
        ["pdftotext", "-f", str(page_no), "-l", str(page_no), str(pdf), "-"],
        capture_output=True, text=True).stdout


# ---------------------------------------------------------------------------
# Own-name landing: every fillable field, exact widget, no collisions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form_id", FORMS)
def test_every_field_lands_in_its_mapped_widget(form_id, tmp_path):
    desc = form_fill.load_descriptor(form_id)
    fields = desc.get("fields") or {}
    # Tokens must be SHORT: on dense table forms (an income/expense
    # grid packs sidewise neighbors a few points apart) a long token
    # overflows its box across the neighbor's, the two overprint, and
    # poppler drops the mangled glyphs — the token is then "absent"
    # even though the draw landed exactly where the map said. A short
    # token fits inside any real box, so what this test proves stays
    # exactly what it claims: each field draws on its mapped page (and,
    # for acroform, in its own widget). Z{i}J is substring-safe: the
    # index is delimited on both sides, so no token contains another.
    tokens = {name: f"Z{i}J" for i, name in enumerate(fields)}
    data = dict(tokens)
    out = tmp_path / f"{form_id}.pdf"
    form_fill.fill(form_id, out, meta={}, data=data)

    vals = dict(out_widget_values(out))  # single form: names unique
    overlay_form = str(desc.get("technology") or "") == "overlay"
    problems = []
    for name, spec in fields.items():
        token = tokens[name]
        if overlay_form or spec.get("method") == "overlay":
            txt = page_text(out, int(spec.get("page", 1)))
            if token not in txt.replace("\n", " "):
                problems.append(f"{name}: overlay token absent from page {spec.get('page')}")
            continue
        mapped = spec.get("map", "")
        hit = vals.get(mapped)
        if hit is None:  # bare-name map
            hit = next((v for k, v in vals.items() if k.split(".")[-1] == mapped), None)
        if hit != token:
            problems.append(f"{name} -> {mapped}: expected own token, got {hit!r}")
    assert not problems, f"{form_id}: {problems}"


@pytest.mark.parametrize("form_id", FORMS)
def test_no_two_fields_share_a_widget(form_id):
    desc = form_fill.load_descriptor(form_id)
    seen: dict[str, str] = {}
    for name, spec in (desc.get("fields") or {}).items():
        if spec.get("method") == "overlay" or not spec.get("map"):
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
    vals = dict(out_widget_values(out))  # single form: names unique
    leaks = []
    for name in _blank_marked(desc):
        mapped = desc["fields"][name].get("map", "")
        v = vals.get(mapped)
        if v is None:
            v = next((x for k, x in vals.items() if k.split(".")[-1] == mapped), "")
        if (v or "").strip():
            leaks.append(f"{name} -> {mapped} = {v!r}")
    assert not leaks, f"{form_id}: machine filled human/court-owned fields: {leaks}"


# ---------------------------------------------------------------------------
# XFA and stress
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form_id", [f for f in FORMS
                                     if form_fill.load_descriptor(f).get("technology") == "xfa"])
def test_xfa_layer_stripped_from_output(form_id, tmp_path):
    out = tmp_path / f"{form_id}.pdf"
    form_fill.fill(form_id, out, meta=dict(RICH_META))
    root = PdfReader(str(out)).trailer["/Root"]
    assert "/AcroForm" in root and "/XFA" not in root["/AcroForm"].get_object(), (
        f"{form_id}: XFA layer survived — form will render BLANK in XFA-aware viewers")


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
    joined = " ".join(v for _n, v in out_widget_values(out)).replace("\n", " ")
    missing = [s for s in sentinels if s not in joined]
    assert not missing, f"overflow text truncated — missing sentinels: {missing[:5]}..."
    # Page N of M must be filled on multi-page attachments.
    assert any(v == "2" for _n, v in out_widget_values(out)), "page_number not filled"


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

    def test_each_notice_addresses_only_its_own_consumer(self, tmp_path):
        smith, major = self._emit(tmp_path)
        to_field = "SubTitle1[0].FillText1[0]"
        for path, mine, theirs in ((smith, "JOHN SMITH", "MARY MAJOR"),
                                   (major, "MARY MAJOR", "JOHN SMITH")):
            vals = dict(out_widget_values(path))
            addressed = [v for k, v in vals.items() if k.endswith(to_field)]
            assert addressed == [mine], f"{path.name}: TO (name) = {addressed}"
            # The other recipient's name must appear nowhere in the file:
            # notices are served separately and disclose each other's
            # subjects otherwise.
            assert theirs not in " ".join(vals.values())

    def test_shared_block_fills_and_the_entry_overrides_it(self, tmp_path):
        smith, major = self._emit(tmp_path)
        smith_vals = " | ".join(dict(out_widget_values(smith)).values())
        assert "JANE ELIZABETH ROE, Respondent" in smith_vals
        assert "September 15, 2026" in smith_vals
        assert "Example Bank" in smith_vals
        major_vals = " | ".join(dict(out_widget_values(major)).values())
        assert "Example Employer" in major_vals, "entry did not override witness"
        assert "Example Bank" not in major_vals

    def test_both_notices_carry_the_caption_on_both_pages(self, tmp_path):
        for path in self._emit(tmp_path):
            vals = out_widget_values(path)
            assert sum(1 for _n, v in vals if v == RICH_META["case_number"]) == 2, (
                f"{path.name}: case number missing from a page's caption")
            assert sum(1 for _n, v in vals if v == RICH_META["petitioner"]) == 2

    def test_notices_leave_the_recipients_half_of_the_form_blank(self, tmp_path):
        """Objection block and both proofs of service belong to other
        people; nothing in the metadata may leak into them."""
        for path in self._emit(tmp_path):
            for name, value in out_widget_values(path):
                leaf = name.split(".")[-1]
                if any(tok in name for tok in ("Sign2[0]", "Lis1[0]", "Lis2[0]",
                                               "Lis3[0]")) or name.split(".")[1] == "Page2[0]":
                    if leaf.startswith(("Party1", "Party2", "CaseNumber")):
                        continue  # page-2 caption echo is ours
                    assert not value.strip(), f"{path.name}: {name} = {value!r}"

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
