"""The drafts audit: drafts that older captures left in the mail record.

A draft is not mail (ADR-0049). The connector no longer captures one,
but a matter captured before that rule can hold drafts rendered exactly
like sent mail. `sc mail-audit-drafts` finds them by comparing the
mailbox's drafts and threads (stubbed here) with the matter's files,
and `--apply` moves them out of the record without deleting anything.

Every message, file and Gmail response here is synthetic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GMAIL = REPO_ROOT / "connectors" / "gmail"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

CRLF = "\r\n"


def _json(body: str, matter: Path | None = None) -> Any:
    env = {**os.environ, "NODE_PATH": str(REPO_ROOT / "connectors" / "node_modules")}
    if matter is not None:
        env["MATTER"] = str(matter)
    proc = subprocess.run(
        ["node", "-e", body], cwd=GMAIL, capture_output=True, text=True, env=env, timeout=120
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _raw(message_id: str, subject: str, sender: str, date: str, body: str) -> str:
    return CRLF.join(
        [
            f"Message-ID: <{message_id}>",
            f"Subject: {subject}",
            f"From: {sender}",
            "To: John Smith <john.smith@example.com>",
            f"Date: {date}",
            "",
            body,
            "",
        ]
    )


JANE = "Jane Roe <jane.roe@example.com>"
JOHN = "John Smith <john.smith@example.com>"

DRAFT_BODY = "I have been thinking about the inspection schedule and would propose the ninth"
REAL_BODY = "The inspection is confirmed for the fifth at ten in the morning"


def _write_mbox(path: Path, raws: list[str]) -> None:
    """Write an mbox through the connector's own writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = ",".join(
        f"{{id: 'x{i}', raw: Buffer.from({json.dumps(r)}, 'binary')}}" for i, r in enumerate(raws)
    )
    _json(
        f"const m = require('./mbox'); m.appendMessages({json.dumps(str(path))}, [{entries}]);"
        "console.log('{}');"
    )


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    """A matter holding one render of each kind the audit must tell apart."""
    m = tmp_path / "m"
    g = m / "assets" / "gmail"
    (g / "mbox").mkdir(parents=True)
    dt = m / "derived" / "text" / "assets" / "gmail"
    dt.mkdir(parents=True)
    threads = m / "derived" / "mail" / "threads"
    threads.mkdir(parents=True)

    # 1. draft-only, captured with an mbox
    s1 = "20260105_inspection_schedule"
    _write_mbox(
        g / "mbox" / f"{s1}.mbox",
        [
            _raw(
                "d1@mail.example.com",
                "Inspection schedule",
                JANE,
                "Mon, 5 Jan 2026 10:00:00 -0800",
                DRAFT_BODY,
            )
        ],
    )
    (g / f"{s1}.pdf").write_bytes(b"%PDF draft-only render")
    (g / f"{s1}.txt").write_text(f"Inspection schedule\n1 message\n{DRAFT_BODY}\n")
    (g / "attachments" / s1).mkdir(parents=True)
    (g / "attachments" / s1 / "plan.pdf").write_bytes(b"%PDF plan")
    (dt / f"{s1}.pdf.txt").write_text("sidecar\n")
    (threads / f"{s1}.txt").write_text("bodies\n")

    # 2. mixed: a real thread whose mbox also holds a draft reply
    s2 = "20260106_site_access"
    real2 = _raw("r2@example.com", "Site access", JOHN, "Tue, 6 Jan 2026 09:00:00 -0800", REAL_BODY)
    draft2 = _raw(
        "d2@mail.example.com", "Re: Site access", JANE, "Tue, 6 Jan 2026 11:00:00 -0800", DRAFT_BODY
    )
    _write_mbox(g / "mbox" / f"{s2}.mbox", [real2, draft2])
    (g / f"{s2}.pdf").write_bytes(b"%PDF mixed render")
    (dt / f"{s2}.pdf.txt").write_text("sidecar\n")

    # 3. unverified: a stored message Gmail no longer has
    s3 = "20260107_keys"
    _write_mbox(
        g / "mbox" / f"{s3}.mbox",
        [_raw("gone@example.com", "Keys", JOHN, "Wed, 7 Jan 2026 09:00:00 -0800", "keys")],
    )
    (g / f"{s3}.pdf").write_bytes(b"%PDF")

    # 4. a PDF-only legacy render of a real thread that included a draft
    s4 = "20250301_invoice"
    (g / f"{s4}.pdf").write_bytes(b"%PDF legacy")
    (g / f"{s4}.txt").write_text(f"Invoice\n2 messages\nPlease find attached\n{DRAFT_BODY} too\n")

    # 5. a PDF no ledger entry names, rendered from a lone draft
    s5 = "20250410_lease_renewal"
    (g / f"{s5}.pdf").write_bytes(b"%PDF loose")
    (dt / f"{s5}.pdf.txt").write_text(f"Lease renewal\n1 message\n{DRAFT_BODY} and more\n")

    # 7. a PDF-only render that printed more than Gmail now holds: the
    #    real messages were deleted, and the PDF is their only record
    s7 = "20250501_deposit"
    (g / f"{s7}.pdf").write_bytes(b"%PDF only record")
    (g / f"{s7}.txt").write_text(f"Deposit\n3 messages\n{DRAFT_BODY}\n")

    # an ordinary thread the audit must leave alone
    s6 = "20260108_ordinary"
    _write_mbox(
        g / "mbox" / f"{s6}.mbox",
        [_raw("r6@example.com", "Ordinary", JOHN, "Thu, 8 Jan 2026 09:00:00 -0800", REAL_BODY)],
    )
    (g / f"{s6}.pdf").write_bytes(b"%PDF")

    (g / "CATALOG.md").write_text(
        f"| 2026-01-05 | {s1}.pdf | letter |\n| 2026-01-08 | {s6}.pdf |\n"
    )
    (m / ".gitignore").write_text(".state/\n")

    ledger = {
        "t1": {
            "filename": f"{s1}.pdf",
            "mbox": f"mbox/{s1}.mbox",
            "messageIds": ["d1"],
            "draftCount": 0,
        },
        "t2": {"filename": f"{s2}.pdf", "mbox": f"mbox/{s2}.mbox", "messageIds": ["r2", "d2"]},
        "t3": {"filename": f"{s3}.pdf", "mbox": f"mbox/{s3}.mbox", "messageIds": ["g3"]},
        "t4": {"filename": f"{s4}.pdf", "messageCount": 2},
        "t8": {"filename": f"{s7}.pdf", "messageCount": 3},
        "t6": {"filename": f"{s6}.pdf", "mbox": f"mbox/{s6}.mbox", "messageIds": ["r6"]},
    }
    (m / "ledger.json").write_text(json.dumps(ledger))
    return m


