# 0050 — Project tools run through `sc`, under the project environment

**Status:** accepted (2026-11)

## Context
Every Python tool here needs packages a stock interpreter lacks:
PyMuPDF, pypdf, reportlab, PyYAML. The instructions agents follow ---
the workspace contract, the matter template, the skills, the specs ---
said `python3 <prosaic>/pleading/ocr_supplement.py ...`. On macOS that
`python3` is Apple's 3.9 with none of those packages, so the
instruction failed at `import fitz`, every time, in every session that
followed it. The agent then improvised: hunted for an interpreter that
happened to work, or installed packages into whatever Python it found.
`sc` itself survived only by accident, re-executing under the first
interpreter that had PyYAML, which on one machine also had PyMuPDF.

The same gap existed one layer down. The binaries the pipeline needs
(ocrmypdf, tesseract, poppler) were declared (ADR-0013) and `sc deps`
probed them, but nothing told a new user how to get the *Python*
half, and nothing said which programs prosaic may simply assume.

## Decision
The project is self-contained: anything beyond the stock programs of
macOS and Debian/Ubuntu is reached through prosaic.

1. **One interpreter, decided in one place.**
   `pleading/project_python.py` resolves it: `$PROSAIC_PYTHON` if set,
   else `<checkout>/.venv/bin/python` if it exists, else the running
   interpreter (the container, which installs system-wide). `sc`
   re-executes itself under that interpreter before doing anything, so
   every subcommand's `sys.executable` is the right one. The sync and
   supervisor shell helpers and `cli/agent-run` put the same
   environment first in their probes.
2. **Every tool a person or agent runs by hand has an `sc` route.**
   Existing pass-throughs (`form`, `attest`, `phone`, ...) stay; the
   scripts that were only reachable by path get thin pass-throughs
   (`sc ocr`, `highlight`, `redact`, `verify-redactions`,
   `check-redaction-schedule`, `pleadings-manifest`, `pleadings-scan`,
   `read-coverage`, `phone-logs`) whose arguments and `--help` go
   straight to the script. Anything else is `sc run <script>`, and
   one-off work that needs the packages is `sc python`.
3. **Instructions name only `sc`.** No document an agent executes
   tells it to run bare `python3`, `pip`, or a script by path.
   `tests/test_tool_routing.py` enforces this over the matter
   contracts, skills, specs and docs.
4. **Bare invocations still work.** The entry-point scripts under
   `pleading/` and `triage/` call `project_python.ensure()` under
   `__main__`: run by a stock `python3`, they re-execute under the
   project interpreter and print one line naming the `sc` route.
   Instructions written before this decision live in matters and
   overlays prosaic cannot edit; they keep working rather than failing
   at an import.
5. **Setup and diagnosis are commands.** `sc setup` creates or updates
   the environment (`uv sync --locked`; without uv, a venv from
   `pleading/requirements.txt`) and then runs `sc doctor`. `sc doctor`
   checks the interpreter, the packages, every declared program and
   every assumed stock program, and prints the exact install command
   for the host --- Homebrew on macOS, apt on Debian/Ubuntu.
6. **Stock programs are a declared list too.** `system-dependencies.yaml`
   gains a `stock:` section: what prosaic assumes a fresh macOS or
   Debian/Ubuntu install provides (sh, bash, env, sed, awk, grep, find,
   curl; `open`/`shasum`/`launchctl` on macOS, `sha256sum` on Linux).
   Where the platforms differ, code picks per platform (`sc open` uses
   `open` or `xdg-open`) and instructions prefer an `sc` command
   (`sc attest hash`) over either spelling.

Debian/Ubuntu is the Linux prosaic designs around. Its differences
are handled in the manifest and in code: `python3-venv` is a separate
package (setup says so), `npm` is separate from `nodejs`, uv is not
in the archive (doctor prints Astral's installer), `xdg-open` comes
from `xdg-utils`, and poppler's tools come from `poppler-utils`.

## Consequences
An agent that reads any instruction in this repository runs a command
that works on the first try, and a stale instruction elsewhere costs
one stderr line instead of a failed import. A fresh clone is two
commands from working: `cli/sc setup`, then whatever `sc doctor` says
to install.

`sc` now always runs under the project environment when one exists,
which means a developer who deliberately ran it under some other
interpreter must say so with `PROSAIC_PYTHON`. The hop also costs one
`exec` at startup, which is negligible beside importing PyMuPDF.

Speech-to-text's multi-voice pipeline (WhisperX in its own conda
environment) remains outside this: its dependency stack conflicts
with the project's and it is optional. docs/stt.md says so.
