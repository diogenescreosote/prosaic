"""Front-matter defaults (ADR-0035): local/config.yaml < matter.yaml <
the source's own front matter."""

from __future__ import annotations

import sys
from pathlib import Path

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))

import jc_common  # noqa: E402


def test_precedence_chain(tmp_path, monkeypatch):
    box = tmp_path / "repo"
    (box / "local").mkdir(parents=True)
    (box / "local" / "config.yaml").write_text(
        "front_matter_defaults:\n"
        "  filer_eservice_address: box@example.com\n"
        "  judge: Hon. Box Default\n")
    matter = tmp_path / "matter"
    matter.mkdir()
    (matter / "matter.yaml").write_text(
        "front_matter_defaults:\n"
        "  judge: Hon. Matter Shadow\n")
    monkeypatch.setattr(jc_common, "REPO_ROOT", box)

    d = jc_common.front_matter_defaults(matter)
    assert d["filer_eservice_address"] == "box@example.com"   # box survives
    assert d["judge"] == "Hon. Matter Shadow"                 # matter shadows box

    meta = {**d, **{"judge": "Hon. Source Wins"}}             # source wins
    assert meta["judge"] == "Hon. Source Wins"
    assert jc_common.AUTO_BINDINGS["eservice_address"](meta) == "box@example.com"


def test_missing_files_contribute_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(jc_common, "REPO_ROOT", tmp_path / "nowhere")
    assert jc_common.front_matter_defaults(tmp_path / "no-matter") == {}