#: The mailbox as Gmail holds it now, in the shapes auditRecord takes.
SETUP = r"""
const fs = require('fs'); const path = require('path');
const audit = require('./drafts_audit');
const matterDir = process.env.MATTER;
const outDir = path.join(matterDir, 'assets', 'gmail');
const ledger = { threads: JSON.parse(fs.readFileSync(path.join(matterDir, 'ledger.json'))) };
const body = 'I have been thinking about the inspection schedule and would propose the ninth';
const drafts = [
  { gmailId: 'd1', threadId: 't1', key: '<d1@mail.example.com>', subject: 'Inspection schedule',
    date: 'Mon, 5 Jan 2026 10:00:00 -0800', snippet: body },
  { gmailId: 'd2', threadId: 't2', key: '<d2@mail.example.com>', subject: 'Re: Site access',
    date: 'Tue, 6 Jan 2026 11:00:00 -0800', snippet: body },
  { gmailId: 'd4', threadId: 't4', key: '<d4@mail.example.com>', subject: 'Re: Invoice',
    date: 'Sun, 2 Mar 2025 10:00:00 -0800', snippet: body.replace('would', 'would') },
  { gmailId: 'd5', threadId: 't5', key: '<d5@mail.example.com>', subject: 'Lease renewal',
    date: 'Thu, 10 Apr 2025 12:00:00 -0700', snippet: body + ' and more' },
  { gmailId: 'd8', threadId: 't8', key: '<d8@mail.example.com>', subject: 'Re: Deposit',
    date: 'Thu, 1 May 2025 10:00:00 -0700', snippet: body },
  { gmailId: 'd7', threadId: 't7', key: '<d7@mail.example.com>', subject: 'Unrelated',
    date: 'Fri, 9 Jan 2026 12:00:00 -0800', snippet: 'a draft about something the matter never captured' },
];
const S = (a) => new Set(a);
const live = new Map([
  ['t1', { exists: true, realKeys: S([]), realIds: S([]), draftKeys: S(['<d1@mail.example.com>']), draftIds: S(['d1']) }],
  ['t2', { exists: true, realKeys: S(['<r2@example.com>']), realIds: S(['r2']), draftKeys: S(['<d2@mail.example.com>']), draftIds: S(['d2']) }],
  ['t3', { exists: true, realKeys: S(['<other@example.com>']), realIds: S(['o3']), draftKeys: S([]), draftIds: S([]) }],
  ['t4', { exists: true, realKeys: S(['<r4@example.com>']), realIds: S(['r4']), draftKeys: S(['<d4@mail.example.com>']), draftIds: S(['d4']) }],
  ['t8', { exists: true, realKeys: S([]), realIds: S([]), draftKeys: S(['<d8@mail.example.com>']), draftIds: S(['d8']) }],
  ['t6', { exists: true, realKeys: S(['<r6@example.com>']), realIds: S(['r6']), draftKeys: S([]), draftIds: S([]) }],
]);
const result = audit.auditRecord({ matterDir, outDir, ledgerThreads: ledger.threads, drafts, live });
const brief = (f) => ({ stem: f.stem, kind: f.kind, source: f.source, threadId: f.threadId,
  files: f.files, copies: f.copies, references: f.references, draftGmailIds: f.draftGmailIds });
"""


