"""The knowledge vault (ADR-0043): one note per entity, Obsidian-compatible,
linted; a legacy single file migrates into staging, never into the void.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "triage"))
import knowledge_vault as kv  # noqa: E402

SC = REPO_ROOT / "cli" / "sc"

LEGACY = """# KNOWLEDGE --- Smith v. Roe

Bold preamble about the case.

## Posture

The matter is set for trial November 12, 2026.

## Key people

Jane Roe is the respondent. Counsel is A. Advocate.

## September 3--4, 2026 --- a diary block

### The filing went in

Something happened on September 3, 2026.

## Timeline

- January 5, 2026: petition filed.
"""


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    m = tmp_path / "m"
    (m / "assets").mkdir(parents=True)
    (m / "matter.yaml").write_text("case:\n  name: Smith v. Roe\n")
    (m / "assets" / "letter.pdf").write_bytes(b"%PDF-1.4\n")
    return m


def sc(*argv: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SC), *argv], cwd=cwd, capture_output=True, text=True, timeout=300)


def test_init_scaffolds_an_obsidian_compatible_vault(matter: Path):
    out = kv.init(matter)
    for d in kv.TYPE_DIRS.values():
        assert (matter / "knowledge" / d).is_dir()
    assert (matter / "knowledge" / "README.md").exists()
    assert ".obsidian/" in (matter / ".gitignore").read_text()
    idx = (matter / "KNOWLEDGE.md").read_text()
    assert kv.INDEX_START in idx and kv.INDEX_END in idx
    assert any("entities.json" in o for o in out)


def test_init_refuses_to_overwrite_a_monolith(matter: Path):
    (matter / "KNOWLEDGE.md").write_text(LEGACY)
    with pytest.raises(SystemExit):
        kv.init(matter)
    assert (matter / "KNOWLEDGE.md").read_text() == LEGACY


def test_new_note_and_index_and_entity_index(matter: Path):
    kv.init(matter)
    p = kv.new_note(matter, "person", "Jane Roe", aliases=["J. Roe", "Roe"])
    assert p == matter / "knowledge" / "people" / "jane-roe.md"
    kv.write_index(matter, kv.load_notes(matter))
    idx = (matter / "KNOWLEDGE.md").read_text()
    assert "[[jane-roe]]" in idx and "## People (1)" in idx
    import json
    ent = json.loads((matter / "derived" / "knowledge" / "entities.json").read_text())
    assert ent["aliases"]["j. roe"] == ["jane-roe"]
    assert ent["notes"]["jane-roe"]["type"] == "person"


def test_check_catches_the_failure_modes(matter: Path):
    kv.init(matter)
    kv.new_note(matter, "person", "Jane Roe", aliases=["Roe"])
    bad = matter / "knowledge" / "topics" / "bad.md"
    bad.write_text("""---
title: Bad note
type: topic
aliases: [Roe]
updated: last week
sources:
  - path: assets/missing.pdf
related: ["[[nowhere]]"]
verified: human
---

## September 3, 2026 --- a diary heading

We met yesterday. See [[jane-roe]].
""")
    kv.write_index(matter, kv.load_notes(matter))
    notes = kv.check(matter)
    problems = "\n".join(p for n in notes for p in n.problems)
    assert "absolute YYYY-MM-DD" in problems
    assert "alias 'Roe' is also claimed by [[jane-roe]]" in problems
    assert "source path does not exist" in problems
    assert "link does not resolve: [[nowhere]]" in problems
    assert "heading is a date" in problems
    warnings = "\n".join(w for n in notes for w in n.warnings)
    assert "relative date 'yesterday'" in warnings
    # the good note is fine, apart from the orphan warning
    good = next(n for n in notes if n.stem == "jane-roe")
    assert not good.problems


def test_check_flags_a_note_missing_from_the_index(matter: Path):
    kv.init(matter)
    kv.new_note(matter, "topic", "Fresh")
    notes = kv.check(matter)  # index not regenerated since the note was made
    assert any("not in the KNOWLEDGE.md index" in p for n in notes for p in n.problems)
    proc = sc("knowledge", "check", str(matter), "--fix", cwd=matter)
    assert proc.returncode == 0, proc.stdout


def test_migrate_splits_the_monolith_into_staging_and_preserves_it(matter: Path):
    (matter / "KNOWLEDGE.md").write_text(LEGACY)
    out = kv.init(matter, migrate=True)
    stage = matter / "knowledge" / "_migration"
    assert (stage / "KNOWLEDGE.legacy.md").read_text() == LEGACY
    names = sorted(p.name for p in stage.glob("*.md") if p.name != "KNOWLEDGE.legacy.md")
    assert names[0].startswith("01-") and any("key-people" in n for n in names)
    diary = next(p for p in stage.glob("*.md") if "september" in p.name)
    meta, body, err = kv.split_front_matter(diary.read_text())
    assert err is None and meta["updated"] == "2026-09-04" and meta["migrated_from"].startswith("KNOWLEDGE.md ##")
    idx = (matter / "KNOWLEDGE.md").read_text()
    assert "Migration in progress" in idx and "Migration staging" in idx
    notes = kv.check(matter)
    assert not any(n.problems for n in notes), [p for n in notes for p in n.problems]
    assert all(n.staging for n in notes)
    assert any("staging note" in w for n in notes for w in n.warnings)
    assert any("split into" in o for o in out)


def test_brief_and_find_use_the_vault(matter: Path):
    kv.init(matter)
    ev = kv.new_note(matter, "event", "Motion hearing")
    ev.write_text(ev.read_text().replace("date: \n", "date: 2099-10-02\n"))
    iss = kv.new_note(matter, "issue", "Privilege log dispute")
    kv.new_note(matter, "person", "Jane Roe", aliases=["J. Roe"])
    kv.write_index(matter, kv.load_notes(matter))
    brief = sc("brief", str(matter), cwd=matter).stdout
    assert "Upcoming events (knowledge vault)" in brief and "2099-10-02: Motion hearing" in brief
    assert "Open issues (1)" in brief and "Privilege log dispute" in brief
    find = sc("find", "j. roe", "--matter-dir", str(matter), cwd=matter).stdout
    assert "## Knowledge notes (alias index)" in find and "[[jane-roe]]" in find


def test_upgrade_dry_run_reports_every_step(matter: Path):
    (matter / "KNOWLEDGE.md").write_text(LEGACY)
    proc = sc("upgrade", str(matter), "--dry-run", cwd=matter)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for step in ("harness bundle", "derived text tree", "knowledge vault", ".gitignore", "scheduled sync"):
        assert step in out
    assert "would split" in out and "Needs a human or an agent" in out
    assert (matter / "KNOWLEDGE.md").read_text() == LEGACY, "dry run changes nothing"
    assert not (matter / ".claude").exists()


def test_upgrade_is_idempotent(matter: Path, monkeypatch):
    (matter / "KNOWLEDGE.md").write_text(LEGACY)
    first = sc("upgrade", str(matter), cwd=matter)
    assert first.returncode == 0, first.stderr
    assert (matter / ".claude" / "skills" / "build" / "SKILL.md").exists()
    assert (matter / "knowledge" / "_migration" / "KNOWLEDGE.legacy.md").exists()
    second = sc("upgrade", str(matter), cwd=matter)
    assert second.returncode == 0
    assert "vault present" in second.stdout and "staging" in second.stdout
    assert (matter / "knowledge" / "_migration" / "KNOWLEDGE.legacy.md").read_text() == LEGACY
