"""Documentation cannot silently fall behind the code.

Six `sc` subcommands were added across one working session — `paths`,
`clean`, `backup`, `commit-check`, `hooks`, `deps` — and not one of
them reached `specs/cli.md`. Nothing failed, because nothing was
checking. The docs were not wrong; they were merely eight commands
short, which reads exactly like being complete.

That is the same failure mode as `plain: true` (ADR-0018): a thing
that is silently absent is indistinguishable from a thing that is
fine. The answer is the same too — make it mechanical, because
"remember to update the docs" is what was already in place.

Deliberately narrow. These check that documentation *exists and is
reachable*, not that it is any good; no test can do the second. What
they buy is that adding a capability and forgetting to write it down
fails in the suite rather than surfacing months later when somebody
needs it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# --- the CLI surface ------------------------------------------------


def test_every_subcommand_has_a_promise_in_the_spec():
    """`specs/cli.md` states what each subcommand promises."""
    source = read("cli/sc")
    commands = set(re.findall(r'sub\.add_parser\("([a-z-]+)"', source))
    assert commands, "could not find any subcommands — has cli/sc changed shape?"
    spec = read("specs/cli.md")
    missing = sorted(c for c in commands if f"`sc {c}" not in spec)
    assert not missing, (
        f"these subcommands exist but specs/cli.md does not mention them: "
        f"{missing}. Add a promise for each — help text is not the spec."
    )


def test_spec_does_not_promise_commands_that_do_not_exist():
    """The reverse: a removed command must not linger as a promise."""
    source = read("cli/sc")
    commands = set(re.findall(r'sub\.add_parser\("([a-z-]+)"', source))
    spec = read("specs/cli.md")
    promised = set(re.findall(r"\*\*`sc ([a-z-]+)", spec))
    stale = sorted(promised - commands)
    assert not stale, (
        f"specs/cli.md promises subcommands that no longer exist: {stale}"
    )


# --- decisions ------------------------------------------------------


def test_every_adr_is_in_the_index():
    """An ADR nobody can find is an ADR nobody reads."""
    adrs = sorted((REPO_ROOT / "design" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    assert adrs, "no ADRs found"
    index = read("design/README.md")
    missing = [a.name for a in adrs if a.name not in index]
    assert not missing, (
        f"these ADRs are not listed in design/README.md: {missing}"
    )


def test_adr_numbers_are_unique_and_contiguous():
    """Two ADRs sharing a number means one of them got written blind."""
    numbers = sorted(
        int(p.name[:4])
        for p in (REPO_ROOT / "design" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")
    )
    duplicates = {n for n in numbers if numbers.count(n) > 1}
    assert not duplicates, f"duplicate ADR numbers: {sorted(duplicates)}"
    expected = list(range(1, len(numbers) + 1))
    assert numbers == expected, (
        f"ADR numbering has a gap: {sorted(set(expected) - set(numbers))}"
    )


def test_every_adr_states_a_status():
    for path in (REPO_ROOT / "design" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"):
        assert "**Status:**" in path.read_text(), f"{path.name} has no Status line"


# --- the manual -----------------------------------------------------


def test_every_doc_is_reachable_from_somewhere():
    """A page nothing links to will not be found when it is needed."""
    docs = sorted((REPO_ROOT / "docs").glob("*.md"))
    assert docs, "no docs found"
    corpus = ""
    for path in REPO_ROOT.rglob("*.md"):
        if path.parent.name == "docs" and path.suffix == ".md":
            # A doc linking only to itself does not count as reachable.
            continue
        corpus += path.read_text(encoding="utf-8", errors="replace")
    for extra in ("cli/sc", "templates/matter/matter.yaml"):
        corpus += read(extra)
    # Docs may also legitimately be reached from a sibling doc.
    sibling = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in docs
    )
    orphans = [
        d.name for d in docs
        if d.name not in corpus and d.name not in sibling.replace(d.read_text(), "")
    ]
    assert not orphans, (
        f"nothing links to these docs: {orphans}. Link them from README.md, "
        f"docs/architecture.md, or wherever a reader would start looking."
    )


def test_system_dependencies_are_documented_not_only_declared():
    """The manifest is the source of truth; docs/install.md is how to use it."""
    install = read("docs/install.md")
    for expected in ("sc deps", "system-dependencies.yaml"):
        assert expected in install, f"docs/install.md does not mention {expected}"