def test_the_audit_tells_draft_only_mixed_and_unverified_apart(matter: Path) -> None:
    out = _json(
        SETUP
        + r"""
        console.log(JSON.stringify({
          findings: result.findings.map(brief),
          inRecord: [...result.inRecord].sort(),
          unmatched: result.unmatched.map((d) => d.gmailId),
        }));
        """,
        matter,
    )
    by = {f["stem"]: f for f in out["findings"]}
    assert set(by) == {
        "20260105_inspection_schedule",
        "20260106_site_access",
        "20260107_keys",
        "20250301_invoice",
        "20250410_lease_renewal",
        "20250501_deposit",
    }, "the ordinary thread is not a finding"
    assert by["20260105_inspection_schedule"]["kind"] == "draft-only"
    assert by["20260106_site_access"]["kind"] == "mixed"
    assert by["20260107_keys"]["kind"] == "unverified"
    assert by["20250501_deposit"]["kind"] == "unverified", (
        "a PDF that printed more than Gmail now holds may be the only record of deleted mail"
    )
    assert (by["20250301_invoice"]["kind"], by["20250301_invoice"]["source"]) == ("mixed", "pdf")
    loose = by["20250410_lease_renewal"]
    assert (loose["kind"], loose["threadId"]) == ("draft-only", None), (
        "a PDF no ledger names is matched by the draft's date, subject and opening words"
    )
    assert out["inRecord"] == ["d1", "d2", "d4", "d5", "d8"]
    assert out["unmatched"] == ["d7"]

    s1 = by["20260105_inspection_schedule"]
    assert s1["files"] == [
        "assets/gmail/20260105_inspection_schedule.pdf",
        "assets/gmail/20260105_inspection_schedule.txt",
        "assets/gmail/attachments/20260105_inspection_schedule",
        "assets/gmail/mbox/20260105_inspection_schedule.mbox",
        "derived/mail/threads/20260105_inspection_schedule.txt",
        "derived/text/assets/gmail/20260105_inspection_schedule.pdf.txt",
    ]
    assert s1["references"] == ["assets/gmail/CATALOG.md:1"]
    assert s1["draftGmailIds"] == ["d1"]


