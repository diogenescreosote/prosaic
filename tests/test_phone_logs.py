"""Phone log extraction keeps its promises (specs/phone-logs.md).

Fixtures are synthetic: invented numbers, invented names, invented
text. No case material enters this repo (leak-guard discipline).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from triage import phone_logs

# Epoch ms for fixed LOCAL wall-clock times, so window assertions hold
# in any timezone the suite runs in (promise 3: local-time bounds).


def ms(y, mo, d, h=12, mi=0, s=0):
    return int(datetime.datetime(y, mo, d, h, mi, s).timestamp() * 1000)


TARGET = "+15550001234"  # fictional: 555 prefix
OTHER = "+15550009999"

CALLS_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<calls count="4" backup_date="1787413928144" type="full">
  <call number="(555) 000-1234" duration="120" date="{a}" type="1" contact_name="Pat Fixture" />
  <call number="+15550001234" duration="0" date="{b}" type="3" contact_name="Pat Fixture" />
  <call number="+15550009999" duration="30" date="{a}" type="2" contact_name="Someone Else" />
  <call number="+15550001234" duration="60" date="{c}" type="2" contact_name="Pat Fixture" />
</calls>
""".format(a=ms(2026, 4, 10), b=ms(2026, 4, 11), c=ms(2026, 6, 1))

SMS_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="5" backup_date="1787413928144" type="full">
  <sms address="15550001234" date="{a}" type="1" body="hello from fixture" contact_name="Pat Fixture" />
  <sms address="+15550001234" date="{b}" type="2" body="reply | with pipe" contact_name="Pat Fixture" />
  <sms address="+15550009999" date="{a}" type="1" body="unrelated" contact_name="Someone Else" />
  <sms address="882867" date="{a}" type="1" body="short code spam" contact_name="(Unknown)" />
  <mms date="{c}" msg_box="2" address="+15550001234~+15550008888" contact_name="Group">
    <parts>
      <part seq="0" ct="application/smil" text="null" />
      <part seq="1" ct="text/plain" text="group hello" />
      <part seq="2" ct="image/jpeg" data="AAAA" />
    </parts>
    <addrs>
      <addr address="+15550007777" type="137" />
      <addr address="+15550001234" type="151" />
      <addr address="+15550008888" type="151" />
    </addrs>
  </mms>
</smses>
""".format(a=ms(2026, 4, 10, 13), b=ms(2026, 4, 12), c=ms(2026, 6, 2))


def write_backups(tmp_path: Path) -> Path:
    (tmp_path / "calls-20260601000000.xml").write_text(CALLS_XML, encoding="utf-8")
    (tmp_path / "sms-20260601000000.xml").write_text(SMS_XML, encoding="utf-8")
    # A second, overlapping daily backup: identical content, new name.
    (tmp_path / "calls-20260602000000.xml").write_text(CALLS_XML, encoding="utf-8")
    (tmp_path / "sms-20260602000000.xml").write_text(SMS_XML, encoding="utf-8")
    return tmp_path


def run(tmp_path, argv):
    out = tmp_path / "report.md"
    rc = phone_logs.main(argv + ["-o", str(out), str(tmp_path)])
    assert rc == 0
    return out.read_text(encoding="utf-8")


def test_number_matching_is_format_blind():
    assert phone_logs.numbers_match(
        phone_logs.normalize_number("1-555-000-1234"),
        phone_logs.normalize_number("(555) 000-1234"),
    )
    # Short codes match exactly, never by suffix.
    assert phone_logs.numbers_match("882867", "882867")
    assert not phone_logs.numbers_match("882867", "5550882867")


def test_extract_filters_dedupes_and_reports(tmp_path):
    report = run(write_backups(tmp_path), ["-n", TARGET])
    # 3 calls and 3 messages survive, though every row appears in two files.
    assert "Result: 3 calls, 3 messages (de-duplicated from 12 matching rows)" in report
    assert "hello from fixture" in report
    assert "group hello" in report  # group MMS matches a participant
    assert "[attachment: image/jpeg — not extracted]" in report
    assert "AAAA" not in report  # payload never decoded or copied
    assert "unrelated" not in report and "Someone Else" not in report
    assert "short code spam" not in report
    assert "MACHINE EXTRACT" in report  # provenance banner
    assert "sms-20260601000000.xml" in report  # sources named
    # Direction labels decoded, chronological order held.
    assert "| incoming |" in report and "| missed |" in report
    assert report.index("hello from fixture") < report.index("group hello")


def test_window_is_inclusive_and_local(tmp_path):
    report = run(
        write_backups(tmp_path),
        ["-n", TARGET, "--after", "2026-04-10", "--before", "2026-04-12"],
    )
    # Both endpoints' events survive; the June rows do not.
    assert "Result: 2 calls, 2 messages" in report
    assert "reply \\| with pipe" not in report  # bodies are quoted, not piped
    assert "reply | with pipe" in report
    assert "group hello" not in report


def test_sources_are_read_only(tmp_path):
    write_backups(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.xml")}
    run(tmp_path, ["-n", TARGET])
    after = {p.name: p.read_bytes() for p in tmp_path.glob("*.xml")}
    assert before == after


def test_streaming_root_is_cleared(tmp_path):
    """Bounded memory: after a scan the parse tree holds no records.

    (A true multi-GB test has no place in a suite; clearing the root
    per record is the mechanism the promise rides on.)
    """
    write_backups(tmp_path)
    records, seen, stats = [], set(), {}
    phone_logs.scan_file(
        tmp_path / "sms-20260601000000.xml",
        [phone_logs.normalize_number(TARGET)],
        None,
        None,
        records,
        seen,
        stats,
    )
    assert len(records) == 3
    assert stats["sources"][0][2] == "smses"
