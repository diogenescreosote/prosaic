"""The entity journal of acts, pinned (ADR-0052).

An entity's journal is the numbered, dated record of what it actually
did, read by people who will never open git. Two things make it worth
keeping: every entry has the same shape (so a reader can find the act,
the vote and the paper), and nothing once written silently changes (so
the journal can be relied on as a record). These tests pin both: the
form check, the append-only check against HEAD, and the commit-msg
gate that refuses an unannotated edit unless the human overrides.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"

PREAMBLE = "# Journal of Acts\n\nPreamble for a lay reader.\n\n## Entries\n"


def entry(n: int, date: str = "2026-01-15", title: str = "Articles filed", **over: str) -> str:
    bullets = {
        "Act": "Articles of incorporation filed and endorsed.",
        "By": "Jane Roe, incorporator",
        "Vote": "n/a",
        "Authority": "n/a",
        "Record": "assets/01 Formation/2026-01-15_articles.pdf",
        "Entered": "2026-01-20 by Jane Roe",
    }
    bullets.update(over)
    body = "".join(f"- **{k}:** {v}\n" for k, v in bullets.items() if v != "OMIT")
    return f"\n## J-{n:04d} · {date} · {title}\n{body}"


GOOD = PREAMBLE + entry(1) + entry(2, "2026-01-16", "Bylaws adopted", Vote="3 for, 0 against")


def git_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="Jane Roe",
        GIT_AUTHOR_EMAIL="jane@example.com",
        GIT_COMMITTER_NAME="Jane Roe",
        GIT_COMMITTER_EMAIL="jane@example.com",
        PROSAIC_ROOT=str(REPO_ROOT),
    )
    return env


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, env=git_env(), capture_output=True, text=True, check=False
    )


def journal_check(matter: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SC), "journal", "check", str(matter), *extra],
        capture_output=True,
        text=True,
        env=git_env(),
    )


def commit_check(repo: Path, message: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SC), "commit-check"],
        input=message,
        cwd=repo,
        capture_output=True,
        text=True,
        env=git_env(),
    )


def committed_repo(tmp_path: Path, text: str = GOOD) -> Path:
    """A git repo whose HEAD holds `text` as JOURNAL.md (no hooks)."""
    repo = tmp_path / "m"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "core.hooksPath", "/dev/null")
    (repo / "JOURNAL.md").write_text(text, encoding="utf-8")
    git(repo, "add", "JOURNAL.md")
    assert git(repo, "commit", "-q", "-m", "record: journal").returncode == 0
    return repo


# --- form -----------------------------------------------------------------


def form(tmp_path: Path, text: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "JOURNAL.md").write_text(text, encoding="utf-8")
    return journal_check(tmp_path)


def test_a_well_formed_journal_passes(tmp_path: Path) -> None:
    proc = form(tmp_path, GOOD)
    assert proc.returncode == 0, proc.stderr
    assert "2 entries" in proc.stdout


def test_absent_journal_is_nothing_to_check(tmp_path: Path) -> None:
    proc = journal_check(tmp_path)
    assert proc.returncode == 0
    assert "nothing to check" in proc.stdout


def test_a_gap_in_numbering_fails(tmp_path: Path) -> None:
    proc = form(tmp_path, PREAMBLE + entry(1) + entry(3))
    assert proc.returncode == 1
    assert "expected J-0002" in proc.stderr


def test_an_impossible_date_fails(tmp_path: Path) -> None:
    proc = form(tmp_path, PREAMBLE + entry(1, date="2026-02-30"))
    assert proc.returncode == 1
    assert "not a YYYY-MM-DD date" in proc.stderr


def test_a_missing_bullet_fails(tmp_path: Path) -> None:
    proc = form(tmp_path, PREAMBLE + entry(1, Authority="OMIT"))
    assert proc.returncode == 1
    assert "missing `- **Authority:**`" in proc.stderr


def test_an_act_dated_after_its_entry_is_a_plan(tmp_path: Path) -> None:
    proc = form(tmp_path, PREAMBLE + entry(1, date="2026-03-01"))
    assert proc.returncode == 1
    assert "acts, not plans" in proc.stderr


def test_the_scaffolded_template_is_well_formed(tmp_path: Path) -> None:
    """Its worked example sits in a fence, so it is not entry J-0001."""
    text = (REPO_ROOT / "templates" / "entity" / "JOURNAL.md").read_text(encoding="utf-8")
    proc = form(tmp_path, text)
    assert proc.returncode == 0, proc.stderr
    assert "0 entries" in proc.stdout
    proc = form(tmp_path, text + entry(1))
    assert proc.returncode == 0, proc.stderr


# --- append-only against HEAD ---------------------------------------------


def test_a_pure_append_passes(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    (repo / "JOURNAL.md").write_text(GOOD + entry(3, "2026-01-17", "Officers elected"))
    proc = journal_check(repo)
    assert proc.returncode == 0, proc.stderr


def test_an_unannotated_edit_fails(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    (repo / "JOURNAL.md").write_text(GOOD.replace("3 for, 0 against", "2 for, 1 against"))
    proc = journal_check(repo)
    assert proc.returncode == 1
    assert "no annotation" in proc.stderr


def test_an_annotated_edit_passes(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    amended = GOOD.replace(
        "- **Vote:** 3 for, 0 against\n",
        "- **Vote:** ~~3 for, 0 against~~ 2 for, 1 against\n"
        "> **Amended 2026-01-21 by Jane Roe:** vote corrected --- the minutes were misread.\n",
    )
    (repo / "JOURNAL.md").write_text(amended)
    proc = journal_check(repo)
    assert proc.returncode == 0, proc.stderr


def test_an_annotation_in_another_entry_does_not_cover_the_edit(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    edited = GOOD.replace("Jane Roe, incorporator", "John Smith, incorporator")
    edited += "> **Amended 2026-01-21 by Jane Roe:** unrelated note.\n"
    (repo / "JOURNAL.md").write_text(edited)
    proc = journal_check(repo)
    assert proc.returncode == 1
    assert "no annotation" in proc.stderr


def test_a_deletion_fails_even_annotated(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    # The removed line is in the preamble, so the result is still well
    # formed: only the append-only check can catch it.
    deleted = GOOD.replace(
        "Preamble for a lay reader.\n",
        "> **Amended 2026-01-21 by Jane Roe:** removed the preamble --- it was wrong.\n",
    )
    (repo / "JOURNAL.md").write_text(deleted)
    proc = journal_check(repo)
    assert proc.returncode == 1
    assert "deleted" in proc.stderr
    assert "missing" not in proc.stderr


def test_a_removed_entry_fails(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    (repo / "JOURNAL.md").write_text(PREAMBLE + entry(1))
    proc = journal_check(repo)
    assert proc.returncode == 1
    assert "deleted" in proc.stderr


def test_staged_checks_the_index_not_the_working_tree(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    (repo / "JOURNAL.md").write_text(GOOD.replace("Bylaws adopted", "Bylaws rejected"))
    git(repo, "add", "JOURNAL.md")
    (repo / "JOURNAL.md").write_text(GOOD)
    assert journal_check(repo).returncode == 0
    assert journal_check(repo, "--staged").returncode == 1


# --- the commit gate ------------------------------------------------------

MESSAGE = "record(journal): correct the bylaws vote\n\nBody.\n"


def test_commit_gate_rejects_an_unannotated_edit(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    (repo / "JOURNAL.md").write_text(GOOD.replace("3 for, 0 against", "2 for, 1 against"))
    git(repo, "add", "JOURNAL.md")
    proc = commit_check(repo, MESSAGE)
    assert proc.returncode == 1
    assert "append-only" in proc.stderr
    assert "Journal-Override" in proc.stderr


def test_commit_gate_accepts_the_human_override(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    (repo / "JOURNAL.md").write_text(GOOD.replace("3 for, 0 against", "2 for, 1 against"))
    git(repo, "add", "JOURNAL.md")
    proc = commit_check(repo, MESSAGE + "\nJournal-Override: typo on entry, per the secretary\n")
    assert proc.returncode == 0, proc.stderr
    assert "overridden" in proc.stderr


def test_commit_gate_passes_an_append_and_ignores_unstaged_journals(tmp_path: Path) -> None:
    repo = committed_repo(tmp_path)
    (repo / "JOURNAL.md").write_text(GOOD + entry(3, "2026-01-17", "Officers elected"))
    git(repo, "add", "JOURNAL.md")
    assert commit_check(repo, MESSAGE).returncode == 0
    git(repo, "commit", "-q", "-m", "record: append")
    # An unstaged edit is not this commit's business.
    (repo / "JOURNAL.md").write_text("vandalized\n")
    assert commit_check(repo, MESSAGE).returncode == 0


def test_the_installed_hook_refuses_the_commit(tmp_path: Path) -> None:
    """End to end: `sc init --type entity --git` wires the gate into git."""
    m = tmp_path / "m"
    subprocess.run(
        [sys.executable, str(SC), "init", str(m), "--type", "entity", "--git"],
        check=True,
        capture_output=True,
        env=git_env(),
    )
    journal = m / "JOURNAL.md"
    journal.write_text(journal.read_text(encoding="utf-8") + entry(1), encoding="utf-8")
    git(m, "add", "JOURNAL.md")
    first = git(m, "commit", "-q", "-m", "record(journal): articles filed")
    assert first.returncode == 0, first.stderr
    journal.write_text(journal.read_text(encoding="utf-8").replace("Jane Roe, inc", "J. Roe, inc"))
    git(m, "add", "JOURNAL.md")
    refused = git(m, "commit", "-q", "-m", "record(journal): tidy a name")
    assert refused.returncode != 0
    assert "append-only" in refused.stderr


# --- scaffold -------------------------------------------------------------


def test_entity_init_scaffolds_the_journal(tmp_path: Path) -> None:
    m = tmp_path / "m"
    subprocess.run(
        [sys.executable, str(SC), "init", str(m), "--type", "entity"],
        check=True,
        capture_output=True,
    )
    text = (m / "JOURNAL.md").read_text(encoding="utf-8")
    assert text.startswith("# Journal of Acts")
    assert "JOURNAL.md" in (m / "START HERE.md").read_text(encoding="utf-8")
    assert "Every act goes in the journal" in (m / "AGENTS.md").read_text(encoding="utf-8")


def test_litigation_init_has_no_journal(tmp_path: Path) -> None:
    m = tmp_path / "m"
    subprocess.run([sys.executable, str(SC), "init", str(m)], check=True, capture_output=True)
    assert not (m / "JOURNAL.md").exists()
