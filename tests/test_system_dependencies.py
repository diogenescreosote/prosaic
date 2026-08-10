"""The system-dependency manifest has to match reality, both ways.

``system-dependencies.yaml`` only earns its place if it is complete
and true. Two ways it rots, and this file forbids both:

1. **A subprocess call lands undeclared.** Someone adds
   ``subprocess.run(["qpdf", ...])``, it works on their machine because
   ocrmypdf already pulled qpdf in, and the container — or the next
   contributor — discovers the dependency by way of a stack trace.
   This is the failure the manifest exists to prevent, so it is
   checked mechanically rather than trusted to review.

2. **An entry outlives its call site.** A dependency gets dropped from
   the code and stays in the manifest, so the image installs a package
   nothing uses and `sc deps` reports a missing tool that nothing
   needs. A manifest that over-declares stops being believed.

Only literal program names are checked. A call built from a variable
or ``sys.executable`` is invisible here, which is a known and accepted
hole: the realistic mistake is a hardcoded name, not a computed one.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "system-dependencies.yaml"

VALID_PLATFORMS = frozenset({"darwin", "linux"})

# Programs a call site may name without a manifest entry.
#
#   /bin/sh, /bin/bash  POSIX, and the thing running the script already
#   npm, npx            ship with node, which is declared
#   pip                 ships with the Python that is declared
#   sc                  prosaic's own CLI
EXEMPT = frozenset({"/bin/sh", "/bin/bash", "sh", "bash", "env", "npm", "npx", "pip", "pip3", "sc"})

# Where a program name can appear as the first argument of a call.
CALL_SITES = (
    # subprocess.run(["prog", ...]) / check_output / Popen / call
    re.compile(r"subprocess\.(?:run|check_output|check_call|call|Popen)\(\s*\[\s*[\"']([^\"']+)[\"']"),
    # execFileSync('prog', [...]) / spawnSync / execFile / spawn
    re.compile(r"(?:execFileSync|execFile|spawnSync|spawn)\(\s*[\"']([^\"']+)[\"']"),
)


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return [REPO_ROOT / p for p in out.stdout.split("\0") if p]


@pytest.fixture(scope="module")
def dependencies() -> list[dict]:
    return yaml.safe_load(MANIFEST.read_text())["dependencies"]


@pytest.fixture(scope="module")
def declared(dependencies) -> frozenset[str]:
    return frozenset(d["binary"] for d in dependencies)


def test_every_entry_is_completely_specified(dependencies):
    """A half-filled entry is worse than none: it reads as considered."""
    for dep in dependencies:
        binary = dep.get("binary")
        assert binary, f"entry with no binary: {dep}"
        for field in ("why", "used_by", "required", "platforms", "in_container"):
            assert field in dep, f"{binary}: missing {field}"
        assert isinstance(dep["required"], bool), f"{binary}: required must be a bool"
        assert isinstance(dep["in_container"], bool), f"{binary}: in_container must be a bool"
        assert dep["used_by"], f"{binary}: used_by must name at least one call site"
        unknown = set(dep["platforms"]) - VALID_PLATFORMS
        assert not unknown, f"{binary}: unknown platform(s) {sorted(unknown)}"
        # A package for some manager, or a stated reason there is
        # none. `security` ships with macOS; `claude` comes from npm.
        # Silence is the thing being forbidden: an entry with three
        # nulls and no explanation is indistinguishable from one
        # somebody stopped filling in halfway.
        assert (
            dep.get("apt") or dep.get("brew") or dep.get("npm")
            or dep.get("no_package_reason")
        ), f"{binary}: no package for any manager and no no_package_reason"


def test_container_entries_have_an_apt_package(dependencies):
    """`sc deps --format apt` is what the Dockerfile installs."""
    for dep in dependencies:
        if dep["in_container"]:
            assert dep.get("apt"), (
                f"{dep['binary']}: in_container is true but there is no apt "
                f"package, so the image would silently omit it"
            )
            assert "linux" in dep["platforms"], (
                f"{dep['binary']}: in_container is true but the entry does "
                f"not apply to linux"
            )


def test_no_undeclared_subprocess_calls(declared):
    """A program invoked by name must be in the manifest."""
    undeclared: list[str] = []
    for path in tracked_files():
        if path.suffix not in {".py", ".js", ".sh"} and path.name != "sc":
            continue
        # This file names programs it does not run — the patterns
        # above, and the example in the docstring.
        if path in (MANIFEST, Path(__file__).resolve()):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for pattern in CALL_SITES:
            for match in pattern.finditer(text):
                prog = match.group(1)
                if prog in EXEMPT or prog in declared:
                    continue
                # A path into the repo is prosaic calling itself.
                if "/" in prog and not prog.startswith("/"):
                    continue
                rel = path.relative_to(REPO_ROOT)
                undeclared.append(f"{rel}: {prog}")

    assert not undeclared, (
        "these programs are invoked but not declared in "
        f"system-dependencies.yaml:\n  " + "\n  ".join(sorted(set(undeclared)))
    )


def test_no_phantom_entries(dependencies):
    """Every declared binary is named somewhere outside the manifest."""
    corpus: list[tuple[Path, str]] = []
    for path in tracked_files():
        if path == MANIFEST:
            continue
        try:
            corpus.append((path, path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue

    orphans = []
    for dep in dependencies:
        binary = dep["binary"]
        word = re.compile(rf"(?<![\w-]){re.escape(binary)}(?![\w-])")
        if not any(word.search(text) for _, text in corpus):
            orphans.append(binary)

    assert not orphans, (
        "declared in system-dependencies.yaml but referenced nowhere else "
        f"in the tree: {sorted(orphans)}"
    )


def test_dockerfile_installs_from_the_manifest():
    """The package list must be computed, never transcribed.

    A hand-written apt line in the Dockerfile is a second copy of the
    manifest, and the copy is what drifts.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    assert "sc deps --format apt" in dockerfile

    for line in dockerfile.splitlines():
        stripped = line.strip()
        if "apt-get install" not in stripped or stripped.startswith("#"):
            continue
        # The bootstrap layer is allowed a literal list: it installs
        # only what is needed to read the manifest at all.
        bootstrap = {"ca-certificates", "python3", "python3-venv"}
        args = stripped.split("apt-get install", 1)[1].split()
        packages = {a for a in args if not a.startswith("-") and a not in {"&&", "\\"}}
        if "$(sc" in stripped or "$(cli/sc" in stripped:
            continue
        assert packages <= bootstrap, (
            f"Dockerfile hardcodes packages outside the bootstrap set: "
            f"{sorted(packages - bootstrap)} — add them to "
            f"system-dependencies.yaml instead"
        )
