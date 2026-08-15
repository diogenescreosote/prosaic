"""Local-modules overlay (ADR-0032): forms, front-matter keys, and
auto-bindings discovered from a gitignored local/ tree.

These tests build ephemeral overlays and point the seams at them; the
suite must pass identically with no local/ directory present, which is
how CI runs it.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

PLEADING = Path(__file__).resolve().parent.parent / "pleading"
sys.path.insert(0, str(PLEADING))

import form_fill  # noqa: E402
import jc_common  # noqa: E402
import md_pleading  # noqa: E402


def _write_descriptor(d: Path, form_id: str, blank: str) -> None:
    (d / f"{form_id}.yaml").write_text(textwrap.dedent(f"""\
        form: {form_id.upper()}
        blank: {blank}
        fields: []
    """))


def test_local_registry_joins_and_wins(tmp_path, monkeypatch):
    stock = tmp_path / "stock"
    local = tmp_path / "local"
    stock.mkdir()
    local.mkdir()
    _write_descriptor(stock, "zz900", "zz900.pdf")
    _write_descriptor(stock, "zz901", "zz901.pdf")
    _write_descriptor(local, "zz901", "zz901-local.pdf")  # collision: local wins
    _write_descriptor(local, "zz902", "zz902.pdf")        # local-only
    monkeypatch.setattr(form_fill, "REGISTRY_DIRS", [local, stock])
    assert form_fill.list_forms() == ["zz900", "zz901", "zz902"]
    assert form_fill.load_descriptor("zz901")["blank"] == "zz901-local.pdf"
    assert form_fill.load_descriptor("zz902")["form"] == "ZZ902"


def test_missing_descriptor_error_names_known_forms(tmp_path, monkeypatch):
    stock = tmp_path / "stock"
    stock.mkdir()
    _write_descriptor(stock, "zz900", "zz900.pdf")
    monkeypatch.setattr(form_fill, "REGISTRY_DIRS", [stock])
    try:
        form_fill.load_descriptor("nope")
    except FileNotFoundError as e:
        assert "zz900" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_blank_path_resolves_across_dirs(tmp_path, monkeypatch):
    stock = tmp_path / "stock"
    local = tmp_path / "local"
    stock.mkdir()
    local.mkdir()
    (local / "only-local.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(form_fill, "BLANKS_DIRS", [local, stock])
    assert form_fill.blank_path({"blank": "only-local.pdf"}) == local / "only-local.pdf"


def test_local_front_matter_keys_merge(tmp_path, monkeypatch):
    extra = tmp_path / "front_matter_keys.yaml"
    extra.write_text("local:\n  - zz_local_key\n")
    monkeypatch.setattr(md_pleading, "LOCAL_FRONT_MATTER_KEYS_FILE", extra)
    keys = md_pleading.recognized_front_matter_keys()
    assert "zz_local_key" in keys
    assert "paper_title" in keys  # stock schema still present


def test_recognized_keys_without_local_overlay(monkeypatch, tmp_path):
    monkeypatch.setattr(md_pleading, "LOCAL_FRONT_MATTER_KEYS_FILE",
                        tmp_path / "absent.yaml")
    assert "paper_title" in md_pleading.recognized_front_matter_keys()


def test_local_auto_bindings_load_and_merge(tmp_path):
    mod = tmp_path / "auto_bindings.py"
    mod.write_text(
        "AUTO_BINDINGS = {'zz_local': lambda m: 'ZZ ' + str(m.get('case_number', ''))}\n"
    )
    loaded = jc_common._load_local_auto_bindings(mod)
    assert set(loaded) == {"zz_local"}
    assert loaded["zz_local"]({"case_number": "26CV00123"}) == "ZZ 26CV00123"


def test_local_auto_bindings_absent_is_empty(tmp_path):
    assert jc_common._load_local_auto_bindings(tmp_path / "absent.py") == {}
