"""The coding-agent harness bundle (ADR-0040): routine operations are
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
EXPECTED_COMMANDS = {"build", "build-doc", "open", "clean", "status", "commit", "find", "standup",
                     "citecheck", "clerkreview", "judgereview", "oppo", "preflight", "secondopinion"}


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
    assert fm.get("effort") in {"low", "medium", "high"}
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
    import pymupdf as fitz
    (matter / "assets").mkdir(exist_ok=True)
    scan = fitz.open(); pg = scan.new_page(); pg.draw_rect(pg.rect, color=(0, 0, 0))
    scan.save(str(matter / "assets" / "scan.pdf")); scan.close()          # no text layer, no sidecar
    letter = fitz.open(); letter.new_page().insert_text((72, 72), "Dear Jane Roe, about the meeting on May 3. " * 3)
    letter.save(str(matter / "assets" / "letter.pdf")); letter.close()
    (matter / "assets" / "letter.txt").write_text("Dear Jane Roe, about the meeting on May 3.")
    (matter / "out").mkdir(exist_ok=True)
    (matter / "out" / "ignored.md").write_text("Jane Roe should not be found under out/")
    proc = sc("find", "Jane Roe", "--matter-dir", str(matter))
    assert proc.returncode == 2, "something was not searchable, so exit 2 even with hits"
    out = proc.stdout
    assert "assets/letter.txt" in out
    assert "Declaration of Jane Roe.md" in out
    assert "out/ignored.md" not in out
    assert "UNSEARCHED: 1 document(s)" in out and "assets/scan.pdf" in out
    assert "text coverage:" in out
    miss = sc("find", "zzz-not-there", "--matter-dir", str(matter))
    assert miss.returncode == 2 and "0 hit line(s)" in miss.stdout


def test_find_summarizes_a_broad_term(matter: Path):
    import pymupdf as fitz
    (matter / "assets").mkdir(exist_ok=True)
    for i in range(45):  # more files than the summary threshold
        (matter / "assets" / f"note{i:02d}.txt").write_text(f"Quill wrote on day {i}. Quill again.\n")
    proc = sc("find", "Quill", "--matter-dir", str(matter))
    out = proc.stdout
    assert "in 45 file(s)" in out and "files by directory: assets 45" in out
    assert "(summary: broad term" in out and "Quill wrote" not in out, "no snippets in summary mode"
    assert len(out) < 6000, f"summary output should stay small, got {len(out)} chars"
    full = sc("find", "Quill", "--full", "--per-file", "1", "--matter-dir", str(matter)).stdout
    assert "Quill wrote" in full
    narrow = sc("find", "-F", "day 7.", "--matter-dir", str(matter)).stdout
    assert "note07.txt" in narrow and "Quill wrote on day 7" in narrow


def test_find_all_keeps_only_files_with_every_term(matter: Path):
    (matter / "assets").mkdir(exist_ok=True)
    (matter / "assets" / "both.txt").write_text("Marlow sent the 364 notice.\n")
    (matter / "assets" / "one.txt").write_text("Marlow only.\n")
    (matter / "assets" / "other.txt").write_text("Section 364 only.\n")
    out = sc("find", "--all", "Marlow", "364", "--matter-dir", str(matter)).stdout
    assert "files carrying every term: 1" in out
    assert "assets/both.txt" in out and "assets/one.txt" not in out and "assets/other.txt" not in out


def test_find_searches_related_matters(matter: Path, tmp_path: Path):
    other = tmp_path / "other"
    (other / "assets").mkdir(parents=True)
    (other / "matter.yaml").write_text("case:\n  name: Other v. Thing\n")
    (other / "assets" / "prod.txt").write_text("Bates OTHER00050: a letter to Hubbard.\n")
    (matter / "matter.yaml").write_text((matter / "matter.yaml").read_text() + "\nrelated_matters:\n  - ../other\n")
    out = sc("find", "Hubbard", "--matter-dir", str(matter)).stdout
    assert "# Matter: other (related)" in out and "assets/prod.txt" in out
    only = sc("find", "Hubbard", "--this-matter-only", "--matter-dir", str(matter)).stdout
    assert "prod.txt" not in only
    brief = sc("brief", str(matter)).stdout
    assert "related matters searched by `/find`: ../other" in brief


def test_find_checklist_gates_the_answer(matter: Path):
    (matter / "assets").mkdir(exist_ok=True)
    for i in range(45):
        (matter / "assets" / f"n{i:02d}.txt").write_text(f"Quill {i}\n")
    proc = sc("find", "Quill", "--matter-dir", str(matter))
    m = re.search(r"CHECKLIST: (derived/find/\S+) --- 45 file", proc.stdout)
    assert m, proc.stdout[-400:]
    cl = matter / m.group(1)
    assert cl.read_text().count("- [ ] ") == 45
    v = sc("find", "--verify", str(cl), "--matter-dir", str(matter))
    assert v.returncode == 3 and "45 unmarked" in v.stdout
    text = cl.read_text().replace("- [ ] assets/n00.txt", "- [read] assets/n00.txt", 1)
    text = re.sub(r"- \[ \] (assets/n\d+\.txt \(\d+\))", r"- [skip: filename only, a test note] \1", text)
    cl.write_text(text)
    v2 = sc("find", "--verify", str(cl), "--matter-dir", str(matter))
    assert v2.returncode == 0 and "1 read, 44 skipped, 0 unmarked" in v2.stdout
    assert "filename only" in v2.stdout


def test_find_writes_a_checklist_above_ten_files_even_with_snippets(matter: Path):
    (matter / "assets").mkdir(exist_ok=True)
    for i in range(12):
        (matter / "assets" / f"c{i:02d}.txt").write_text(f"Roth IRA line {i}\n")
    out = sc("find", "-F", "Roth IRA", "--matter-dir", str(matter)).stdout
    assert "Roth IRA line 3" in out, "snippets still shown below the summary threshold"
    assert "CHECKLIST: derived/find/" in out and "12 file(s)" in out
