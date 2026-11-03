# Installing the dependencies

## The short version

```bash
cli/sc setup        # the Python environment, from uv.lock
cli/sc doctor       # what else is missing, and the command that installs it
```

Then run everything through `sc`. **Never run a project tool with bare
`python3`, and never `pip install` into a system Python to make one
work** ([ADR-0050](../design/adr/0050-project-tools-run-through-sc.md)).
The stock `python3` on macOS is Apple's, without PyMuPDF or pypdf; the
project's interpreter is `<checkout>/.venv/bin/python`, and `sc`
always runs under it:

| Instead of | Run |
|---|---|
| `python3 pleading/ocr_supplement.py a.pdf out/` | `sc ocr a.pdf out/` |
| `python3 pleading/highlight_pdf.py ...` | `sc highlight ...` |
| `python3 pleading/redact_pdf.py cfg.json` | `sc redact cfg.json` |
| `python3 pleading/verify_redactions.py ...` | `sc verify-redactions ...` |
| `python3 pleading/check_redaction_schedule.py ...` | `sc check-redaction-schedule ...` |
| `python3 pleading/pleadings_manifest.py <matter>` | `sc pleadings-manifest <matter>` |
| `python3 pleading/pleadings_scan.py <matter>` | `sc pleadings-scan <matter>` |
| `python3 triage/read_coverage.py ...` | `sc read-coverage ...` |
| `python3 triage/phone_logs.py ...` | `sc phone-logs ...` |
| `python3 <any other script>.py ...` | `sc run <script>.py ...` |
| `python3 -c 'import fitz; ...'` | `sc python -c 'import fitz; ...'` |
| `pip install <pkg>` | add it to `pyproject.toml`, `uv lock`, `sc setup` |

A script run the old way still works: it notices it is under the wrong
interpreter, re-executes under the project's, and prints one line
naming the `sc` command to use next time.

## The three layers

prosaic has three layers of dependency and one file for each:

| Layer | Declared in | Installed with |
|---|---|---|
| Python | `pyproject.toml` (+ `uv.lock`) | `uv sync` |
| Node | `connectors/package.json` | `cd connectors && npm ci` |
| System binaries | `system-dependencies.yaml` | `sc deps` tells you |

`pleading/requirements.txt` still lists what the pleading pipeline
alone needs, so that tree stays installable on its own — the container
uses it, and it is a subset of what `uv sync` gives you. `uv sync` is
the supported path for the repository as a whole.

The third one is the one that used to bite. The pipeline shells out to
ocrmypdf, tesseract, poppler's `pdftotext`, and a browser; none of
those belong to either package file, so until
[ADR-0013](../design/adr/0013-system-dependencies-declared-once.md)
they lived in a paragraph of prose that was already out of date.

## Checking what you have

```bash
sc deps
```

Every binary that applies to your platform, whether it is present, and
for anything missing, the command that installs it:

```
  ok       python3        runs the CLI, the pleading generator, and the form fillers
  MISSING  pdftotext      brew install poppler
  --       whisper-cli    brew install whisper-cpp
```

`ok` is present, `MISSING` is a required tool that is absent — the
command exits non-zero — and `--` is an optional one you can ignore
until you want the feature it serves. `OLD` means present but below
the minimum version.

To install everything at once:

```bash
brew install $(sc deps --format brew)          # macOS
sudo apt install $(sc deps --format apt)       # Debian/Ubuntu
```

`sc doctor` is the fuller check: the project environment and its
packages first, then the same programs as `sc deps`, then the stock
programs prosaic assumes, then the connectors' Node modules. It prints
the fix for every gap in the host's terms and exits non-zero until
nothing required is missing.

## What prosaic assumes, and what it provides

Two lists, both in `system-dependencies.yaml`:

