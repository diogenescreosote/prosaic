"""`sc recall` and `sc open-questions`: the cheap search of what the
humans already said, run before any question to them.

The fixture is a tiny synthetic matter: two knowledge notes, the live
lists, a mail index row, a draft with placeholders, and a Claude Code
transcript whose user turns mix typed text with tool results and task
notifications that must never be searched.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"
sys.path.insert(0, str(REPO_ROOT / "triage"))
from triage import recall  # noqa: E402

NOTE_CLINIC = """---
title: Example Clinic
type: organization
updated: 2026-09-02
---

# Example Clinic

Jane Roe first called the Example Clinic on 2026-03-14 to ask about
intake. The clinic's records custodian is Pat Lee.

The intake form was signed March 20, 2026.
"""

NOTE_LETTER = """---
title: The March letter
type: topic
updated: 2026-09-03
---

# The March letter

The March 9 letter from John Smith is a two-page demand, not a notice
of termination. An earlier note called it a termination notice; that
was wrong.
"""

DRAFT = """---
notreal: "DRAFT---not served"
---

1. On March 14, 2026, Jane Roe telephoned the Example Clinic.
[XX: what time of day was the call?]

2. John Smith sent a letter on March 9. [Confirm whether the letter was
a termination notice]

3. The deposit was $4,500. [Verify amount against the Quillfeather Bank statement]