def test_matching_rules_are_strict_enough_to_be_evidence() -> None:
    out = _json(
        r"""
        const a = require('./drafts_audit');
        const p = a.candidateStemPattern({ subject: 'Re: Lease renewal', date: 'Thu, 10 Apr 2025 23:30:00 -0700' });
        const S = (x) => new Set(x);
        console.log(JSON.stringify({
          short: a.snippetKey('Thanks!'),
          entity: a.textHasSnippet("We can't make Tuesday at all, sorry about that", a.snippetKey('We can&#39;t make Tuesday at all, sorry')),
          stems: ['20250411_lease_renewal', '20250410_lease_renewal_2', '20250411_lease_renewal_x', '20250415_lease_renewal'].map((s) => p.test(s)),
          count: [a.printedMessageCount('Subj\n3 messages\nx'), a.printedMessageCount('none')],
          cls: [
            a.classifyStoredThread(['<a>', '<b>'], { draftKeys: S(['<b>']), liveRealKeys: S(['<a>']) }).kind,
            a.classifyStoredThread(['<b>'], { draftKeys: S(['<b>']) }).kind,
            a.classifyStoredThread(['<a>', '<c>'], { draftKeys: S([]), liveRealKeys: S(['<a>']) }).kind,
            a.classifyStoredThread(['<a>', '<c>'], { draftKeys: S([]), liveRealKeys: null }).kind,
          ],
        }));
        """
    )
    assert out["short"] is None, "a few words are not evidence"
    assert out["entity"] is True, "Gmail's HTML-escaped snippet matches the printed text"
    assert out["stems"] == [True, True, False, False]
    assert out["count"] == [3, None]
    assert out["cls"] == ["mixed", "draft-only", "unverified", None]


def test_the_report_names_files_never_a_drafts_words(matter: Path) -> None:
    out = _json(
        SETUP
        + r"""
        const text = audit.formatReport(result, { matterDir, account: 'jane.roe@example.com' });
        console.log(JSON.stringify({ text }));
        """,
        matter,
    )
    text = out["text"]
    assert "report only (nothing was changed)" in text
    assert "draft-only renders:               2" in text
    assert "mixed renders (real + draft):     2" in text
    assert "unverified (not in Gmail now):    2" in text
    assert "not in the record:              1" in text
    assert "file: assets/gmail/mbox/20260106_site_access.mbox" in text
    assert "mentioned in: assets/gmail/CATALOG.md:1" in text
    assert "inspection schedule and would propose" not in text.lower()
    assert "Unrelated" not in text and "something the matter never captured" not in text


def test_a_report_run_changes_nothing(matter: Path) -> None:
    before = sorted(str(p.relative_to(matter)) for p in matter.rglob("*"))
    _json(
        SETUP + "audit.formatReport(result, { matterDir, account: 'x' }); console.log('{}');",
        matter,
    )
    assert sorted(str(p.relative_to(matter)) for p in matter.rglob("*")) == before


