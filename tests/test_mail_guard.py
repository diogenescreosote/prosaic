"""The mail watch (the address list is the only net; these are the alarms
on its edges): a failing connector interrupts and heads the brief, the
owner's sent mail names correspondents the list does not cover, exported
threads are announced in the brief, and an unsent draft is never mistaken
for a reply.

Nothing here touches Google: the gmail client is a hand-built stub.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"
SYNC = REPO_ROOT / "sync" / "matter_sync.sh"
GMAIL = REPO_ROOT / "connectors" / "gmail"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def sc(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SC), *argv], cwd=cwd, capture_output=True, text=True, timeout=300
    )


def _json(body: str) -> Any:
    proc = subprocess.run(["node", "-e", body], cwd=GMAIL, capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout)


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    m = tmp_path / "m"
    proc = sc("init", str(m), "--git", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    (m / "matter.yaml").write_text(
        "case:\n  name: Smith v. Roe\n"
        "connectors:\n  gmail:\n    addresses:\n      - examplefirm.com\n"
    )
    return m


# --- the connector: correspondents the list does not cover -----------------


@needs_node
def test_coverage_follows_gmail_s_own_address_rules() -> None:
    out = _json(
        r"""
        const p = require('./pull.js');
        const firm = ['examplefirm.com'];
        console.log(JSON.stringify({
          parsed: p.parseAddresses(
            'Jane Roe <Jane.Roe@ExampleFirm.com>, bob@vendor.example; "Q" <q@x.example>'),
          canon: [p.canonicalAddress('First.Last+tag@gmail.com'),
                  p.canonicalAddress('a+b@other.example')],
          domain: p.addressCovered('someone@mail.examplefirm.com', firm),
          otherDomain: p.addressCovered('someone@examplefirm.com.evil.example', firm),
          exact: p.addressCovered('Opposing@Example.com',
            [{ address: 'opposing@example.com', after: '2024/01/01' }]),
          miss: p.addressCovered('legal@vendor.example', ['examplefirm.com', 'other@example.com']),
          noise: [p.isNoiseAddress('no-reply@vendor.example'),
                  p.isNoiseAddress('notifications@svc.example'),
                  p.isNoiseAddress('legal@vendor.example'),
                  p.isNoiseAddress('owner+service@gmail.com', ['o.w.ner@gmail.com'])],
        }));
        """
    )
    assert out["parsed"] == ["jane.roe@examplefirm.com", "bob@vendor.example", "q@x.example"]
    assert out["canon"] == ["firstlast@gmail.com", "a@other.example"]
    assert out["domain"] is True and out["otherDomain"] is False
    assert out["exact"] is True and out["miss"] is False
    assert out["noise"] == [True, True, False, True]


@needs_node
def test_sent_mail_names_unlisted_recipients_without_fetching_a_body() -> None:
    """One in:sent listing, metadata-only gets, and every recipient the
    list does not cover comes back once with its newest sighting."""
    out = _json(
        r"""
        const p = require('./pull.js');
        const calls = [];
        const meta = {
          m1: { threadId: 't1', payload: { headers: [
            { name: 'To', value: 'Legal <legal@vendor.example>, jane@examplefirm.com' },
            { name: 'Cc', value: 'no-reply@vendor.example' },
            { name: 'Date', value: 'Wed, 03 Sep 2026 15:22:10 -0700' },
            { name: 'Subject', value: 'Preservation demand' } ] } },
          m2: { threadId: 't2', payload: { headers: [
            { name: 'To', value: 'legal@vendor.example' },
            { name: 'Date', value: 'Mon, 07 Sep 2026 20:15:49 -0700' },
            { name: 'Subject', value: 'Re: Preservation demand' } ] } },
          m3: { threadId: 't3', payload: { headers: [
            { name: 'To', value: 'me+service@gmail.com, promo@newsletter.example' },
            { name: 'Date', value: 'Tue, 08 Sep 2026 09:00:00 -0700' },
            { name: 'Subject', value: 'note to self' } ] } },
        };
        const gmail = { users: {
          messages: {
            list: async (q) => {
              calls.push({ q: q.q });
              return { data: { messages: [{ id: 'm1' }, { id: 'm2' }, { id: 'm3' }] } };
            },
            get: async (q) => {
              calls.push({ id: q.id, format: q.format, headers: q.metadataHeaders });
              return { data: { id: q.id, ...meta[q.id] } };
            },
          } } };
        (async () => {
          const rows = await p.collectUnlisted(gmail, {
            addresses: ['examplefirm.com'], ignore: ['newsletter.example'],
            ownAddresses: ['m.e@gmail.com'], newerThanDays: 3,
          });
          const previous = { correspondents: {
            'old@gone.example': { address: 'old@gone.example', date: '2026-01-01T00:00:00.000Z' },
            'now@examplefirm.com': {
              address: 'now@examplefirm.com', date: '2026-01-02T00:00:00.000Z' },
          } };
          const merged = p.mergeUnlisted(
            previous, rows, { addresses: ['examplefirm.com'], ignore: [], windowDays: 3 });
          console.log(JSON.stringify(
            { rows, calls, merged: Object.keys(merged.correspondents).sort() }));
        })();
        """
    )
    assert [r["address"] for r in out["rows"]] == ["legal@vendor.example"], (
        "listed, noise, own and ignored recipients are not correspondents"
    )
    row = out["rows"][0]
    assert row["subject"] == "Re: Preservation demand" and row["threadId"] == "t2", (
        "the newest sighting wins"
    )
    assert row["domain"] == "vendor.example"
    assert out["calls"][0]["q"] == "in:sent newer_than:3d"
    gets = [c for c in out["calls"] if "id" in c]
    assert all(c["format"] == "metadata" for c in gets), "never a body"
    assert all(set(c["headers"]) == {"To", "Cc", "Date", "Subject"} for c in gets)
    assert out["merged"] == ["legal@vendor.example", "old@gone.example"], (
        "a listed address drops out; an old one persists"
    )


@needs_node
def test_a_draft_in_a_thread_is_counted_but_never_a_message() -> None:
    out = _json(
        r"""
        const p = require('./pull.js');
        const gmail = { users: { threads: { get: async () => ({ data: { messages: [
          { id: 's1', labelIds: ['INBOX'], payload: { headers: [
            { name: 'Subject', value: 'Objection' },
            { name: 'Date', value: 'Thu, 10 Sep 2026 09:10:16 -0500' } ] } },
          { id: 'd1', labelIds: ['DRAFT'], payload: { headers: [
            { name: 'Subject', value: 'Re: Objection' },
            { name: 'Date', value: 'Thu, 10 Sep 2026 07:59:49 -0700' } ] } },
        ] } }) } } };
        (async () => {
          const meta = await p.fetchThreadMeta(gmail, { id: 't', historyId: '9' });
          console.log(JSON.stringify(meta));
        })();
        """
    )
    assert out["messageCount"] == 1 and out["messageIds"] == ["s1"]
    assert out["draftCount"] == 1 and out["latestDraftAt"] == "2026-09-10T14:59:49.000Z"


# --- the brief: the alarms ---------------------------------------------------


def _mbox(path: Path, sender: str, subject: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"From {sender} Thu Sep 10 14:10:16 2026\n"
        f"From: Vendor Legal <{sender}>\nTo: owner@example.com\n"
        f"Subject: {subject}\nDate: Thu, 10 Sep 2026 09:10:16 -0500\n"
        "Message-ID: <x@vendor.example>\n\nWe object.\n\n"
    )


def test_brief_leads_with_a_failing_connector_and_counts_the_runs(matter: Path) -> None:
    state = matter / ".state"
    state.mkdir(exist_ok=True)
    (state / "sync_last_success").write_text("1")
    (state / "sync_last_run.json").write_text(
        json.dumps(
            {
                "mode": "scheduled",
                "started": 1789000000,
                "finished": 1789000100,
                "outcome": "connector-failures",
                "new_files": 0,
                "triage": "skipped",
                "connectors": {"gmail": "failed", "docs": "ok"},
                "failed_connectors": ["gmail"],
                "failure_hints": {"gmail": "token rejected --- run: node connectors/gmail/auth.js"},
                "first_failure": 1788990000,
                "failed_runs_since_success": 3,
            }
        )
    )
    out = sc("brief", str(matter), cwd=matter).stdout
    first = out.splitlines()[0]
    assert first.startswith(
        "!! CONNECTOR FAILURE: gmail --- token rejected --- run: node connectors/gmail/auth.js"
    )
    assert "3 failed run(s)" in first and "since 2026-09-0" in first
    assert "(3 failed run(s) since)" in out
    assert "# Matter brief: Smith v. Roe" in out


def test_brief_announces_new_mail_unsent_drafts_and_unlisted_correspondents(matter: Path) -> None:
    state = matter / ".state"
    state.mkdir(exist_ok=True)
    _mbox(
        matter / "assets" / "gmail" / "mbox" / "20260903_preservation_demand.mbox",
        "legal@vendor.example",
        "Preservation demand",
    )
    (state / "gmail.json").write_text(
        json.dumps(
            {
                "version": 2,
                "accounts": {
                    "owner@example.com": {
                        "identity": "Owner <owner@example.com>",
                        "threads": {
                            "t1": {
                                "historyId": "1",
                                "messageCount": 4,
                                "filename": "20260903_preservation_demand.pdf",
                                "mbox": "mbox/20260903_preservation_demand.mbox",
                                "exportedAt": "2026-09-10T14:52:25.000Z",
                                "draftCount": 1,
                                "latestDraftAt": "2026-09-10T14:59:49.000Z",
                                "subject": "Preservation demand",
                            },
                            "t0": {
                                "historyId": "1",
                                "messageCount": 1,
                                "filename": "20250101_old.pdf",
                                "exportedAt": "2025-01-01T00:00:00.000Z",
                                "draftCount": 0,
                            },
                        },
                    }
                },
            }
        )
    )
    (state / "gmail_unlisted.json").write_text(
        json.dumps(
            {
                "version": 1,
                "correspondents": {
                    "legal@vendor.example": {
                        "address": "legal@vendor.example",
                        "domain": "vendor.example",
                        "date": "2026-09-08T03:15:49.000Z",
                        "subject": "Re: Preservation demand",
                        "threadId": "t1",
                    }
                },
            }
        )
    )
    # the brief has never run: the window reaches back to the export
    (state / "brief_last.json").write_text(json.dumps({"at": 1780000000}))
    out = sc("brief", str(matter), cwd=matter).stdout
    assert (
        "## New correspondence since" in out
        and "(1)" in out.split("## New correspondence since")[1].splitlines()[0]
    )
    assert "from vendor.example --- Preservation demand --- 20260903_preservation_demand.pdf" in out
    assert "20250101_old.pdf" not in out, "only what arrived inside the window"
    assert "## Unsent drafts in captured threads (1)" in out
    assert "Preservation demand --- 1 draft(s), latest 2026-09-10" in out
    assert "a draft is not a reply" in out
    assert "## Correspondents not on the address list (1)" in out
    assert (
        "legal@vendor.example --- 2026-09-0" in out and "add to connectors.gmail.addresses" in out
    )
    assert json.loads((state / "brief_last.json").read_text())["at"] > 1780000000, (
        "the brief stamps its own time"
    )


def test_brief_window_never_shrinks_below_a_day(matter: Path) -> None:
    state = matter / ".state"
    state.mkdir(exist_ok=True)
    _mbox(
        matter / "assets" / "gmail" / "mbox" / "20260910_letter.mbox",
        "legal@vendor.example",
        "Letter",
    )
    recent = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 3600))
    (state / "gmail.json").write_text(
        json.dumps(
            {
                "version": 2,
                "accounts": {
                    "owner@example.com": {
                        "identity": "owner@example.com",
                        "threads": {
                            "t1": {
                                "historyId": "1",
                                "messageCount": 1,
                                "filename": "20260910_letter.pdf",
                                "mbox": "mbox/20260910_letter.mbox",
                                "exportedAt": recent,
                            }
                        },
                    }
                },
            }
        )
    )
    (state / "brief_last.json").write_text(
        json.dumps({"at": time.time()})
    )  # a brief ran a moment ago
    out = sc("brief", str(matter), cwd=matter).stdout
    assert "20260910_letter.pdf" in out, "a compact or resume must not hide the morning's letter"


# --- the sync: a failing connector interrupts ------------------------------


def test_sync_records_the_failure_streak_and_the_fix(matter: Path, tmp_path: Path) -> None:
    conns = tmp_path / "connectors"
    (conns / "gmail").mkdir(parents=True)
    (conns / "gmail" / "pull.js").write_text(
        "console.error('Fatal: invalid_grant'); process.exit(1);\n"
    )
    (conns / "node_modules").mkdir()
    fake_agent = tmp_path / "agent.sh"
    fake_agent.write_text("#!/bin/bash\ncat >/dev/null\n")
    fake_agent.chmod(0o755)
    env = {
        **os.environ,
        "PROSAIC_ROOT": str(REPO_ROOT),
        "PROSAIC_CONNECTORS_DIR": str(conns),
        "PROSAIC_AGENT_CMD": str(fake_agent),
        "PROSAIC_NO_NOTIFY": "1",
        "PROSAIC_LOG_DIR": str(tmp_path / "logs"),
    }
    for _ in range(2):
        proc = subprocess.run(
            ["/bin/bash", str(SYNC), str(matter)],
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, proc.stderr
    summary = json.loads((matter / ".state" / "sync_last_run.json").read_text())
    assert summary["failed_connectors"] == ["gmail"]
    assert (
        summary["failure_hints"]["gmail"] == "token rejected --- run: node connectors/gmail/auth.js"
    )
    assert summary["failed_runs_since_success"] == 2
    assert (
        isinstance(summary["first_failure"], int) and summary["first_failure"] <= summary["started"]
    )
    assert not (matter / ".state" / "sync_last_success").exists(), (
        "a failing run never advances the guard"
    )
    log = next((tmp_path / "logs").glob("sync-*.log")).read_text()
    assert "NOTIFY: gmail failed" in log and "auth.js" in log
    brief = sc("brief", str(matter), cwd=matter).stdout
    assert brief.startswith("!! CONNECTOR FAILURE: gmail --- token rejected")