4. [TODO: who is the Zephyrine Archive custodian]
"""


def _user(text: str | list[dict[str, object]], **extra: object) -> str:
    rec: dict[str, object] = {
        "type": "user",
        "timestamp": "2026-10-20T17:00:00Z",
        "message": {"role": "user", "content": text},
        "isSidechain": False,
    }
    rec.update(extra)
    return json.dumps(rec)


def _transcript_lines() -> list[str]:
    return [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "Assistant says the Example Clinic custodian is unknown.",
                        }
                    ]
                },
            }
        ),
        _user("The Example Clinic call was in the morning, around 9.", origin={"kind": "human"}),
        _user(
            [{"type": "tool_result", "content": "Example Clinic tool output"}],
            toolUseResult={"stdout": "Example Clinic"},
        ),
        _user(
            "<task-notification>Example Clinic agent finished</task-notification>",
            origin={"kind": "task-notification"},
        ),
        _user([{"type": "text", "text": "Example Clinic meta caveat"}], isMeta=True),
        _user("Example Clinic subagent prompt", isSidechain=True),
        _user([{"type": "text", "text": "Older format: the Example Clinic visit was brief."}]),
    ]


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    m = tmp_path / "smith-v-roe"
    (m / "knowledge" / "organizations").mkdir(parents=True)
    (m / "knowledge" / "topics").mkdir(parents=True)
    (m / "matter.yaml").write_text("case:\n  name: Smith v. Roe\n  number: 24CV00000\n")
    (m / "knowledge" / "organizations" / "example-clinic.md").write_text(NOTE_CLINIC)
    (m / "knowledge" / "topics" / "march-letter.md").write_text(NOTE_LETTER)
    (m / "knowledge" / "README.txt").write_text("Example Clinic: not a note, never searched\n")
    (m / "KNOWLEDGE.md").write_text(
        "# Knowledge\n\n- [[example-clinic]]: Jane Roe first called the Example Clinic on 2026-03-14 to ask about\n"
    )
    (m / "TODO.md").write_text("# TODO\n\n1. Subpoena the Example Clinic records\n")
    (m / "QUESTIONS.md").write_text("# QUESTIONS\n\n1. Who is the Zephyrine Archive custodian?\n")
    (m / "derived" / "mail").mkdir(parents=True)
    (m / "derived" / "mail" / "messages.tsv").write_text(
        "date\ttime\tfrom\tsubject\tsnippet\n"
        "2026-04-02\t10:15\tpat.lee@example.com\tRecords\tThe Example Clinic will produce by May 1.\n"
    )
    (m / "src").mkdir()
    (m / "src" / "draft.md").write_text(DRAFT)
    (m / "src" / "other.md").write_text("Example Clinic in a source is not a knowledge surface.\n")
    return m


@pytest.fixture
def claude_home(tmp_path: Path, matter: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "claude-config"
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(matter.absolute()))
    proj = home / "projects" / slug
    proj.mkdir(parents=True)
    (proj / "0123abcd-0000-0000-0000-000000000000.jsonl").write_text(
        "\n".join(_transcript_lines()) + "\n"
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    return home


def sc(
    *argv: str, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SC), *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, **(env or {})},
    )


# --- recall --------------------------------------------------------------


def test_recall_finds_the_note_and_exits_zero(matter: Path) -> None:
    proc = sc("recall", "Example Clinic", cwd=matter)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.splitlines()[0].startswith("recall 'Example Clinic':")
    assert "knowledge/organizations/example-clinic.md:9: " in out
    assert "TODO.md:3: 1. Subpoena the Example Clinic records" in out
    assert "derived/mail/messages.tsv:2:" in out and "pat.lee@example.com | Records" in out
    assert "src/other.md" not in out, "sources are not knowledge surfaces"
    assert "README.txt" not in out, "only .md under knowledge/"


def test_notes_come_first_and_index_duplicates_are_dropped(matter: Path) -> None:
    out = sc("recall", "first called", cwd=matter).stdout
    hits = [ln for ln in out.splitlines() if re.match(r"^\S+:\d+: ", ln)]
    assert hits[0].startswith("knowledge/organizations/example-clinic.md:")
    assert not any(h.startswith("KNOWLEDGE.md:") for h in hits), "same snippet as the note"


def test_no_hits_exits_one_and_says_what_was_searched(matter: Path) -> None:
    proc = sc("recall", "zzz-nowhere", "--matter", str(matter))
    assert proc.returncode == 1
    assert (
        "no hits in knowledge, KNOWLEDGE.md, QUESTIONS.md, TODO.md, derived/mail/messages.tsv"
        in proc.stdout
    )
    assert "transcripts not searched" in proc.stdout


def test_several_terms_and_within_a_window_by_default(matter: Path) -> None:
    # "custodian" and "Pat Lee" share a line; "intake" sits one line above.
    both = sc("recall", "custodian", "Pat Lee", cwd=matter)
    assert both.returncode == 0 and "example-clinic.md:10:" in both.stdout
    assert "within 3 lines" in both.stdout.splitlines()[0]
    # "termination" is in the letter note; "Zephyrine" only in QUESTIONS.md.
    apart = sc("recall", "termination", "Zephyrine", cwd=matter)
    assert apart.returncode == 1
    either = sc("recall", "--any", "termination", "Zephyrine", cwd=matter)
    assert either.returncode == 0
    assert "march-letter.md" in either.stdout and "QUESTIONS.md" in either.stdout
    narrow = sc("recall", "--window", "0", "first called", "intake form", cwd=matter)
    assert narrow.returncode == 1, "three lines apart: outside a zero window"


def test_terms_are_case_insensitive_regexes(matter: Path) -> None:
    out = sc("recall", r"pat\s+lee", cwd=matter).stdout
    assert "example-clinic.md:10:" in out
    bad = sc("recall", "(unclosed", cwd=matter)
    assert bad.returncode == 1, "an invalid regex is taken literally, not a crash"


def test_snippets_are_trimmed_around_the_match(tmp_path: Path) -> None:
    m = tmp_path / "m"
    (m / "knowledge").mkdir(parents=True)
    (m / "matter.yaml").write_text("case: {}\n")
    (m / "knowledge" / "long.md").write_text(
        "filler " * 80 + "the Quillfeather deposit " + "tail " * 80 + "\n"
    )
    out = sc("recall", "Quillfeather", "--matter", str(m)).stdout
    line = next(ln for ln in out.splitlines() if ln.startswith("knowledge/long.md:1:"))
    assert "Quillfeather" in line
    assert len(line) < recall.SNIPPET_CHARS + 40
    assert line.split(": ", 1)[1].startswith("…") and line.endswith("…")


def test_output_is_capped_with_the_remainder_and_the_rg_command(tmp_path: Path) -> None:
    m = tmp_path / "m"
    (m / "knowledge").mkdir(parents=True)
    (m / "matter.yaml").write_text("case: {}\n")
    (m / "knowledge" / "many.md").write_text("".join(f"Marlow line {i}\n" for i in range(60)))
    proc = sc("recall", "Marlow", "--matter", str(m), "--max", "5")
    out = proc.stdout
    assert sum(1 for ln in out.splitlines() if ln.startswith("knowledge/many.md:")) == 5
    assert "… 55 more hit(s) not shown" in out
    assert "sc recall Marlow --matter" in out and out.count("--max") == 1 and "--max 0" in out
    assert "rg -n -i --no-heading" in out and "-e Marlow" in out
    full = sc("recall", "Marlow", "--matter", str(m), "--max", "0").stdout
    assert sum(1 for ln in full.splitlines() if ln.startswith("knowledge/many.md:")) == 60
    assert len(sc("recall", "Marlow", "--matter", str(m)).stdout.splitlines()) < 50


def test_recall_works_without_ripgrep(matter: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    hits = recall.search(matter, ["Pat Lee"])
    assert {h.path for h in hits} == {"knowledge/organizations/example-clinic.md"}


# --- transcripts -----------------------------------------------------------


def test_transcripts_are_off_by_default(matter: Path, claude_home: Path) -> None:
    out = sc("recall", "in the morning", cwd=matter, env={"CLAUDE_CONFIG_DIR": str(claude_home)})
    assert out.returncode == 1


def test_transcripts_yield_only_what_the_human_typed(matter: Path, claude_home: Path) -> None:
    proc = sc(
        "recall",
        "Example Clinic",
        "--transcripts",
        "--max",
        "0",
        cwd=matter,
        env={"CLAUDE_CONFIG_DIR": str(claude_home)},
    )
    assert proc.returncode == 0, proc.stderr
    t = [ln for ln in proc.stdout.splitlines() if ln.startswith("transcript/")]
    assert t == [
        "transcript/0123abcd:2: [2026-10-20] The Example Clinic call was in the morning, around 9.",
        "transcript/0123abcd:7: [2026-10-20] Older format: the Example Clinic visit was brief.",
    ]
    for never in (
        "tool output",
        "agent finished",
        "meta caveat",
        "subagent prompt",
        "Assistant says",
    ):
        assert never not in proc.stdout


def test_transcript_source_is_pluggable(matter: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(
        _m: Path, _terms: list[str], _pats: list[re.Pattern[str]], _mode: str, _fixed: bool
    ) -> list[recall.Hit]:
        return [
            recall.Hit(
                "transcript/fake", 1, "the human said Pat Lee retired", {0}, {0}, 99, "2026-10-01"
            )
        ]

    monkeypatch.setitem(recall.TRANSCRIPT_SOURCES, "fake", fake)
    hits = recall.search(matter, ["Pat Lee"], transcripts="fake")
    assert any(h.path == "transcript/fake" for h in hits)
    with pytest.raises(SystemExit, match="unknown transcript source"):
        recall.search(matter, ["Pat Lee"], transcripts="nope")


def test_slug_follows_claude_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = tmp_path / "My Drive" / "a.b@c"
    m.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    want = tmp_path / "cfg" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(m))
    want.mkdir(parents=True)
    assert recall.claude_code_dir(m) == [want]
    assert " " not in want.name and "@" not in want.name and "." not in want.name


# --- open questions --------------------------------------------------------


def test_placeholders_are_extracted_with_lines() -> None:
    found = recall.placeholders(DRAFT)
    assert [p.line for p in found] == [6, 8, 11, 13]
    assert found[0].inner == "what time of day was the call?"
    assert found[1].text.startswith("[Confirm whether the letter was a termination notice")
    assert "Example Clinic" in found[0].context
    assert recall.placeholders("prose [in brackets] and [[wikilink]]") == []
    custom = recall.placeholders("see [[Q: open]] and {{ASK me}}", r"\{\{ASK[^}]*\}\}")
    assert [p.text for p in custom] == ["{{ASK me}}"]


def test_keywords_keep_names_dates_numbers_and_drop_stopwords() -> None:
    pairs = recall.keyword_pairs(
        "what time of day was the call?",
        "On March 14, 2026, Jane Roe telephoned the Example Clinic.",
    )
    regexes = [r for r, _ in pairs]
    shown = [label for _, label in pairs]
    assert shown[0] == "March 14, 2026" and "2026-03-14" in regexes[0], (
        "a written date also searches its ISO form"
    )
    assert re.search(regexes[0], "on 2026-03-14") and re.search(regexes[0], "Mar. 14, 2026")
    assert "Jane Roe" in shown and "Example Clinic" in shown
    assert "the" not in shown and "what" not in shown and "March" not in shown
    assert len(pairs) <= recall.DEFAULT_TERMS
    money = [
        label
        for _, label in recall.keyword_pairs(
            "amount against the Quillfeather Bank statement", "The deposit was $4,500."
        )
    ]
    assert money[0] == "Quillfeather Bank" and "$4,500" in money
    quoted = recall.keyword_pairs('the note says "two-page demand" somewhere', "")
    assert quoted[0][1] == "two-page demand"
    assert recall.keywords("Jane wrote", "")[0] == "Jane", "a name is not a month abbreviation"


def test_open_questions_points_each_placeholder_at_the_record(matter: Path) -> None:
    proc = sc("open-questions", str(matter / "src" / "draft.md"))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.startswith("open questions in src/draft.md: 4 placeholder(s)")
    blocks = out.split("\n\n")
    call = next(b for b in blocks if b.startswith("L6 "))
    assert "knowledge/organizations/example-clinic.md:9" in call, "the note recording the call"
    letter = next(b for b in blocks if b.startswith("L8 "))
    assert "march-letter.md" in letter and "termination" in letter
    archive = next(b for b in blocks if b.startswith("L13 "))
    assert "QUESTIONS.md:3" in archive, "already asked: do not ask again"
    deposit = next(b for b in blocks if b.startswith("L11 "))
    assert "nothing recorded; ask the human" in deposit
    assert (
        "2 of 4 placeholder(s) have candidate answers on record; 1 only already listed as open"
        in out
    )
    assert "a placeholder is not evidence the question is open" in out
    assert len(out) < 3000, "compact enough to run before every question list"


def test_open_questions_reads_transcripts_on_request(matter: Path, claude_home: Path) -> None:
    out = sc(
        "open-questions",
        "src/draft.md",
        "--transcripts",
        cwd=matter,
        env={"CLAUDE_CONFIG_DIR": str(claude_home)},
    ).stdout
    call = next(b for b in out.split("\n\n") if b.startswith("L6 "))
    assert "transcript/0123abcd:2" in call


def test_open_questions_without_placeholders_exits_one(matter: Path) -> None:
    (matter / "src" / "clean.md").write_text("No open items here.\n")
    proc = sc("open-questions", "src/clean.md", cwd=matter)
    assert proc.returncode == 1 and "none" in proc.stdout
    assert sc("open-questions", "src/missing.md", cwd=matter).returncode == 2
