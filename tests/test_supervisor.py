"""The standby supervisor (ADR-0044): agent roles, watch-mode sync with a
run summary, refinement inputs, the standup agenda, and age-based clean.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"
AGENT_RUN = REPO_ROOT / "cli" / "agent-run"
SYNC = REPO_ROOT / "sync" / "matter_sync.sh"


def sc(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SC), *argv], cwd=cwd, capture_output=True, text=True, timeout=300
    )


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    m = tmp_path / "m"
    proc = sc("init", str(m), "--git", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    (m / "matter.yaml").write_text(
        "case:\n  name: Smith v. Roe\nagent:\n  roles:\n    triage: {model: claude-test-model, max_turns: 7}\n"
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "chore: init",
        ],
        cwd=m,
        check=True,
    )
    return m


def fake_claude(bin_dir: Path) -> None:
    (bin_dir / "claude").write_text('#!/bin/bash\necho "ARGS: $*"\ncat >/dev/null\n')
    (bin_dir / "claude").chmod(0o755)


def test_agent_run_role_reads_matter_yaml(matter: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_claude(bin_dir)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PROSAIC_AGENT_CLI": "claude"}
    out = subprocess.run(
        [str(AGENT_RUN), "--role", "triage"],
        input="hello",
        text=True,
        cwd=matter,
        capture_output=True,
        env=env,
    ).stdout
    assert "--model claude-test-model" in out and "--max-turns 7" in out
    out2 = subprocess.run(
        [str(AGENT_RUN), "--role", "triage", "--model", "explicit"],
        input="hello",
        text=True,
        cwd=matter,
        capture_output=True,
        env=env,
    ).stdout
    assert "--model explicit" in out2, "an explicit flag wins over the role"
    out3 = subprocess.run(
        [str(AGENT_RUN), "--role", "nosuch"],
        input="hello",
        text=True,
        cwd=matter,
        capture_output=True,
        env=env,
    ).stdout
    assert "--model" not in out3, "an unknown role adds nothing"


def test_watch_mode_triages_settled_inbox_files_and_writes_a_summary(
    matter: Path, tmp_path: Path
) -> None:
    inbox = matter / "inbox"
    (inbox / "letter.txt").write_text("a new letter\n")
    old = time.time() - 120
    os.utime(inbox / "letter.txt", (old, old))  # settled
    (inbox / "fresh.txt").write_text("still downloading\n")  # too new; skipped this round
    seen = tmp_path / "seen.txt"
    fake = tmp_path / "agent.sh"
    fake.write_text(f"#!/bin/bash\ncat > {seen}\n")
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PROSAIC_AGENT_CMD": str(fake),
        "PROSAIC_ROOT": str(REPO_ROOT),
        "PROSAIC_PYTHON": sys.executable,
    }
    proc = subprocess.run(
        ["/bin/bash", str(SYNC), str(matter), "--watch"],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    prompt = seen.read_text()
    assert "inbox " in prompt and "letter.txt" in prompt and "fresh.txt" not in prompt
    summary = json.loads((matter / ".state" / "sync_last_run.json").read_text())
    assert summary["mode"] == "watch" and summary["new_files"] == 1 and summary["triage"] == "ok"
    assert summary["connectors"] == {}
    # a second run finds nothing new
    seen.unlink()
    proc2 = subprocess.run(
        ["/bin/bash", str(SYNC), str(matter), "--watch"],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc2.returncode == 0 and not seen.exists()


def test_refine_inputs_and_standup_agenda(matter: Path) -> None:
    (matter / "QUESTIONS.md").write_text("# QUESTIONS\n\n1. When did the letter arrive?\n")
    (matter / ".state").mkdir(exist_ok=True)
    (matter / ".state" / "sync_last_run.json").write_text(
        json.dumps(
            {
                "mode": "scheduled",
                "started": 1,
                "finished": 2,
                "outcome": "connector-failures",
                "new_files": 3,
                "triage": "ok",
                "connectors": {"gmail": "ok", "mycase": "failed"},
                "failed_connectors": ["mycase"],
            }
        )
    )
    proc = sc("refine", str(matter), "--inputs-only", cwd=matter)
    assert proc.returncode == 0, proc.stderr
    inputs = next((matter / "derived" / "refine").glob("*_inputs.md")).read_text()
    assert (
        "## Commits" in inputs
        and "## Text coverage" in inputs
        and "failed connectors: mycase" in inputs
    )
    assert "When did the letter arrive" in inputs
    proc = sc("standup", "agenda", str(matter), cwd=matter)
    assert proc.returncode == 0, proc.stderr
    agenda = Path(proc.stdout.strip()).read_text()
    assert "Standup agenda" in agenda and "FAILED connectors: mycase" in agenda
    assert "When did the letter arrive" in agenda and "/standup" in agenda
    brief = sc("brief", str(matter), cwd=matter).stdout
    assert "FAILED connectors: mycase" in brief


def test_clean_older_than_reports_only_disposable_trees(matter: Path) -> None:
    (matter / "out" / "env").mkdir(parents=True)
    old = time.time() - 40 * 86400
    for rel in ("out/env/old.pdf", "derived/find/old.md", "assets/keep.pdf", "out/env/new.pdf"):
        p = matter / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
        if "new" not in rel:
            os.utime(p, (old, old))
    proc = sc("clean", str(matter), "--older-than", "30", cwd=matter)
    assert proc.returncode == 0, proc.stderr
    assert "out/env/old.pdf" in proc.stdout and "derived/find/old.md" in proc.stdout
    assert "assets/keep.pdf" not in proc.stdout and "new.pdf" not in proc.stdout
    assert (matter / "out" / "env" / "old.pdf").exists(), "report only without --apply"
    proc = sc("clean", str(matter), "--older-than", "30", "--apply", cwd=matter)
    assert (
        not (matter / "out" / "env" / "old.pdf").exists()
        and (matter / "assets" / "keep.pdf").exists()
    )


def test_supervisor_dispatches_only_what_is_due(matter: Path, tmp_path: Path) -> None:
    """One launchd job, one script: inbox triage always looks, sync is
    guarded, refine and standup run once a day after their hours."""
    seen = tmp_path / "seen.txt"
    fake = tmp_path / "agent.sh"
    fake.write_text(f"#!/bin/bash\ncat > {seen}\n")
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PROSAIC_AGENT_CMD": str(fake),
        "PROSAIC_ROOT": str(REPO_ROOT),
        "PROSAIC_PYTHON": sys.executable,
        "PROSAIC_NOW": "01:00",
        "PROSAIC_MIN_INTERVAL_HOURS": "999",
    }
    (matter / ".state").mkdir(exist_ok=True)
    (matter / ".state" / "sync_last_success").write_text(str(int(time.time())))
    sup = REPO_ROOT / "sync" / "matter_supervisor.sh"
    proc = subprocess.run(
        ["/bin/bash", str(sup), str(matter)], env=env, capture_output=True, text=True, timeout=600
    )
    assert proc.returncode == 0, proc.stderr
    assert not (matter / "derived" / "standup").exists(), "01:00 is before the standup hour"
    assert (
        not list((matter / "derived").glob("refine/*.md"))
        if (matter / "derived" / "refine").exists()
        else True
    )
    env["PROSAIC_NOW"] = "09:00"
    proc = subprocess.run(
        ["/bin/bash", str(sup), str(matter)], env=env, capture_output=True, text=True, timeout=600
    )
    assert proc.returncode == 0, proc.stderr
    agendas = list((matter / "derived" / "standup").glob("*.md"))
    assert len(agendas) == 1, "agenda written once after 08:50"
    inputs = list((matter / "derived" / "refine").glob("*_inputs.md"))
    log_root = subprocess.run(
        [sys.executable, str(SC), "paths", "log-dir"], capture_output=True, text=True
    ).stdout.strip()
    log = Path(log_root) / f"sync-{matter.name}.log"
    assert inputs, (
        "refine ran after 02:30 (the fake agent stands in for the model); "
        f"supervisor log:\n{log.read_text() if log.exists() else f'(no log at {log})'}"
    )
    proc = subprocess.run(
        ["/bin/bash", str(sup), str(matter)], env=env, capture_output=True, text=True, timeout=600
    )
    assert len(list((matter / "derived" / "standup").glob("*.md"))) == 1, (
        "not written twice in a day"
    )
