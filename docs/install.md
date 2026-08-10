# Installing the dependencies

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
- **Claude Code**, which the AI triage pass invokes. It installs from
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
