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

A denylist only catches what someone thought to list. The documentation
examples in this repository were first written against live matters, and what
they carried through was not vocabulary at all: a real person's name and work
email in a proof-of-service example, real exhibit shortnames, a real case
number, and a real courthouse. No pattern above would have fired on any of
it. So two of the checks below are allowlists instead — an email address or a
case number that is not recognizably a placeholder fails, and adding a real
one means arguing for it in this file rather than merely not being noticed.
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
    # Bounded: a short surname is otherwise a substring of ordinary words
    # ("Ross" inside "across"), and a guard that cries wolf gets muted.
    return [
        re.compile(rb"\b" + re.escape(line.strip().encode()) + rb"\b", re.IGNORECASE)
        for line in lines
        if line.strip() and not line.startswith("#")
    ]


def _all_patterns() -> list[re.Pattern[bytes]]:
    return FORBIDDEN_PATTERNS + _local_patterns()


def _git(*argv: str) -> bytes:
    return subprocess.run(["git", *argv], cwd=REPO_ROOT, capture_output=True, check=True).stdout


def _tracked_files() -> list[Path]:
    names = _git("ls-files", "-z").split(b"\0")
    # A submodule appears in ls-files as a gitlink whose path is a
    # directory; its contents are another repository's problem.
    return [p for name in names if name if (p := REPO_ROOT / name.decode()).is_file()]


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


# --- allowlists: what a public repository is allowed to contain ------------

#: Addresses that may appear here. Everything else is presumed real.
ALLOWED_EMAILS = frozenset(
    {
        "andrewpcone@gmail.com",  # the author's own published contact
    }
)

#: Case numbers used by the fictional examples and fixtures. A number not on
#: this list is presumed to belong to a real proceeding.
ALLOWED_CASE_NUMBERS = frozenset(
    {
        "24CV00000",
        "24CV000123",
        "26CV00123",
        "26CV012345",
        "23CV135875",
    }
)

EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CASE_NUMBER = re.compile(rb"\b\d{2}[A-Z]{2,4}\d{4,6}\b")

#: Read as bytes and searched; these carry no prose worth searching and
#: produce false positives from binary noise.
BINARY_SUFFIXES = {".pdf", ".ttf", ".otf", ".png", ".jpg", ".jpeg", ".ico"}


def _placeholder_domain(domain: str) -> bool:
    """RFC 2606 reserved names and the `examplefirm.com` style built on them."""
    return any(
        label == "example" or label.startswith("example") for label in domain.lower().split(".")
    )


def _text_files() -> list[Path]:
    return [p for p in _tracked_files() if p.suffix.lower() not in BINARY_SUFFIXES]


def test_email_addresses_are_placeholders() -> None:
    """Every address is a documentation placeholder, or explicitly allowed."""
    violations: list[str] = []
    for path in _text_files():
        if path == THIS_FILE:
            continue
        for match in EMAIL.finditer(path.read_bytes()):
            address = match.group().decode()
            if address in ALLOWED_EMAILS or _placeholder_domain(address.split("@", 1)[1]):
                continue
            violations.append(f"{path.relative_to(REPO_ROOT)}: {address}")
    assert not violations, (
        "real-looking email addresses in tracked files:\n"
        + "\n".join(violations)
        + "\n\nUse an example.com/.org address, or add it to ALLOWED_EMAILS "
        "with a reason."
    )


def test_case_numbers_are_fictional() -> None:
    """No case number outside the fictional set used by the examples."""
    violations: list[str] = []
    for path in _text_files():
        if path == THIS_FILE:
            continue
        for match in CASE_NUMBER.finditer(path.read_bytes()):
            number = match.group().decode()
            if number in ALLOWED_CASE_NUMBERS:
                continue
            violations.append(f"{path.relative_to(REPO_ROOT)}: {number}")
    assert not violations, (
        "case numbers that are not from the fictional set:\n"
        + "\n".join(violations)
        + "\n\nUse one of ALLOWED_CASE_NUMBERS, or add the new fictional "
        "number to that set."
    )