- **`stock:`** --- programs a fresh install of macOS or Debian/Ubuntu
  already has, which prosaic never installs: `sh`, `bash`, `env`,
  `sed`, `awk`, `grep`, `find`, `curl`; on macOS `open`, `shasum`,
  `launchctl` (and `security`, `osascript`); on Linux `sha256sum`.
  Instructions and code stay inside that set, and where the platforms
  spell a tool differently the code chooses (`sc open` runs `open` or
  `xdg-open`). For a hash in an instruction, use `sc attest hash`
  rather than either `shasum -a 256` or `sha256sum`.
- **`dependencies:`** --- everything else, each with its Homebrew and
  apt package. `sc doctor` checks them; nothing else should be assumed.

### Debian and Ubuntu

Debian/Ubuntu is the Linux prosaic designs around. The differences
from macOS that matter, all handled in the manifest or the code:

| | macOS | Debian/Ubuntu |
|---|---|---|
| Python venv support | built in | `sudo apt install python3-venv` (only without uv) |
| uv | `brew install uv` | not in the archive: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| npm | with `node` | separate `npm` package |
| poppler (`pdftotext`, `pdftoppm`, `pdfinfo`) | `poppler` | `poppler-utils` |
| tesseract + English data | `tesseract` | `tesseract-ocr-eng` |
| open a file in the viewer | `open` (stock) | `xdg-open` from `xdg-utils` |
| SHA-256 on the command line | `shasum -a 256` (stock) | `sha256sum` (coreutils) |
| credentials | Keychain (`security`) | the `env` backend (ADR-0012) |
| scheduling | `launchd` via `sc schedule` | not yet supported |

## The container

The image is the dependency set assembled and proven — the same
manifest, resolved:

```bash
docker build -t prosaic .
```

Run it against a matter on the host. Mount the matter, and run as
yourself so the files it writes belong to you rather than to root:

```bash
docker run --rm -v ~/cases/smith-v-smith:/matter \
    --user "$(id -u):$(id -g)" \
    prosaic build responsive_declaration
```

Credentials come from the environment
([ADR-0012](../design/adr/0012-credential-reference-not-store.md)) —
there is no Keychain in a container:

```bash
docker run --rm -v ~/cases/smith-v-smith:/matter \
    -e PROSAIC_OFW_USERNAME -e PROSAIC_OFW_PASSWORD \
    prosaic sync /matter
```

Matters are always mounted, never built into the image. Privileged
material does not belong in a layer that can be pushed to a registry.

### Running the suite in it

```bash
docker run --rm --entrypoint python3 -w /opt/prosaic prosaic \
    -m pytest pleading/tests -q
```

The component tests pass in the container exactly as they do on
macOS, and an envelope built inside it is byte-identical to the same
envelope built on the host — same fonts, same layout, same bytes.

The tests under `tests/` that enumerate the repository
(`test_repo_hygiene.py`, `test_system_dependencies.py`) do **not**
run in the image: they walk `git ls-files`, and `.git` is excluded
from the build context on purpose. They belong to a clone, not to a
deployment, and the pre-push hook is where they matter.

### What the image is and isn't

**On Linux it is the deployment artifact.** Everything works.

**On macOS it is for development and CI.** A Linux container on macOS
runs inside a VM that cannot reach Metal, so GPU-accelerated
transcription has to run on the host regardless — which is why the
speech tools are marked `in_container: false` in the manifest and are
absent from the image on purpose. Transcribing privileged audio slowly
on a container CPU, with a worse result, is not an improvement over
running `whisper-cli` natively.

Also absent, deliberately:

- **The macOS Keychain.** Nothing to install; the `env` credential
  backend is what a container uses.
- **An agent CLI** (Claude Code, Codex, or Gemini), which the AI
  triage pass invokes through `cli/agent-run`. Claude Code installs from
  npm rather than a system package manager and needs credentials the
  image cannot carry. Everything except triage works without it.

## Adding a dependency

If you add a `subprocess.run(["something", ...])` or an
`execFileSync('something', ...)`, add the entry to
`system-dependencies.yaml` in the same change. This is enforced:
`tests/test_system_dependencies.py` fails on a program that is invoked
but not declared, and on an entry whose call site has gone away. The
Dockerfile takes its package list from `sc deps --format apt`, so
there is nothing else to update.
