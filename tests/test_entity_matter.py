"""The entity matter scaffold, pinned (ADR-0051).

An entity matter's readers mostly never run prosaic, so its shape is
its interface: the numbered sections a director learns once, the front
page that says where things stand, and the absence of litigation
directories that would make a reader wonder what was lost. These tests
pin that shape, and that `sc init` without `--type` is unchanged.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"

SECTIONS = [
    "01 Formation",
    "02 Governing Documents",
    "03 Board Minutes and Consents",
    "04 Directors and Officers",
    "05 Other Official Acts",
    "06 Tax Status",
    "07 Government Filings",
    "08 Litigation",
    "09 Finances",
    "10 Correspondence",
]
LITIGATION_ONLY = ["pleadings", "discovery", "lawyer_drafts", "unfiled"]


def init(tmp_path: Path, *extra: str) -> Path:
    dest = tmp_path / "m"
    subprocess.run(
        [sys.executable, str(SC), "init", str(dest), *extra],
        check=True,
        capture_output=True,
        text=True,
    )
    return dest


def test_entity_scaffold_has_every_section_and_no_litigation_dirs(tmp_path: Path) -> None:
    m = init(tmp_path, "--type", "entity")
    for s in SECTIONS:
        assert (m / "assets" / s).is_dir(), s
        assert (m / "assets" / s / ".gitkeep").exists(), f"{s} would vanish from git"
    for d in LITIGATION_ONLY:
        assert not (m / d).exists(), d
    assert (m / "inbox").is_dir()
    assert (m / "processed_files" / "MANIFEST.md").exists()


def test_entity_front_page_index_and_type(tmp_path: Path) -> None:
    m = init(tmp_path, "--type", "entity")
    front = (m / "START HERE.md").read_text(encoding="utf-8")
    assert "Where things stand" in front
    index = (m / "assets" / "INDEX.md").read_text(encoding="utf-8")
    for s in SECTIONS:
        assert s in front, f"front page omits {s}"
        assert f"## {s}" in index, f"INDEX omits {s}"
    cfg = yaml.safe_load((m / "matter.yaml").read_text(encoding="utf-8"))
    assert cfg["case"]["type"] == "entity"


def test_entity_contract_is_the_base_plus_the_addendum(tmp_path: Path) -> None:
    m = init(tmp_path, "--type", "entity")
    agents = (m / "AGENTS.md").read_text(encoding="utf-8")
    base = (REPO_ROOT / "templates" / "matter" / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith(base), "the shared matter contract must not be replaced"
    assert "This is an entity matter (ADR-0051)" in agents


def test_default_init_is_unchanged(tmp_path: Path) -> None:
    m = init(tmp_path)
    for d in LITIGATION_ONLY:
        assert (m / d).is_dir(), d
    assert not (m / "START HERE.md").exists()
    assert not (m / "assets" / "01 Formation").exists()
    assert "entity matter" not in (m / "AGENTS.md").read_text(encoding="utf-8")


def test_rerun_keeps_a_filled_front_page(tmp_path: Path) -> None:
    m = init(tmp_path, "--type", "entity")
    (m / "START HERE.md").write_text("filled in\n", encoding="utf-8")
    init(tmp_path, "--type", "entity")
    assert (m / "START HERE.md").read_text(encoding="utf-8") == "filled in\n"
