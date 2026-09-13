"""The per-message mail index: a message is findable by ITS date.

A thread's PDF is named for its first message; a reply weeks later has
no file carrying its own date. `sc mail-index` gives every message a
row of its own, and `sc find --near` finds two words that belong
together without the exact phrase.
"""

from __future__ import annotations

import mailbox
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def _load_mail_index() -> Any:
    """connectors/ is outside the typed tree; load the module by path."""
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader

    loader = SourceFileLoader("mail_index", str(REPO / "connectors" / "gmail" / "mail_index.py"))
    spec = spec_from_loader("mail_index", loader)
    assert spec
    mod = module_from_spec(spec)
    # Register before exec: dataclass processing resolves cls.__module__
    # through sys.modules, and an unregistered module arrives as None.
    sys.modules["mail_index"] = mod
    loader.exec_module(mod)
    return mod


mail_index = _load_mail_index()


def _msg(
    date: str, sender: str, to: str, subject: str, body: str, html: bool = False
) -> EmailMessage:
    m = EmailMessage()
    m["Date"] = date
    m["From"] = sender
    m["To"] = to
    m["Subject"] = subject
    if html:
        m.set_content("")
        m.add_alternative(f"<html><body><p>{body}</p><br>sig</body></html>", subtype="html")
    else:
        m.set_content(body)
    return m


def _thread(path: Path) -> Path:
    box = mailbox.mbox(str(path))
    box.add(
        _msg(
            "Tue, 11 Nov 2025 13:38:01 -0800",
            "Andrew Roe <andrew@example.com>",
            "Laura Doe <laura@example.com>",
            "Intake form",
            "On the questionnaire, should I answer for myself or for the child?",
        )
    )
    box.add(
        _msg(
            "Tue, 18 Nov 2025 08:20:50 -0800",
            "Laura Doe <laura@example.com>",
            "Andrew Roe <andrew@example.com>",
            "Re: Intake form",
            "Good morning. This would change my role from the child's therapist to family "
            "therapist, which gives me more flexibility.\n\nOn Tue, Nov 11, 2025 Andrew Roe "
            "<andrew@example.com>\nwrote:\n> On the questionnaire\n"
            "The information contained in this transmission may be privileged.",
            html=True,
        )
    )
    box.add(
        _msg(
            "Fri, 5 Dec 2025 16:28:18 -0800",
            "Laura Doe <laura@example.com>",
            "Andrew Roe <andrew@example.com>",
            "Re: Intake form",
            "> quoted only\n> more quoted\n",
        )
    )
    box.flush()
    box.close()
    return path


def test_index_rows_carry_each_messages_own_date(tmp_path: Path) -> None:
    matter = tmp_path
    mbox_dir = matter / "assets" / "gmail" / "mbox"
    mbox_dir.mkdir(parents=True)
    _thread(mbox_dir / "20251111_intake_form.mbox")
    _tsv, md, n = mail_index.build(matter)
    assert n == 3
    rows = mail_index.search(matter, sender="laura", after="2025-11-15", before="2025-11-30")
    assert len(rows) == 1
    r = rows[0]
    assert (r.date, r.time, r.thread, r.n) == ("2025-11-18", "08:20", "20251111_intake_form", 2)
    # The snippet is the message's own words: the HTML body was read, the
    # quoted chain and the boilerplate were cut.
    assert r.snippet.startswith("Good morning. This would change my role")
    assert "wrote:" not in r.snippet and "information contained" not in r.snippet
    # A message that is only a quoted chain has an empty snippet, not the quote.
    assert mail_index.search(matter, after="2025-12-01")[0].snippet == ""
    text = md.read_text(encoding="utf-8")
    assert "## 2025-11" in text and "`20251111_intake_form` #2" in text
    assert mail_index.search(matter, grep=r"family.{0,20}therapist")[0].n == 2


def test_cli_query_and_find_near(tmp_path: Path) -> None:
    matter = tmp_path / "m"
    (matter / "assets" / "gmail" / "mbox").mkdir(parents=True)
    (matter / "matter.yaml").write_text("case:\n  short_name: test\n", encoding="utf-8")
    _thread(matter / "assets" / "gmail" / "mbox" / "20251111_intake_form.mbox")
    proc = subprocess.run(
        [
            str(REPO / "cli" / "sc"),
            "mail-index",
            str(matter),
            "--from",
            "laura",
            "--after",
            "2025-11-12",
            "--before",
            "2025-11-30",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "2025-11-18 08:20" in proc.stdout and "[20251111_intake_form #2]" in proc.stdout
    # find --near over the generated index: the words are six apart in the
    # source ("child's therapist to family therapist"), never adjacent.
    proc = subprocess.run(
        [
            str(REPO / "cli" / "sc"),
            "find",
            "--near",
            "family",
            "therapist",
            "--matter-dir",
            str(matter),
            "--this-matter-only",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "derived/mail/messages.md" in proc.stdout, proc.stdout[-800:] + proc.stderr[-800:]
    proc = subprocess.run(
        [
            str(REPO / "cli" / "sc"),
            "find",
            "--near",
            "family",
            "unicorn",
            "--matter-dir",
            str(matter),
            "--this-matter-only",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "messages.md" not in proc.stdout


def test_near_regex_is_order_free_and_bounded() -> None:
    import importlib.util
    import re
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("sc_cli", str(REPO / "cli" / "sc"))
    spec = importlib.util.spec_from_loader("sc_cli", loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    pat = re.compile(mod.near_regex(["family", "therapist"], 6), re.I)
    assert pat.search("from the child's therapist to family therapist")
    assert pat.search("a family systems therapist")
    assert not pat.search("family " + "word " * 8 + "therapist")