#: Rendering needs a browser; the apply step's renderer is stubbed to
#: write a marker PDF so the test sees exactly what was re-rendered.
APPLY = r"""
const mbox = require('./mbox');
const realRender = require('./render');
const rendered = [];
const render = { ...realRender,
  renderMboxToPdf: async (m, pdf, o) => { rendered.push({ pdf, n: o.messages.length }); fs.writeFileSync(pdf, 'rerendered'); },
};
(async () => {
  const done = {};
  const added = audit.ensurePrivateIgnored(matterDir);
  const again = audit.ensurePrivateIgnored(matterDir);
  for (const f of result.findings) {
    done[f.stem] = await audit.applyFinding(f, { matterDir, outDir, ledger, render, quoted: 'show', identity: 'x' });
  }
  const mixed = path.join(outDir, 'mbox', '20260106_site_access.mbox');
  console.log(JSON.stringify({ added, again, done, rendered: rendered.map((r) => [path.basename(r.pdf), r.n]),
    ledger: ledger.threads, mixedKeys: mbox.readMessages(mixed).map(mbox.messageKey) }));
})();
"""


def test_apply_moves_drafts_out_and_rebuilds_mixed_threads(matter: Path) -> None:
    original_real = (matter / "assets/gmail/mbox/20260106_site_access.mbox").read_bytes()
    out = _json(SETUP + APPLY, matter)
    private = matter / ".private" / "gmail_drafts"

    assert out["added"] is True and out["again"] is False
    assert ".private/" in (matter / ".gitignore").read_text()

    # draft-only: every file moved, paths kept, nothing deleted, entry dropped
    s1 = "20260105_inspection_schedule"
    for rel in (
        f"assets/gmail/{s1}.pdf",
        f"assets/gmail/{s1}.txt",
        f"assets/gmail/attachments/{s1}/plan.pdf",
        f"assets/gmail/mbox/{s1}.mbox",
        f"derived/text/assets/gmail/{s1}.pdf.txt",
        f"derived/mail/threads/{s1}.txt",
    ):
        assert not (matter / rel).exists(), rel
        assert (private / s1 / rel).exists(), rel
    manifest = json.loads((private / s1 / "manifest.json").read_text())
    assert manifest["reason"] == "draft-only" and manifest["threadId"] == "t1"
    assert all(len(m.get("sha256", "x" * 64)) == 64 for m in manifest["moved"])
    assert manifest["ledgerEntry"]["filename"] == f"{s1}.pdf"
    assert "t1" not in out["ledger"]

    # mixed with an mbox: the original (draft and all) moved; the new mbox
    # holds the real message, byte-identical; the PDF is re-rendered
    s2 = "20260106_site_access"
    assert (private / s2 / f"assets/gmail/mbox/{s2}.mbox").read_bytes() == original_real
    assert out["mixedKeys"] == ["<r2@example.com>"]
    assert [s2 + ".pdf", 1] in out["rendered"]
    assert (matter / f"assets/gmail/{s2}.pdf").read_text() == "rerendered"
    assert out["ledger"]["t2"]["messageIds"] == ["r2"]
    assert out["ledger"]["t2"]["messageCount"] == 1
    assert not (matter / f"derived/text/assets/gmail/{s2}.pdf.txt").exists(), (
        "the stale sidecar moved out with the old render"
    )

    # the loose draft-only PDF moved; unverified and ordinary untouched
    assert (private / "20250410_lease_renewal" / "assets/gmail/20250410_lease_renewal.pdf").exists()
    assert out["done"]["20260107_keys"] == "not touched (unverified)"
    assert out["done"]["20250501_deposit"] == "not touched (unverified)"
    assert (matter / "assets/gmail/20250501_deposit.pdf").exists() and "t8" in out["ledger"]
    assert (matter / "assets/gmail/mbox/20260107_keys.mbox").exists()
    assert (matter / "assets/gmail/20260108_ordinary.pdf").exists()
    assert "t6" in out["ledger"] and "t3" in out["ledger"]

    # the PDF-only mixed render has no mbox and no Gmail here: moved, and
    # the report says it was not rebuilt
    assert "NOT rebuilt" in out["done"]["20250301_invoice"]
