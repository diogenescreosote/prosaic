"""cli/agent-run is the one place an agent CLI is named (ADR-0020).

These tests run the real script against fake provider binaries, so
what is pinned is the dispatch itself: which provider gets selected,
and the exact flags each one receives. When a provider CLI renames a
flag, the fix is one function in agent-run and one expectation here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_RUN = REPO_ROOT / "cli" / "agent-run"

FAKE_PROVIDER = """#!/bin/bash
printf '%s\\n' "$@" > "{argfile}"
cat >> "{argfile}" 2>/dev/null || true
echo "{name} ran"
"""


def fake_bin(bin_dir: Path, name: str, argfile: Path) -> None:
    exe = bin_dir / name
    exe.write_text(FAKE_PROVIDER.format(argfile=argfile, name=name))
    exe.chmod(0o755)


def run(
    args: list[str],
    bin_dir: Path,
    prompt: str = "do the thing",
    **env_extra: str,
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    env.update(env_extra)
    return subprocess.run(
        [str(AGENT_RUN), *args],
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    return d


def test_check_reports_the_provider_it_finds(bin_dir: Path, tmp_path: Path) -> None:
    fake_bin(bin_dir, "claude", tmp_path / "args")
    proc = run(["--check"], bin_dir)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "claude"


def test_check_fails_when_no_provider_exists(bin_dir: Path) -> None:
    proc = run(["--check"], bin_dir)
    assert proc.returncode == 1


def test_selection_prefers_claude_then_codex(bin_dir: Path, tmp_path: Path) -> None:
    fake_bin(bin_dir, "codex", tmp_path / "codex_args")
    fake_bin(bin_dir, "gemini", tmp_path / "gemini_args")
    assert run(["--check"], bin_dir).stdout.strip() == "codex"
    fake_bin(bin_dir, "claude", tmp_path / "claude_args")
    assert run(["--check"], bin_dir).stdout.strip() == "claude"


def test_claude_dispatch_flags(bin_dir: Path, tmp_path: Path) -> None:
    argfile = tmp_path / "args"
    fake_bin(bin_dir, "claude", argfile)
    proc = run(["--dir", "/tmp/a", "--yolo"], bin_dir, prompt="judge this")
    assert proc.returncode == 0
    args = argfile.read_text().splitlines()
    assert args[:2] == ["-p", "judge this"]
    assert "--add-dir" in args and "/tmp/a" in args
    assert "--dangerously-skip-permissions" in args


def test_codex_dispatch_flags(bin_dir: Path, tmp_path: Path) -> None:
    argfile = tmp_path / "args"
    fake_bin(bin_dir, "codex", argfile)
    proc = run([], bin_dir, prompt="judge this", PROSAIC_AGENT_CLI="codex")
    assert proc.returncode == 0
    args = argfile.read_text().splitlines()
    assert args[0] == "exec"
    assert "--skip-git-repo-check" in args
    assert "--sandbox" in args and "read-only" in args
    assert args[-1] == "judge this"


def test_codex_yolo_bypasses_sandbox(bin_dir: Path, tmp_path: Path) -> None:
    argfile = tmp_path / "args"
    fake_bin(bin_dir, "codex", argfile)
    run(["--yolo"], bin_dir, PROSAIC_AGENT_CLI="codex")
    args = argfile.read_text().splitlines()
    assert "--dangerously-bypass-approvals-and-sandbox" in args
    assert "read-only" not in args


def test_gemini_dispatch_flags(bin_dir: Path, tmp_path: Path) -> None:
    argfile = tmp_path / "args"
    fake_bin(bin_dir, "gemini", argfile)
    run(
        ["--dir", "/tmp/a", "--dir", "/tmp/b", "--yolo"],
        bin_dir,
        prompt="judge this",
        PROSAIC_AGENT_CLI="gemini",
    )
    args = argfile.read_text().splitlines()
    assert "--include-directories" in args
    assert "/tmp/a,/tmp/b" in args
    assert "--yolo" in args
    assert args[-2:] == ["-p", "judge this"]


def test_custom_command_gets_prompt_on_stdin_and_env(bin_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "custom_out"
    cmd = f'cat > "{out}"; echo "dirs=$AGENT_RUN_DIRS yolo=$AGENT_RUN_YOLO"'
    proc = run(
        ["--dir", "/tmp/x", "--yolo"], bin_dir, prompt="custom prompt", PROSAIC_AGENT_CMD=cmd
    )
    assert proc.returncode == 0
    # The herestring delivery appends one trailing newline; providers
    # tolerate it, so the seam does not strip it.
    assert out.read_text() == "custom prompt\n"
    assert "dirs=/tmp/x yolo=1" in proc.stdout


def test_forced_provider_missing_from_path_is_an_error(bin_dir: Path) -> None:
    proc = run([], bin_dir, PROSAIC_AGENT_CLI="codex")
    assert proc.returncode == 1
    assert "not on PATH" in proc.stderr


def test_unknown_provider_name_is_an_error(bin_dir: Path, tmp_path: Path) -> None:
    fake_bin(bin_dir, "claude", tmp_path / "args")
    proc = run([], bin_dir, PROSAIC_AGENT_CLI="hal9000")
    assert proc.returncode == 1
    assert "unsupported" in proc.stderr


def test_empty_prompt_is_an_error_not_an_empty_run(bin_dir: Path, tmp_path: Path) -> None:
    argfile = tmp_path / "args"
    fake_bin(bin_dir, "claude", argfile)
    proc = run([], bin_dir, prompt="")
    assert proc.returncode == 2
    assert not argfile.exists(), "provider must not run on an empty prompt"


def test_unknown_flag_is_an_error(bin_dir: Path, tmp_path: Path) -> None:
    fake_bin(bin_dir, "claude", tmp_path / "args")
    proc = run(["--frobnicate"], bin_dir)
    assert proc.returncode == 2
