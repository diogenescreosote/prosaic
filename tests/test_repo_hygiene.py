"""Public-repo hygiene: no machine-specific paths, no secrets.

prosaic is a public repository built out of a private system, so
the failure mode is not exotic — a plausible fix hardcodes the path
that happened to work on the author's laptop, and the username ships.
That is exactly how ``/Users/<someone>/miniforge3/bin/python3`` reached
``sync/matter_sync.sh`` three commits after a manual sanitization pass
declared the tree clean.

Manual passes do not hold. This one runs in the suite, so a leak fails
a test instead of surviving to a push.

Two rules, both enforced over ``git ls-files``:

1. No absolute path into a specific user's home directory. These are
   also a portability bug — the point of Phase 1 is that nothing
   assumes a machine — so a hit here is worth fixing on its own merits
   even when the username is innocuous.
2. No credential material. Cheap shape-matching on the well-known
   prefixes, not a real scanner; it catches paste accidents, which is
   the realistic threat.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Placeholder home directories that are obviously illustrative. Docs
# legitimately say "/home/you/matters"; only real accounts are leaks.
GENERIC_HOME_NAMES = frozenset(
    {
        "you", "user", "username", "someone", "me", "yourname", "your-name",
        "alice", "bob", "jane", "jdoe", "example", "USER", "HOME",
        # Synthetic HOME used by tests that need a fixed base to compare
        # resolved directories against (tests/test_platform_seams.py).
        "testuser", "testhome",
    }
)

# Service accounts that CI runs as. The username check below asks "does
# the author's account name appear in the tree?"; on a hosted runner the
# answer is about a shared build account whose name is also an ordinary
# English word ("runner" matches `runner.invoke`, `runner_shim.c`, and
# every use of the word in prose). Skipping them costs nothing: a leak
# of the author's username is what the check exists for, and that check
# runs on the author's machine and in the pre-push hook.
CI_ACCOUNT_NAMES = frozenset(
    {"runner", "ubuntu", "vagrant", "circleci", "jenkins", "docker",
     "admin", "build", "github", "travis", "buildkite"}
)

HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9._$<{-][^/\s\"'`,;:)\]}]*)")

# Shape-matched credential prefixes. Deliberately narrow: a pattern
# that fires on ordinary prose is a pattern that gets muted.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"BEGIN (?:[A-Z ]+ )?PRIVATE KEY")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
)

# This file necessarily contains the patterns it searches for.
SELF = Path(__file__).resolve()

BINARY_SUFFIXES = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".zst", ".m4a",
     ".mp3", ".wav", ".bin", ".ico", ".woff", ".woff2", ".ttf", ".otf"}
)


def _tracked_text_files() -> list[Path]:
    """Every tracked file git will actually publish, minus binaries."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths = []
    for rel in filter(None, out.split("\0")):
        path = REPO_ROOT / rel
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        if path.resolve() == SELF:
            continue
        paths.append(path)
    return paths


def _read(path: Path) -> list[str] | None:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return None  # undeclared binary; nothing to scan


@pytest.fixture(scope="module")
def tracked_files() -> list[Path]:
    files = _tracked_text_files()
    assert files, "git ls-files returned nothing — is this a work tree?"
    return files


def test_no_user_specific_home_paths(tracked_files: list[Path]) -> None:
    """No absolute path into a real user's home directory.

    Both a privacy leak and a portability bug. Use $HOME, an XDG
    resolver, or a discovery probe instead.
    """
    findings = []
    for path in tracked_files:
        lines = _read(path)
        if lines is None:
            continue
        for lineno, line in enumerate(lines, start=1):
            for match in HOME_PATH.finditer(line):
                name = match.group(1)
                if name in GENERIC_HOME_NAMES:
                    continue
                # $HOME, ${HOME}, <your-name>, ~ — already parameterized.
                if name[0] in "$<{~":
                    continue
                rel = path.relative_to(REPO_ROOT)
                findings.append(f"  {rel}:{lineno}: {match.group(0)}")

    assert not findings, (
        "Machine-specific home paths in tracked files:\n"
        + "\n".join(findings)
        + "\n\nReplace with $HOME, an XDG path resolver, or runtime discovery."
    )


def test_no_current_username_anywhere(tracked_files: list[Path]) -> None:
    """Catch this machine's account name in any form, path or not.

    Complements the path check: a username can leak through a log
    sample, a comment, or an example command line just as easily as
    through an absolute path.
    """
    username = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if len(username) < 4 or username in GENERIC_HOME_NAMES | CI_ACCOUNT_NAMES:
        pytest.skip(f"username {username!r} too generic to match safely")

    pattern = re.compile(rf"\b{re.escape(username)}\b")
    findings = []
    for path in tracked_files:
        lines = _read(path)
        if lines is None:
            continue
        for lineno, line in enumerate(lines, start=1):
            if pattern.search(line):
                rel = path.relative_to(REPO_ROOT)
                findings.append(f"  {rel}:{lineno}: {line.strip()[:100]}")

    assert not findings, (
        f"This machine's username ({username!r}) appears in tracked files:\n"
        + "\n".join(findings)
    )


def test_no_credential_material(tracked_files: list[Path]) -> None:
    """No key or token shapes in tracked files."""
    findings = []
    for path in tracked_files:
        lines = _read(path)
        if lines is None:
            continue
        for lineno, line in enumerate(lines, start=1):
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    findings.append(f"  {rel}:{lineno}: possible {label}")

    assert not findings, (
        "Possible credential material in tracked files:\n"
        + "\n".join(findings)
        + "\n\nIf this is a false positive, narrow the pattern rather than"
        " muting the test. If it is real, the credential is compromised:"
        " rotate it, then rewrite history."
    )
