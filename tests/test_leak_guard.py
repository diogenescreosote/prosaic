"""Fail the build if material from the author's prior matter appears anywhere.

prosaic replaces an earlier private tool that was built around one real case
in a different practice area. Nothing from that case — party names, form
numbers, statutory citations, domain vocabulary — may appear in this
repository. This test walks every git-tracked file and every commit message
and fails on a denylist of patterns associated with the prior domain.

The committed denylist below covers vocabulary and identifier shapes. Personal
names are checked from an optional, gitignored ``.leakguard.local`` file (one
literal string per line, matched case-insensitively) so they are enforced
locally without themselves being committed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
THIS_FILE = Path(__file__).resolve()

# Identifier shapes and vocabulary from the prior practice area. Kept broad on
# purpose: a false positive costs a minute; a false negative is a disclosure.
FORBIDDEN_PATTERNS = [
    re.compile(rb"FL-\d{3}"),
    re.compile(rb"DV-\d{3}"),
    re.compile(rb"GC-\d{3}"),
    re.compile(rb"OurFamilyWizard", re.IGNORECASE),
    re.compile(rb"Family\s+Code", re.IGNORECASE),
    # (?!ian) spares "custodian of records", the statutory term in civil
    # subpoena practice (CCP 1985.3, 2020.410); custody/custodial still match.
    re.compile(rb"custod(?!ian)", re.IGNORECASE),
    re.compile(rb"visitation", re.IGNORECASE),
    re.compile(rb"co-?parent", re.IGNORECASE),
    re.compile(rb"minor\s+child", re.IGNORECASE),
    re.compile(rb"restraining\s+order", re.IGNORECASE),
]

LOCAL_DENYLIST = REPO_ROOT / ".leakguard.local"


def _local_patterns() -> list[re.Pattern[bytes]]:
    if not LOCAL_DENYLIST.exists():
        return []
    lines = LOCAL_DENYLIST.read_text().splitlines()
    return [
        re.compile(re.escape(line.strip().encode()), re.IGNORECASE)
        for line in lines
        if line.strip() and not line.startswith("#")
    ]


def _all_patterns() -> list[re.Pattern[bytes]]:
    return FORBIDDEN_PATTERNS + _local_patterns()


def _git(*argv: str) -> bytes:
    return subprocess.run(["git", *argv], cwd=REPO_ROOT, capture_output=True, check=True).stdout


def _tracked_files() -> list[Path]:
    names = _git("ls-files", "-z").split(b"\0")
    return [REPO_ROOT / name.decode() for name in names if name]


def test_tracked_files_contain_no_prior_matter_content() -> None:
    violations: list[str] = []
    for path in _tracked_files():
        if path == THIS_FILE:
            continue  # the denylist itself necessarily contains its patterns
        content = path.read_bytes()
        violations.extend(
            f"{path.relative_to(REPO_ROOT)}: matches {pattern.pattern!r}"
            for pattern in _all_patterns()
            if pattern.search(content)
        )
    assert not violations, "leaked content:\n" + "\n".join(violations)


def test_commit_messages_contain_no_prior_matter_content() -> None:
    log = _git("log", "--all", "--format=%H%n%B%n---")
    violations = [
        f"commit log matches {pattern.pattern!r}"
        for pattern in _all_patterns()
        if pattern.search(log)
    ]
    assert not violations, "leaked content:\n" + "\n".join(violations)
