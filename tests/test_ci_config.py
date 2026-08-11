"""The checks CI runs must still be runnable.

Every failure this module guards against has already happened once, in
the commit that removed the typed library. All three were visible in the
repository's own configuration and none were caught until CI:

- `[tool.mypy]` kept `plugins = ["pydantic.mypy"]` after pydantic left
  the dependency list, so mypy aborted before checking anything.
- The workflow ran `mypy prosaic tests` against a directory that had
  been deleted.
- `--no-cov` stayed in the pre-push hook, a test subprocess, and three
  documents after pytest-cov was removed, where it stopped being a
  no-op and became an unrecognized-argument error.

The common shape is configuration naming something that no longer
exists. That is checkable without running anything, which matters
because the local environment can hide it: `uv run` does not prune, so
a machine that had the dependency before a removal keeps passing. CI
runs `uv sync --locked`, which does prune, and finds out.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Flags that only exist while a pytest plugin is installed. A flag left
# behind after its plugin is removed is not ignored; it is a hard error.
PLUGIN_FLAGS = {
    "--cov": "pytest-cov",
    "--no-cov": "pytest-cov",
    "--cov-report": "pytest-cov",
}


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _declared_distributions() -> set[str]:
    """Every distribution this project declares, runtime or dev, normalized."""
    cfg = _pyproject()
    names: set[str] = set()
    groups = [cfg.get("project", {}).get("dependencies", [])]
    groups += list(cfg.get("dependency-groups", {}).values())
    for group in groups:
        for spec in group:
            if not isinstance(spec, str):
                continue
            name = re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0]
            names.add(name.strip().lower().replace("_", "-"))
    return names


def _ci_run_steps() -> list[str]:
    doc: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps: list[str] = []
    for job in doc.get("jobs", {}).values():
        for step in job.get("steps", []):
            if isinstance(step, dict) and "run" in step:
                steps.append(step["run"])
    assert steps, "no run steps found in the CI workflow"
    return steps


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / p for p in out.split("\0") if p]


def _is_tracked(token: str) -> bool:
    """Is this a path git actually tracks?

    Deliberately not ``Path.exists()``. Deleting a package leaves its
    ``__pycache__`` behind, so the directory still exists on disk long
    after the code is gone -- which is exactly the state this check
    exists to catch, and exactly the state that would make an
    exists()-based check pass.
    """
    target = (REPO_ROOT / token).resolve()
    for tracked in _tracked_files():
        if tracked.resolve() == target or target in tracked.resolve().parents:
            return True
    return False


# --- configuration may not name what does not exist -------------------


def test_mypy_plugins_are_declared_dependencies() -> None:
    """A plugin whose distribution is not declared aborts mypy on a clean
    install, before a single file is checked."""
    plugins = _pyproject().get("tool", {}).get("mypy", {}).get("plugins", [])
    declared = _declared_distributions()
    for plugin in plugins:
        dist = plugin.split(".")[0].lower().replace("_", "-")
        assert dist in declared, (
            f"[tool.mypy] loads plugin {plugin!r}, but {dist!r} is not in "
            "[project.dependencies] or a dependency group. On a clean "
            "install mypy will abort with 'Error importing plugin'."
        )


def test_ci_commands_reference_paths_that_exist() -> None:
    """`mypy prosaic tests` outlived the directory it named."""
    tool_args = {"ruff", "mypy", "pytest", "check", "format"}
    missing = []
    for run in _ci_run_steps():
        for line in run.splitlines():
            if "uv run" not in line:
                continue
            for token in line.split():
                looks_like_path = (
                    not token.startswith("-")
                    and token not in tool_args
                    and token not in {"uv", "run", "&&"}
                    and "=" not in token
                    and (Path(token).suffix in {"", ".py"} or "/" in token)
                )
                if looks_like_path and not _is_tracked(token):
                    missing.append((line.strip(), token))
    assert not missing, "CI runs a command against a path that does not exist:\n" + "\n".join(
        f"  {line}  ->  {token}" for line, token in missing
    )


@pytest.mark.parametrize(("flag", "dist"), sorted(PLUGIN_FLAGS.items()))
def test_plugin_only_flags_are_not_left_behind(flag: str, dist: str) -> None:
    """`--no-cov` is a no-op only while pytest-cov is installed. Once it is
    removed the flag fails the command, which is how it took out the
    pre-push hook and a test's own subprocess at the same time."""
    if dist in _declared_distributions():
        pytest.skip(f"{dist} is declared; {flag} is valid")

    offenders = []
    for path in _tracked_files():
        if path == Path(__file__) or not path.is_file():
            continue
        # ADRs are historical records, "never edited after acceptance"
        # (design/README.md). One naming a flag it recorded the removal of
        # is correct, not stale.
        if path.is_relative_to(REPO_ROOT / "design" / "adr"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            if flag in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{n}")
    assert not offenders, (
        f"{flag} requires {dist}, which is no longer declared. It is still "
        "used in:\n" + "\n".join(f"  {o}" for o in offenders)
    )
