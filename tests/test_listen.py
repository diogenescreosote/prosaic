"""Listening sessions (ADR-0048): the page pointer, the notes file, the
utterance parser, and one session end to end with a fake reviewer.

The microphone is not exercised here: `whisper-stream` needs a device
and a permission prompt. Its line format is pinned by
`utterances_from_lines`, and the session is driven through typed input
(`--stdin-only`), which is the same path an utterance takes after
transcription. The reviewer is `PROSAIC_AGENT_CMD` pointed at a script
that answers with canned JSON, so the test sees exactly what the
session does with a reply and never calls a model.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from listen import track  # noqa: E402
from listen.agent import build_prompt, parse_reply  # noqa: E402
from listen.docset import Docset, load_docset  # noqa: E402
from listen.notes import Notes  # noqa: E402
from listen.transcribe import clean, pick_device, utterances_from_lines  # noqa: E402

PAGES = [
    "Progress Note\nInitial intake with the father. Discussed family history and identifying my role.",
    "Progress Note\nIndividual session with mother. Parenting support follow-up.",
    "Chart Note\nPhone call with Dr. Example, psychiatrist. Diagnosis discussed. Medication lithium.",
    "Informed Consent for Psychotherapy\nThe therapeutic relationship is unique.",
    "Email\nSubject: termination as family therapist. Family therapy is no longer clinically indicated.",
]
INDEX = textwrap.dedent("""
    | File | Bates | Session |
    |---|---|---|
    | `note_intake.pdf` | 00001 | Initial intake w/ Father |
    | `note_mother.pdf` | 00002 | Individual w/ Mother |
    | `chart_notes.pdf` | 00003 | Collateral call w/ psychiatrist |
    | `consent.pdf` | 00004\u201305 | Consent packet and termination email |
""")


@pytest.fixture
def docset(tmp_path: Path) -> Docset:
    pdf = tmp_path / "prod.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    for i, text in enumerate(PAGES, start=1):
        y = 720
        for line in text.split("\n"):
            c.drawString(72, y, line)
            y -= 16
        c.drawString(400, 40, f"ACME{i:05d}")
        c.showPage()
    c.save()
    idx = tmp_path / "INDEX.md"
    idx.write_text(INDEX, encoding="utf-8")
    return load_docset(pdf, "ACME00001", idx)


# ---------------------------------------------------------------- docset


def test_docset_pages_tokens_and_titles(docset: Docset) -> None:
    assert [p.bates for p in docset.pages] == [f"ACME0000{i}" for i in range(1, 6)]
    assert docset.number_for("ACME00003") == 3
    assert docset.number_for("3") == 3 and docset.number_for("00003") == 3
    assert docset.number_for("OTHER00003") is None
    assert docset.number_for("ACME00009") is None
    assert docset.pages[0].label == "Initial intake w/ Father"
    assert docset.pages[3].label == docset.pages[4].label == "Consent packet and termination email"
    assert "ACME00004--00005: Consent packet and termination email" in docset.index_lines()


# ---------------------------------------------------------------- tracking


@pytest.mark.parametrize(
    "utt,expected",
    [
        ("okay page three", 3),
        ("Acme 4", 4),
        ("let's look at ACME00002", 2),
        ("bates number zero zero zero zero five", 5),
        ("page seventeen", None),  # not in the set
        ("next page", 2),
        ("go back a page", 1),
        ("let's look at the collateral call with the psychiatrist", 3),
        ("I want to ask her about the intake", None),  # no navigation phrasing
    ],
)
def test_explicit_cues(docset: Docset, utt: str, expected: int | None) -> None:
    assert track.explicit_cue(utt, docset, current=1) == expected


def test_content_match_moves_only_on_a_clear_owner(docset: Docset) -> None:
    utt = "she wrote that family therapy is no longer clinically indicated, the termination"
    assert track.content_match(utt, docset, current=1) == 5
    assert track.content_match("I want to ask about the note", docset, current=1) is None
    # Already on the page: nothing to move.
    assert track.content_match(utt, docset, current=5) is None


# ---------------------------------------------------------------- transcription parsing


def test_whisper_lines_become_utterances() -> None:
    lines = iter(
        [
            "init: found 2 capture devices:\n",
            "[Start speaking]\n",
            "\n### Transcription 0 START | t0 = 0 ms | t1 = 2000 ms\n",
            " page three\n",
            "\n### Transcription 0 END\n",
            "[BLANK_AUDIO]\n",
            "(silence)\n",
            "\x1b[2K\rand ask her when she first spoke to the mother\n",
            "### Transcription 1 START | t0 = 0 ms | t1 = 2000 ms\n",
            "would that\n",
            "touch privilege\n",
            "### Transcription 1 END\n",
        ]
    )
    assert list(utterances_from_lines(lines)) == [
        "page three",
        "and ask her when she first spoke to the mother",
        "would that touch privilege",
    ]
    assert clean("[00:00:01.000 --> 00:00:03.000]  hello there") == "hello there"


def test_device_choice_prefers_a_real_microphone() -> None:
    assert pick_device(["BlackHole 2ch", "MacBook Pro Microphone"]) == 1
    assert pick_device(["BlackHole 2ch"]) is None


# ---------------------------------------------------------------- agent plumbing


def test_parse_reply_takes_the_json_and_tolerates_prose() -> None:
    raw = 'Sure.\n{"kind": "question", "page": null, "question": "When did you first meet?"}\nDone.'
    r = parse_reply(raw)
    assert r["kind"] == "question" and r["question"] == "When did you first meet?"
    r = parse_reply("not json at all")
    assert r["kind"] == "ask" and r["reply"] == "not json at all"


def test_prompt_carries_page_brief_and_shape(docset: Docset) -> None:
    p = build_prompt(
        "ROLE",
        "BRIEF",
        docset.index_lines(),
        "ACME00003",
        "Collateral call",
        docset.pages[2].text,
        ["already asked"],
        [{"page": "ACME00001", "said": "hi", "reply": "hello"}],
        "ask her whether she recorded the call",
    )
    for needle in (
        "ROLE",
        "# Session brief",
        "BRIEF",
        "ACME00003",
        "lithium",
        "already asked",
        "speaker: hi",
        "ask her whether she recorded the call",
        '"kind"',
    ):
        assert needle in p


# ---------------------------------------------------------------- notes


def test_notes_render_by_record_with_warnings(tmp_path: Path) -> None:
    n = Notes(out=tmp_path / "q.md", heading="Test", docset_name="prod.pdf", role="depo-prep")
    n.add_question(
        "ACME00003",
        "Collateral call",
        3,
        "Did you record the call?",
        "Calls for the recording's existence, fine.",
    )
    n.add_question("ACME00001", "Intake", 1, "When was the intake?")
    n.add_note("ACME00001", "Intake", 1, "Edited in February.")
    n.add_realization("The intake predates the child's first session.")
    n.add_exchange("is that privileged?", "No: it is her own act.", "ACME00003")
    n.save()
    md = (tmp_path / "q.md").read_text(encoding="utf-8")
    assert md.startswith("<!-- NOTREAL")
    assert md.index("## ACME00001") < md.index("## ACME00003")  # Bates order, not order raised
    assert "1. When was the intake?" in md and "- Edited in February." in md
    assert "⚠ Calls for the recording's existence" in md
    assert "## Realizations" in md and "## Advice given during the session" in md


# ---------------------------------------------------------------- end to end

FAKE_AGENT = r"""#!/usr/bin/env python3
import json, sys
prompt = sys.stdin.read()
if "# Task" in prompt:
    print("One theme."); sys.exit(0)
