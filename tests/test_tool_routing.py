"""Project tools run through `sc`, under the project environment (ADR-0050).

The failure this pins: instructions said ``python3 <prosaic>/pleading/
ocr_supplement.py ...``, the stock macOS ``python3`` has no PyMuPDF, and
every agent that followed them died at ``import fitz``. Three guarantees
keep that from coming back:

1. No document an agent executes tells it to run bare ``python3``,
   ``pip install``, or a script by path. Checked over every Markdown
   file outside design history and the test fixtures, and over the
   usage docstrings of the scripts themselves.
2. ``sc`` runs every subcommand under the project interpreter, and each
   script it routes to exists.
3. A script run the old way re-executes under the project interpreter
   instead of failing, and says which ``sc`` command to use.

Plus ``sc doctor``: a missing program is reported with the command that
installs it on the host, and the exit status says not ready.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"

# A bare interpreter running a script, a module or inline code, or a
# hand pip install. `sc python -c` is the sanctioned form, hence the
# lookbehind.
BARE = re.compile(
    r"(?<!sc )(?<![\w/.-])python3?\s+(?:-[cm]\b|<prosaic>|[\w./<>-]*\.py\b)"
    r"|(?<![\w-])pip3?\s+install\b"
)

# Lines that name a bare invocation in order to forbid or translate it,
# or that document the one tool deliberately outside the environment.
ALLOWED = (
    ("docs/install.md", re.compile(r"^\| `(?:python3|pip) ")),  # the "instead of" table
    ("docs/stt.md", re.compile(r"pip install whisperx")),  # its own conda env, ADR-0050
    ("specs/cli.md", re.compile(r"python3 -m venv|pip install -r")),  # what `sc setup` does
)
PROHIBITION = re.compile(r"\b[Nn]ever\b")

# Trees whose Markdown is not executed by an agent: decision history,
# and the fixtures the suite builds from.
SKIP_PREFIXES = ("design/", "tests/", "local/", "modules/")


def tracked_markdown() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in out.stdout.split("\0") if p and not p.startswith(SKIP_PREFIXES)]


def violations_in(rel: str, text: str) -> list[str]:
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        if not BARE.search(line) or PROHIBITION.search(line):
            continue
        if any(rel == f and rx.search(line) for f, rx in ALLOWED):
            continue
        found.append(f"{rel}:{n}: {line.strip()}")
    return found


def test_no_instruction_runs_bare_python() -> None:
    bad: list[str] = []
    for rel in tracked_markdown():
        path = REPO_ROOT / rel
        if path.is_file():
            bad += violations_in(rel, path.read_text(encoding="utf-8", errors="replace"))
    assert not bad, (
        "these instructions run a project tool with bare python3/pip; use "
        "`sc <command>`, `sc run <script>` or `sc python` (ADR-0050):\n  " + "\n  ".join(bad)
    )


def test_script_usage_strings_name_the_sc_route() -> None:
    bad: list[str] = []
    for script in sorted([*REPO_ROOT.glob("pleading/*.py"), *REPO_ROOT.glob("triage/*.py")]):
        doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))) or ""
        rel = str(script.relative_to(REPO_ROOT))
        bad += violations_in(rel, doc)
    assert not bad, "usage docstrings still say bare python:\n  " + "\n  ".join(bad)


def test_the_rule_is_stated_where_agents_read_it() -> None:
    for rel in ("templates/workspace/AGENTS.md", "templates/matter/AGENTS.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "sc doctor" in text, f"{rel} does not route a missing tool to `sc doctor`"
        assert "sc run" in text, f"{rel} does not name `sc run` for other scripts"


def sc_script_commands() -> dict[str, str]:
    source = SC.read_text(encoding="utf-8")
    block = re.search(r"SCRIPT_COMMANDS = \{(.*?)\n\}", source, re.DOTALL)
    assert block, "SCRIPT_COMMANDS is gone from cli/sc"
    return dict(re.findall(r'"([a-z-]+)": "([\w/.]+\.py)"', block.group(1)))


def test_every_routed_script_exists_and_hops() -> None:
    commands = sc_script_commands()
    assert {"ocr", "highlight", "redact", "verify-redactions", "pleadings-manifest"} <= set(
        commands
    )
    for name, rel in commands.items():
        script = REPO_ROOT / rel
        assert script.is_file(), f"sc {name} routes to missing {rel}"
        text = script.read_text(encoding="utf-8")
        assert f'project_python.ensure(__file__, "{name}")' in text, (
            f"{rel} does not hop into the project environment naming `sc {name}`"
        )


def run_sc(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SC), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def expected_interpreter() -> str:
    sys.path.insert(0, str(REPO_ROOT / "pleading"))
    try:
        import project_python

        return str(project_python.project_python())
    finally:
        sys.path.pop(0)


def test_sc_python_is_the_project_interpreter() -> None:
    out = run_sc("python", "-c", "import sys, pymupdf, pypdf, yaml; print(sys.prefix)")
    assert out.returncode == 0, out.stderr
    want = Path(expected_interpreter())
    # A venv's interpreter is a symlink to its base; the venv is the prefix.
    if want.parent.name == "bin" and (want.parent.parent / "pyvenv.cfg").exists():
        prefix = out.stdout.strip().splitlines()[-1]
        assert Path(prefix).resolve() == want.parent.parent.resolve()


def test_script_passthrough_hands_help_to_the_script() -> None:
    out = run_sc("highlight", "--help")
    assert out.returncode == 0, out.stderr
    assert "highlight_pdf.py" in out.stdout and "--phrase" in out.stdout


def test_run_finds_scripts_by_name_and_refuses_unknown_ones() -> None:
    ok = run_sc("run", "md_to_txt.py", "--help")
    assert ok.returncode == 0, ok.stderr
    assert "md_to_txt.py" in ok.stdout
    missing = run_sc("run", "no_such_script.py")
    assert missing.returncode == 2
    assert "no script" in missing.stderr


def base_interpreter() -> str | None:
    """An interpreter that is not the project's, if this machine has one."""
    base = getattr(sys, "_base_executable", None)
    if base and Path(base).exists() and sys.prefix != sys.base_prefix:
        return str(base)
    return None


