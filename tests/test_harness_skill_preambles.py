"""Skill preambles must survive the harness's argument substitution.

Claude Code rewrites ``$ARGUMENTS`` and the positional ``$0``..``$9``
textually inside a SKILL.md's ``!`...``` blocks before the shell runs.
So a preamble may never parse the argument string in shell: no
``${ARGUMENTS%%...}``, no awk ``$0``. It captures the text in a quoted
heredoc and hands it to the CLI whole, and the CLI splits it. This file
proves both halves: a lint over every bundled skill, and a simulation of
the substitution against a hostile argument string.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"
BUNDLE = REPO_ROOT / "templates" / "matter" / ".claude"

BLOCK = re.compile(r"!`(.*?)`", re.S)

HOSTILE = (
    "my_envelope -- a brief with \"double\" and 'single' quotes, $0 and $1, "
    "$(echo injected), a second -- separator, and a newline\nsecond line of brief"
)


def preambles(text: str) -> list[str]:
    return BLOCK.findall(text)


def test_no_skill_parses_arguments_in_shell() -> None:
    bad = []
    for skill in sorted(BUNDLE.glob("skills/*/SKILL.md")):
        for block in preambles(skill.read_text()):
            if "${ARGUMENTS" in block or re.search(r"\$\d", block) or "awk" in block:
                bad.append(f"{skill.parent.name}: {block[:80]!r}")
    assert not bad, "shell-side argument parsing will be mangled by the harness:\n" + "\n".join(bad)


def _stub_prosaic(tmp_path: Path) -> tuple[Path, Path]:
    """A fake checkout whose cli/sc records its argv as JSON lines."""
    root = tmp_path / "prosaic"
    (root / "cli").mkdir(parents=True)
    log = tmp_path / "argv.jsonl"
    stub = root / "cli" / "sc"
    report = tmp_path / "report.md"
    report.write_text("stub report\n")
    stub.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"print({str(report)!r})\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return root, log


def test_secondopinion_preamble_survives_substitution(tmp_path: Path) -> None:
    text = (BUNDLE / "skills" / "secondopinion" / "SKILL.md").read_text()
    root, log = _stub_prosaic(tmp_path)
    blocks = preambles(text)
    assert len(blocks) == 3
    for block in blocks:
        rendered = block.replace("@@PROSAIC@@", str(root)).replace("$ARGUMENTS", HOSTILE)
        proc = subprocess.run(
            ["bash", "-c", rendered], capture_output=True, text=True, cwd=tmp_path, timeout=30
        )
        assert proc.returncode == 0, f"block failed: {proc.stderr}\n{rendered}"
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [c[:2] for c in calls] == [
        ["review", "paths"],
        ["review", "second-opinion"],
        ["review", "report"],
    ]
    for c in calls:
        assert "--args" in c
        assert c[c.index("--args") + 1] == HOSTILE, "argument string did not arrive verbatim"
    assert not (tmp_path / "injected").exists()


def test_cli_splits_target_and_brief(tmp_path: Path) -> None:
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("sc_module", str(SC))
    spec = importlib.util.spec_from_loader("sc_module", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    assert mod.split_review_args("env -- the brief") == ("env", "the brief")
    assert mod.split_review_args("src/a b.md -- x -- y") == ("src/a b.md", "x -- y")
    assert mod.split_review_args("env") == ("env", "")
    assert mod.split_review_args("env --") == ("env", "")
    assert mod.split_review_args(HOSTILE)[0] == "my_envelope"
    assert mod.split_review_args(HOSTILE)[1].startswith('a brief with "double"')


def test_review_paths_accepts_args(tmp_path: Path) -> None:
    matter = tmp_path / "m"
    subprocess.run(
        [sys.executable, str(SC), "init", str(matter)], check=True, capture_output=True, text=True
    )
    (matter / "src").mkdir(exist_ok=True)
    (matter / "src" / "draft.md").write_text("---\npaper_title: X\n---\n\nbody\n")
    raw = "src/draft.md -- " + HOSTILE.split(" -- ", 1)[1]
    proc = subprocess.run(
        [sys.executable, str(SC), "review", "paths", "--args", raw, "--matter-dir", str(matter)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[0] == "# review target: src/draft.md"