utt = prompt.rsplit("# The utterance", 1)[1].split("\n\n", 2)[1].strip()
if utt.startswith("ask her"):
    out = {"kind": "question", "page": None, "question": utt[len("ask her "):].capitalize() + "?",
           "warning": "opinion" if "why she thinks" in utt else None, "reply": "", "note": None,
           "realization": "Two intakes, one child." if "intake" in utt else None}
elif "privilege" in utt:
    out = {"kind": "ask", "page": None, "question": None, "warning": None,
           "reply": "No: her own act is not another patient's communication.", "note": None, "realization": None}
elif "termination" in utt:
    out = {"kind": "note", "page": "ACME00005", "question": None, "warning": None,
           "reply": "", "note": "The termination email names both parents.", "realization": None}
else:
    out = {"kind": "noise", "page": None, "question": None, "warning": None, "reply": "", "note": None, "realization": None}
print(json.dumps(out))
"""


def test_session_end_to_end_with_typed_input(docset: Docset, tmp_path: Path) -> None:
    fake = tmp_path / "fake_agent.py"
    fake.write_text(FAKE_AGENT, encoding="utf-8")
    fake.chmod(0o755)
    brief = tmp_path / "BRIEF.md"
    brief.write_text("The witness is a family therapist.", encoding="utf-8")
    out = tmp_path / "notes" / "questions.md"
    script = (
        "\n".join(
            [
                "page three",
                "ask her when she first spoke to the psychiatrist about the intake",
                "would that touch privilege",
                "ask her why she thinks the father was unstable",
                "she wrote that family therapy is no longer clinically indicated, the termination",
                "/undo",
                "/quit",
            ]
        )
        + "\n"
    )
    env = {**os.environ, "PROSAIC_AGENT_CMD": f"{sys.executable} {fake}"}
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "listen" / "session.py"),
            "--stdin-only",
            "--docset",
            str(docset.path),
            "--bates-first",
            "ACME00001",
            "--index",
            str(docset.path.parent / "INDEX.md"),
            "--brief",
            str(brief),
            "--out",
            str(out),
            "--role",
            "depo-prep",
        ],
        input=script,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    md = out.read_text(encoding="utf-8")
    # The question was logged under page 3 with its realization.
    assert "## ACME00003" in md
    assert "When she first spoke to the psychiatrist about the intake?" in md
    assert "Two intakes, one child." in md
    # The ask was answered and kept.
    assert "No: her own act is not another patient's communication." in md
    # The warned question was logged, then /undo removed it: the last question logged, whatever page.
    assert "Why she thinks the father was unstable?" not in md
    # The note moved the pointer to page 5 and was filed there.
    assert "## ACME00005" in md and "The termination email names both parents." in md
    # Synthesis ran.
    assert "## Closing synthesis" in md and "One theme." in md
    # Sidecars exist and the transcript carries the page.
    assert (out.with_suffix(".transcript.txt")).exists()
    events = [
        json.loads(line) for line in out.with_suffix(".events.jsonl").read_text().splitlines()
    ]
    assert any(e["kind"] == "nav" and e["page"] == "ACME00003" for e in events)
    assert "→ ACME00003" in proc.stdout and "⚠ opinion" in proc.stdout