def test_bare_python_script_hops_into_the_project_environment() -> None:
    base = base_interpreter()
    if base is None:
        pytest.skip("not running in a virtual environment; nothing to hop into")
    env = {k: v for k, v in os.environ.items() if k not in ("PROSAIC_PYTHON", "PROSAIC_PY_HOP")}
    env["PROSAIC_PYTHON"] = sys.executable
    script = REPO_ROOT / "pleading" / "pleadings_manifest.py"
    out = subprocess.run(
        [base, str(script), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert out.returncode == 0, out.stderr
    assert "re-running under the project environment" in out.stderr
    assert "`sc pleadings-manifest`" in out.stderr


def doctor_env(tmp_path: Path, platform: str, manager: str | None) -> dict[str, str]:
    """An environment where nothing but an optional fake package manager is on PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    if manager:
        fake = bindir / manager
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
    return {
        "HOME": str(tmp_path),
        "PATH": str(bindir),
        "PROSAIC_PLATFORM": platform,
        "PROSAIC_PYTHON": sys.executable,
    }


@pytest.mark.parametrize(
    ("platform", "manager", "hint"),
    [
        ("darwin", None, "brew install poppler"),
        ("linux", "apt-get", "sudo apt install poppler-utils"),
    ],
)
def test_doctor_names_the_fix_for_a_missing_program(
    tmp_path: Path, platform: str, manager: str | None, hint: str
) -> None:
    out = run_sc("doctor", env=doctor_env(tmp_path, platform, manager))
    assert out.returncode == 1, out.stdout + out.stderr
    assert re.search(r"MISSING\s+pdftotext\s+" + re.escape(hint), out.stdout), out.stdout
    assert "Not ready" in out.stderr
    # Stock programs are confirmed, not installed.
    assert "Stock programs assumed present" in out.stdout


def test_doctor_reports_the_environment_and_packages() -> None:
    out = run_sc("doctor")
    assert "packages" in out.stdout
    assert "fitz" in out.stdout or "pymupdf" in out.stdout
