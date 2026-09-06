"""The coding-agent harness bundle (ADR-0039): routine operations are
slash commands that run the CLI and relay, sessions start from a brief,
and `sc find` never skips a document silently.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"
BUNDLE = REPO_ROOT / "templates" / "matter" / ".claude"
EXPECTED_COMMANDS = {"build", "build-doc", "open", "clean", "status", "commit", "find"}


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter"
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def sc(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SC), *argv], cwd=cwd,
                          capture_output=True, text=True, timeout=120)


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    dest = tmp_path / "m"
    proc = sc("init", str(dest))
    assert proc.returncode == 0, proc.stderr
    shutil.copytree(REPO_ROOT / "examples" / "demo-matter" / "src", dest / "src", dirs_exist_ok=True)
    shutil.copy(REPO_ROOT / "examples" / "demo-matter" / "envelopes.yaml", dest / "envelopes.yaml")
    shutil.copy(REPO_ROOT / "examples" / "demo-matter" / "matter.yaml", dest / "matter.yaml")
    return dest


def test_bundle_has_every_routine_command():
    names = {p.name for p in (BUNDLE / "skills").iterdir() if p.is_dir()}
    assert names == EXPECTED_COMMANDS


@pytest.mark.parametrize("name", sorted(EXPECTED_COMMANDS))
def test_each_command_runs_the_cli_and_relays(name: str):
    text = (BUNDLE / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    fm = frontmatter(text)
    assert fm["name"] == name
    assert fm.get("description")
    assert fm.get("model", "").startswith("claude-"), "a relay command names its (small) model"
    assert fm.get("effort") in {"low", "medium"}
    assert "!`" in text, "the CLI runs before the model sees the prompt"
    if name != "commit":  # commit is pure git; the others run sc
        assert "@@PROSAIC@@" in text, "the checkout path is a placeholder until install"
    if name in {"build", "build-doc", "open", "clean", "status"}:
        assert fm["model"] == "claude-haiku-4-5"
        assert re.search(r"not edit|not delete|Nothing else|Do not read", text)


def test_settings_hook_prints_the_brief():
    cfg = json.loads((BUNDLE / "settings.json").read_text())
    starts = cfg["hooks"]["SessionStart"]
    cmds = [h["command"] for entry in starts for h in entry["hooks"]]
    assert any("sc\" brief" in c or "sc brief" in c for c in cmds)
    assert all("@@PROSAIC@@" in c for c in cmds)


def test_init_installs_bundle_with_the_path_resolved(matter: Path):
    installed = matter / ".claude"
    assert (installed / "settings.json").is_file()
    for name in EXPECTED_COMMANDS:
        text = (installed / "skills" / name / "SKILL.md").read_text()
        assert "@@PROSAIC@@" not in text
        if name != "commit":
            assert str(REPO_ROOT) in text
    assert "@@PROSAIC@@" not in (installed / "settings.json").read_text()
    json.loads((installed / "settings.json").read_text())


def test_harness_install_refreshes_but_leaves_local_settings(matter: Path):
    local = matter / ".claude" / "settings.local.json"
    local.write_text('{"permissions": {"allow": ["Bash(ls *)"]}}')
    (matter / ".claude" / "skills" / "build" / "SKILL.md").write_text("garbage")
    proc = sc("harness", "install", str(matter))
    assert proc.returncode == 0, proc.stderr
    assert "garbage" not in (matter / ".claude" / "skills" / "build" / "SKILL.md").read_text()
    assert local.read_text().startswith('{"permissions"')


def test_brief_is_short_and_names_the_routine_commands(matter: Path):
    (matter / "TODO.md").write_text("# TODO\n\n1. File the reply by Friday\n2. Call the clerk\n")
    (matter / "KNOWLEDGE.md").write_text(
        "# KNOWLEDGE\n\n## Upcoming hearings\n\n- October 2, 2026: motion hearing, Dept. 9\n\n## Other\n\nlong text\n")
    proc = sc("brief", str(matter))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.startswith("# Matter brief: Smith v. Roe")
    assert "October 2, 2026" in out
    assert "File the reply by Friday" in out
    assert "long text" not in out, "the brief quotes calendar sections only"
    assert "/build" in out and "/find" in out
    assert len(out.splitlines()) < 60


def test_open_without_a_build_is_a_clear_error(matter: Path):
    proc = sc("open", "demo_declaration", "--print-only", "--matter-dir", str(matter))
    assert proc.returncode != 0
    assert "build it first" in proc.stderr


def test_open_prints_built_pdfs(matter: Path):
    out = matter / "out" / "demo_declaration"
    out.mkdir(parents=True)
    (out / "a.pdf").write_bytes(b"%PDF-1.4\n")
    proc = sc("open", "demo_declaration", "--print-only", "--matter-dir", str(matter))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("a.pdf")


def test_find_reports_hits_and_unsearched_pdfs(matter: Path):
    (matter / "assets").mkdir(exist_ok=True)
    (matter / "assets" / "scan.pdf").write_bytes(b"%PDF-1.4\n")          # no sidecar
    (matter / "assets" / "letter.pdf").write_bytes(b"%PDF-1.4\n")
    (matter / "assets" / "letter.txt").write_text("Dear Jane Roe, about the meeting on May 3.")
    (matter / "out").mkdir(exist_ok=True)
    (matter / "out" / "ignored.md").write_text("Jane Roe should not be found under out/")
    proc = sc("find", "Jane Roe", "--matter-dir", str(matter))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "assets/letter.txt" in out
    assert "Declaration of Jane Roe.md" in out
    assert "out/ignored.md" not in out
    assert "UNSEARCHED: 1 PDF" in out and "assets/scan.pdf" in out
    miss = sc("find", "zzz-not-there", "--matter-dir", str(matter))
    assert miss.returncode == 1
    assert "0 hit line(s)" in miss.stdout
