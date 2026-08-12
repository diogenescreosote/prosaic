"""Skills stay true or fail the suite (ADR-0021).

A SKILL.md is documentation an agent *executes*: it names commands
and paths, and a rename anywhere else in the repo silently turns
those instructions into fiction. Same cure as test_docs_coverage —
make the mechanical half a test. Whether the instructions are any
good remains a human problem.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

# Repo directories a skill may point into with a backticked path.
PATH_ROOTS = (
    "specs/",
    "docs/",
    "pleading/",
    "templates/",
    "cli/",
    "skills/",
    "tests/",
    "connectors/",
    "sync/",
    "triage/",
)


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


def frontmatter(text: str, where: Path) -> dict[str, str]:
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, f"{where}: no YAML frontmatter block"
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        if _:
            fields[key.strip()] = value.strip()
    return fields


def test_skills_directory_is_populated() -> None:
    assert skill_dirs(), "skills/ exists but holds no skills"


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_skill_has_wellformed_skillfile(skill: Path) -> None:
    skillfile = skill / "SKILL.md"
    assert skillfile.exists(), f"{skill.name}/ has no SKILL.md"
    fields = frontmatter(skillfile.read_text(encoding="utf-8"), skillfile)
    assert fields.get("name") == skill.name, (
        f"{skill.name}: frontmatter name {fields.get('name')!r} must equal the directory name"
    )
    desc = fields.get("description", "")
    assert desc, f"{skill.name}: frontmatter has no description"
    assert len(desc) <= 1024, f"{skill.name}: description over 1024 chars"
    assert "Use when" in desc, (
        f"{skill.name}: the description must say when to reach for the "
        f"skill ('... Use when ...') — that field is the loading trigger"
    )


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_skill_is_indexed(skill: Path) -> None:
    index = (SKILLS_DIR / "README.md").read_text(encoding="utf-8")
    assert f"{skill.name}/SKILL.md" in index, f"{skill.name} is not in the skills/README.md index"


def test_index_promises_only_skills_that_exist() -> None:
    index = (SKILLS_DIR / "README.md").read_text(encoding="utf-8")
    promised = set(re.findall(r"\[([a-z-]+)\]\(\1/SKILL\.md\)", index))
    actual = {p.name for p in skill_dirs()}
    stale = sorted(promised - actual)
    assert not stale, f"skills/README.md indexes skills that do not exist: {stale}"


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_every_sc_subcommand_a_skill_names_exists(skill: Path) -> None:
    source = (REPO_ROOT / "cli" / "sc").read_text(encoding="utf-8")
    commands = set(re.findall(r'add_parser\("([a-z-]+)"', source))
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    named = set(re.findall(r"(?:cli/)?\bsc ([a-z][a-z-]*)", text))
    ghosts = sorted(named - commands)
    assert not ghosts, f"{skill.name} instructs `sc {ghosts}` but cli/sc has no such subcommand"


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_every_path_a_skill_names_exists(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    missing = []
    for token in re.findall(r"`([^`]+)`", text):
        token = token.replace("<prosaic>/", "")
        # Only bare repo paths; commands and globs judge themselves.
        if not token.startswith(PATH_ROOTS) or " " in token:
            continue
        candidate = token.rstrip(".,;:")
        if any(ch in candidate for ch in "*<>{}"):
            continue
        if not (REPO_ROOT / candidate).exists():
            missing.append(candidate)
    assert not missing, f"{skill.name} points at paths that do not exist: {missing}"
