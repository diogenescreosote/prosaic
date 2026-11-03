"""The project's Python interpreter: one answer, used everywhere (ADR-0050).

Every Python tool in this repository needs packages the stock
interpreter does not carry (PyMuPDF, pypdf, reportlab, PyYAML). The
supported way to run one is through ``sc``, which runs under the
project's virtual environment; ``sc setup`` creates that environment
and ``sc doctor`` says whether it is healthy.

This module is the only place that decides which interpreter that is,
so ``sc``, the scripts run by path, and the shell helpers cannot
disagree:

1. ``$PROSAIC_PYTHON``, when set: an explicit choice (CI, the
   container, an unusual install) always wins.
2. ``<repo>/.venv/bin/python``, when it exists: what ``uv sync`` and
   ``sc setup`` create.
3. Otherwise the running interpreter, which is all a container that
   installed the requirements system-wide has.

``ensure()`` is the safety net for the scripts. Instructions that hand
a script path to the stock ``python3`` predate this decision and still
exist in matters and overlays; run that way, the stock interpreter
fails at ``import fitz``. A script that calls ``ensure()``
under ``if __name__ == "__main__"`` re-executes itself under the
project interpreter instead, says so once on stderr, and names the
``sc`` route to use next time. Imported as a module (the tests do),
it does nothing.

Standard library only: it runs before anything else is importable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: The repository root: this file lives in <root>/pleading/.
ROOT = Path(__file__).resolve().parent.parent

#: Where the environment lives, relative to the root. uv's default, and
#: what `sc setup` creates when uv is absent.
VENV_DIR = ".venv"

#: Set on the re-executed process so a misconfigured target can never
#: loop.
HOP_GUARD = "PROSAIC_PY_HOP"


def venv_dir(root: Path = ROOT) -> Path:
    return root / VENV_DIR


def venv_python(root: Path = ROOT) -> Path | None:
    """The environment's interpreter, if the environment exists."""
    for name in ("python", "python3"):
        cand = venv_dir(root) / "bin" / name
        if cand.exists():
            return cand
    return None


def project_python(root: Path = ROOT) -> str:
    """The interpreter every project tool should run under."""
    explicit = os.environ.get("PROSAIC_PYTHON")
    if explicit:
        return explicit
    venv = venv_python(root)
    if venv is not None:
        return str(venv)
    return sys.executable


def running_project_python(root: Path = ROOT) -> bool:
    """True when this process already runs under ``project_python()``.

    Compared by environment, not by binary: a venv's ``bin/python`` is a
    symlink to the base interpreter, so the resolved paths are equal
    whether or not the venv is active, while ``sys.prefix`` is not.
    """
    target = project_python(root)
    if target == sys.executable:
        return True
    explicit = os.environ.get("PROSAIC_PYTHON")
    if explicit:
        return os.path.abspath(explicit) == os.path.abspath(sys.executable)
    try:
        return Path(sys.prefix).resolve() == venv_dir(root).resolve()
    except OSError:
        return False


def ensure(script: str, route: str | None = None, quiet: bool = False) -> None:
    """Re-exec ``script`` under the project interpreter if not already in it.

    ``route`` is the ``sc`` command that runs this script, named in the
    one-line notice so the caller learns the supported form.
    """
    if running_project_python():
        # Arrived. Drop the guard so a child this process spawns can
        # still hop on its own account.
        os.environ.pop(HOP_GUARD, None)
        return
    if os.environ.get(HOP_GUARD):
        return  # already hopped once and still not there: never loop
    target = project_python()
    if not os.path.exists(target) and os.path.sep in target:
        return
    if not quiet:
        how = f"`sc {route}`" if route else "`sc run " + os.path.basename(script) + "`"
        sys.stderr.write(
            f"note: re-running under the project environment ({target}); "
            f"use {how} instead of bare python3 (ADR-0050)\n"
        )
    os.environ[HOP_GUARD] = "1"
    os.execv(target, [target, os.path.abspath(script), *sys.argv[1:]])
