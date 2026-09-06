"""The gmail connector's two layers, tested where they are pure.

ADR-0038 split the connector in half: capture writes raw RFC 822 bytes
into a per-thread mbox, and rendering turns one of those mboxes into a
PDF, an attachments directory, or an .eml — reading the stored bytes
and never the network. Both halves are therefore testable without a
mailbox, which is the point of the split and most of what is checked
here: an mbox round-trips byte-for-byte, a re-fetch adds nothing, a
quoted reply chain is present by default and collapsed on request,
attachments come out of the MIME parts, and two accounts' ledgers do
not collide.

Every message here is built in this file. Nothing in these tests
touches Google, a matter directory, or a browser.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GMAIL = REPO_ROOT / "connectors" / "gmail"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

CRLF = "\r\n"


def _node(body: str, env: dict[str, str] | None = None) -> str:
    """Run a JS snippet inside connectors/gmail; return its stdout."""
    proc = subprocess.run(
        ["node", "-e", body],
        cwd=GMAIL,
        capture_output=True,
        text=True,
        env=None if env is None else {**_base_env(), **env},
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def _base_env() -> dict[str, str]:
    return dict(os.environ)


def _json(body: str, env: dict[str, str] | None = None) -> Any:
    return json.loads(_node(body, env))


# --- fixture messages -------------------------------------------------
#
# Built by hand rather than with email.message so the bytes on the wire
# are exactly what the assertions talk about: CRLF line endings, the
# boundary shape real mailers emit, and a body line that begins "From "
# because that is the one thing an mbox has to survive.

PDF_BYTES = b"%PDF-1.4 not really a pdf"
PNG_BYTES = b"\x89PNG\r\n\x1a\nnot really a png"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def multipart_message(
    message_id: str = "thread-1-a@example.com",
    subject: str = "Scheduling the site inspection",
    sender: str = "Jane Roe <jane.roe@examplefirm.com>",
    date: str = "Mon, 5 Jan 2026 10:04:00 -0800",
) -> str:
    """A realistic message: alternative bodies, an attachment, an inline image.

    The HTML body carries both quoting conventions the renderer knows —
    a Gmail `gmail_quote` div and a `blockquote type="cite"` — plus a
    `cid:` reference to the inline image, so one fixture exercises
    quoted-text handling and the inline-vs-attachment rule at once.
    """
    alt = "ALTBOUNDARY"
    mixed = "MIXEDBOUNDARY"
    html_body = (
        '<div dir="ltr">The inspection is confirmed for the 14th.'
        '<img src="cid:sitelogo@example.com"></div>'
        '<div class="gmail_quote">'
        '<div class="gmail_attr">On Sun, Jan 4, 2026, John Smith wrote:</div>'
        '<blockquote type="cite">CAN WE DO THE FOURTEENTH INSTEAD</blockquote>'
        "</div>"
    )
    return CRLF.join(
        [
            f"Message-ID: <{message_id}>",
            f"Subject: {subject}",
            f"From: {sender}",
            "To: John Smith <john.smith@example.com>",
            "Cc: Clerk <clerk@example.org>",
            f"Date: {date}",
            "MIME-Version: 1.0",
            f'Content-Type: multipart/mixed; boundary="{mixed}"',
            "",
            f"--{mixed}",
            f'Content-Type: multipart/alternative; boundary="{alt}"',
            "",
            f"--{alt}",
            "Content-Type: text/plain; charset=UTF-8",
            "",
            "The inspection is confirmed for the 14th.",
            "> CAN WE DO THE FOURTEENTH INSTEAD",
            f"--{alt}",
            "Content-Type: text/html; charset=UTF-8",
            "",
            html_body,
            f"--{alt}--",
            f"--{mixed}",
            'Content-Type: application/pdf; name="Inspection Notice.pdf"',
            'Content-Disposition: attachment; filename="Inspection Notice.pdf"',
            "Content-Transfer-Encoding: base64",
            "",
            _b64(PDF_BYTES),
            f"--{mixed}",
            'Content-Type: image/png; name="sitelogo.png"',
            "Content-ID: <sitelogo@example.com>",
            'Content-Disposition: inline; filename="sitelogo.png"',
            "Content-Transfer-Encoding: base64",
            "",
            _b64(PNG_BYTES),
            f"--{mixed}--",
            "",
        ]
    )


def plain_message(
    message_id: str = "thread-1-b@example.com",
    body_lines: tuple[str, ...] = (
        "Confirmed.",
        "From the desk of John Smith",
        ">From an earlier note",
        "",
        "-- John",
    ),
) -> str:
    """A message whose body contains lines an mbox reader could mistake
    for a From_ separator. mboxrd exists for exactly this."""
    return CRLF.join(
        [
            f"Message-ID: <{message_id}>",
            "Subject: Re: Scheduling the site inspection",
            "From: John Smith <john.smith@example.com>",
            "To: Jane Roe <jane.roe@examplefirm.com>",
            "Date: Tue, 6 Jan 2026 09:15:00 -0800",
            "",
            *body_lines,
        ]
    )


def js_literal(text: str) -> str:
    return json.dumps(text)


def write_mbox_js(messages: list[tuple[str, str]]) -> str:
    """JS that writes a temp mbox holding `messages` as (gmail id, raw)."""
    entries = ",".join(
        f"{{id: {js_literal(mid)}, raw: Buffer.from({js_literal(raw)}, 'binary')}}"
        for mid, raw in messages
    )
    return textwrap.dedent(
        f"""
        const fs = require('fs'), os = require('os'), path = require('path');
        const mbox = require('./mbox');
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gmailtest-'));
        const mboxPath = path.join(dir, 'mbox', '20260105_scheduling.mbox');
        const messages = [{entries}];
        const first = mbox.appendMessages(mboxPath, messages);
        """
    )


# --- storage: mboxrd round-trip and dedup ------------------------------


def test_a_stored_message_reads_back_byte_for_byte() -> None:
    """The claim the whole design rests on: append then read is identity."""
    raw = multipart_message()
    out = _json(
        write_mbox_js([("m1", raw)])
        + """
        const back = mbox.readMessages(mboxPath);
        const original = messages[0].raw;
        console.log(JSON.stringify({
          count: back.length,
          identical: back[0].equals(original),
        }));
        """
    )
    assert out["count"] == 1
    assert out["identical"], "a message read out of the mbox differed from the one put in"


def test_from_lines_in_a_body_survive_the_round_trip() -> None:
    """mboxrd quoting is reversible: >From unquotes, >>From unquotes once."""
    raw = plain_message()
    out = _json(
        write_mbox_js([("m1", raw)])
        + """
        const stored = fs.readFileSync(mboxPath, 'binary');
        const back = mbox.readMessages(mboxPath)[0].toString('binary');
        console.log(JSON.stringify({
          storedHasQuoted: stored.includes('\\r\\n>From the desk'),
          storedHasDoubleQuoted: stored.includes('\\r\\n>>From an earlier note'),
          identical: back === messages[0].raw.toString('binary'),
        }));
        """
    )
    assert out["storedHasQuoted"], "a body line beginning 'From ' was not quoted on write"
    assert out["storedHasDoubleQuoted"], "an existing '>From ' line was not quoted again"
    assert out["identical"], "unquoting did not invert quoting"


def test_appending_the_same_message_twice_adds_nothing() -> None:
    """A re-fetched thread is deduplicated on Message-ID."""
    out = _json(
        write_mbox_js([("m1", multipart_message()), ("m2", plain_message())])
        + """
        const again = mbox.appendMessages(mboxPath, messages);
        const sizeBefore = fs.statSync(mboxPath).size;
        const grown = mbox.appendMessages(mboxPath, [
          ...messages,
          {id: 'm3', raw: Buffer.from(messages[1].raw.toString('binary')
              .replace('thread-1-b@example.com', 'thread-1-c@example.com'), 'binary')},
        ]);
        console.log(JSON.stringify({
          firstAdded: first.added,
          secondAdded: again.added,
          secondSkipped: again.skipped,
          grownAdded: grown.added,
          messages: mbox.readMessages(mboxPath).length,
          sizeUnchangedByRefetch: sizeBefore === fs.statSync(mboxPath).size - 0,
        }));
        """
    )
    assert out["firstAdded"] == ["m1", "m2"]
    assert out["secondAdded"] == []
    assert out["secondSkipped"] == ["m1", "m2"]
    assert out["grownAdded"] == ["m3"], "only the new message should be appended"
    assert out["messages"] == 3


def test_a_message_without_a_message_id_dedups_on_its_bytes() -> None:
    raw = plain_message().replace("Message-ID: <thread-1-b@example.com>" + CRLF, "")
    out = _json(
        write_mbox_js([("m1", raw)])
        + """
        const again = mbox.appendMessages(mboxPath, messages);
        console.log(JSON.stringify({
          key: mbox.messageKey(messages[0].raw).slice(0, 7),
          secondAdded: again.added,
          messages: mbox.readMessages(mboxPath).length,
        }));
        """
    )
    assert out["key"] == "sha256:"
    assert out["secondAdded"] == []
    assert out["messages"] == 1


def test_the_from_line_is_the_senders_address_and_a_utc_date() -> None:
    """Stored bytes must not depend on the reader's timezone."""
    out = _json(
        write_mbox_js([("m1", multipart_message())])
        + """
        const line = fs.readFileSync(mboxPath, 'utf-8').split('\\n')[0];
        console.log(JSON.stringify({line}));
        """,
        env={"TZ": "Asia/Tokyo"},
    )
    assert out["line"] == "From jane.roe@examplefirm.com Mon Jan  5 18:04:00 2026"


def test_the_mbox_path_is_the_pdf_stem() -> None:
    out = _json(
        """
        const path = require('path');
        const mbox = require('./mbox');
        console.log(JSON.stringify({
          p: mbox.mboxPathFor('/matter/assets/gmail', '20260105_scheduling.pdf'),
        }));
        """
    )
    assert out["p"] == "/matter/assets/gmail/mbox/20260105_scheduling.mbox"


# --- MIME reading -------------------------------------------------------


def test_the_parser_finds_both_bodies_and_the_parts() -> None:
    out = _json(
        write_mbox_js([("m1", multipart_message())])
        + """
        const mime = require('./mime');
        const node = mime.parseMessage(mbox.readMessages(mboxPath)[0]);
        const body = mime.findBody(node);
        const inline = mime.inlineParts(node);
        console.log(JSON.stringify({
          mimeType: node.mimeType,
          subject: node.header('Subject'),
          text: body.text.trim(),
          htmlHasImg: body.html.includes('cid:sitelogo@example.com'),
          inlineCids: Object.keys(inline),
          inlineBytes: inline['sitelogo@example.com'].content.length,
        }));
        """
    )
    assert out["mimeType"] == "multipart/mixed"
    assert out["subject"] == "Scheduling the site inspection"
    assert out["text"].startswith("The inspection is confirmed")
    assert out["htmlHasImg"]
    assert out["inlineCids"] == ["sitelogo@example.com"]
    assert out["inlineBytes"] == len(PNG_BYTES)


def test_encoded_words_and_quoted_printable_decode() -> None:
    """RFC 2047 subjects and RFC 2045 quoted-printable bodies."""
    raw = CRLF.join(
        [
            "Message-ID: <qp@example.com>",
            "Subject: =?utf-8?B?UsOpc3Vtw6kgb2YgY2hhcmdlcw==?=",
            "From: =?utf-8?Q?Fran=C3=A7ois_Roe?= <francois@example.com>",
            "To: john.smith@example.com",
            "Date: Wed, 7 Jan 2026 11:00:00 -0800",
            "MIME-Version: 1.0",
            "Content-Type: text/plain; charset=UTF-8",
            "Content-Transfer-Encoding: quoted-printable",
            "",
            "The fee was =E2=82=AC40 on a very long line that the mailer wrapped =",
            "right here.",
            "",
        ]
    )
    out = _json(
        write_mbox_js([("m1", raw)])
        + """
        const mime = require('./mime');
        const node = mime.parseMessage(mbox.readMessages(mboxPath)[0]);
        console.log(JSON.stringify({
          subject: node.header('Subject'),
          from: node.header('From'),
          text: mime.findBody(node).text.trim(),
        }));
        """
    )
    assert out["subject"] == "Résumé of charges"
    assert out["from"] == "François Roe <francois@example.com>"
    assert out["text"] == "The fee was €40 on a very long line that the mailer wrapped right here."


def test_an_rfc_2231_split_filename_reassembles() -> None:
    """Long or non-ASCII filenames arrive in numbered continuations."""
    raw = CRLF.join(
        [
            "Message-ID: <split@example.com>",
            "Subject: Exhibit",
            "From: jane.roe@examplefirm.com",
            "To: john.smith@example.com",
            "Date: Wed, 7 Jan 2026 11:00:00 -0800",
            "MIME-Version: 1.0",
            'Content-Type: multipart/mixed; boundary="B"',
            "",
            "--B",
            "Content-Type: text/plain",
            "",
            "See attached.",
            "--B",
            "Content-Type: application/pdf",
            "Content-Disposition: attachment;",
            ' filename*0="Quarterly statement for the ";',
            ' filename*1="Roe engagement.pdf"',
            "Content-Transfer-Encoding: base64",
            "",
            _b64(PDF_BYTES),
            "--B--",
            "",
        ]
    )
    out = _json(
        write_mbox_js([("m1", raw)])
        + """
        const render = require('./render');
        const thread = render.loadThread(mboxPath);
        console.log(JSON.stringify(
          render.listAttachments(thread).map((a) => [a.originalName, a.name, a.size])
        ));
        """
    )
    assert out == [
        [
            "Quarterly statement for the Roe engagement.pdf",
            "quarterly_statement_for_the_roe_engagement.pdf",
            len(PDF_BYTES),
        ]
    ]


# --- rendering ----------------------------------------------------------


RENDER_PROBE = """
const render = require('./render');
const thread = render.loadThread(mboxPath);
const me = 'Jane Roe <jane.roe@examplefirm.com>';
const shown = render.renderThreadHtml(thread, {account: me});
const hidden = render.renderThreadHtml(thread, {quoted: 'hide', account: me});
console.log(JSON.stringify({
  subject: render.threadSubject(thread),
  shownKeepsQuote: shown.includes('CAN WE DO THE FOURTEENTH INSTEAD'),
  hiddenKeepsQuote: hidden.includes('CAN WE DO THE FOURTEENTH INSTEAD'),
  hiddenHasMarker: hidden.includes('[Quoted text hidden]'),
  shownHasMarker: shown.includes('[Quoted text hidden]'),
  shownKeepsNewText: shown.includes('The inspection is confirmed'),
  hiddenKeepsNewText: hidden.includes('The inspection is confirmed'),
  inlineEmbedded: shown.includes('data:image/png;base64'),
  listsAttachment: shown.includes('Inspection Notice.pdf'),
  listsInlineImage: shown.includes('sitelogo.png'),
  identical: shown === render.renderThreadHtml(thread, {account: me}),
}));
"""


def test_quoted_text_is_shown_by_default_and_hidden_on_request() -> None:
    """The reason for ADR-0038: the stored rendering must be complete."""
    out = _json(write_mbox_js([("m1", multipart_message())]) + RENDER_PROBE)
    assert out["shownKeepsQuote"], "the default rendering dropped the quoted reply"
    assert not out["shownHasMarker"]
    assert not out["hiddenKeepsQuote"], "--quoted hide left the quoted reply in place"
    assert out["hiddenHasMarker"]
    assert out["shownKeepsNewText"] and out["hiddenKeepsNewText"]


def test_rendering_is_deterministic_and_lists_attachments() -> None:
    out = _json(write_mbox_js([("m1", multipart_message())]) + RENDER_PROBE)
    assert out["subject"] == "Scheduling the site inspection"
    assert out["identical"], "two renders of one mbox differed"
    assert out["inlineEmbedded"], "the cid: image was not embedded as a data URI"
    assert out["listsAttachment"], "the attachment was not listed in the print view"
    assert not out["listsInlineImage"], (
        "an image embedded in the rendering was also listed as an attachment"
    )


def test_a_plain_text_thread_renders_both_ways() -> None:
    out = _json(
        write_mbox_js(
            [
                (
                    "m1",
                    plain_message(
                        body_lines=(
                            "Received, thank you.",
                            "",
                            "On Mon, Jan 5, 2026, Jane Roe wrote:",
                            "> The inspection is confirmed for the 14th.",
                        )
                    ),
                )
            ]
        )
        + """
        const render = require('./render');
        const thread = render.loadThread(mboxPath);
        const shown = render.renderThreadHtml(thread, {});
        const hidden = render.renderThreadHtml(thread, {quoted: 'hide'});
        console.log(JSON.stringify({
          shownKeepsQuote: shown.includes('The inspection is confirmed'),
          hiddenKeepsQuote: hidden.includes('The inspection is confirmed'),
          hiddenHasMarker: hidden.includes('[Quoted text hidden]'),
        }));
        """
    )
    assert out["shownKeepsQuote"]
    assert not out["hiddenKeepsQuote"]
    assert out["hiddenHasMarker"]


def test_an_unreferenced_inline_image_is_treated_as_an_attachment() -> None:
    """A Content-ID is not proof a part was rendered.

    Mailers stamp Content-ID and an inline disposition onto genuine
    documents. The rule is what actually went into the HTML.
    """
    raw = multipart_message().replace('<img src="cid:sitelogo@example.com">', "")
    out = _json(
        write_mbox_js([("m1", raw)])
        + """
        const render = require('./render');
        const thread = render.loadThread(mboxPath);
        console.log(JSON.stringify(
          render.listAttachments(thread).map((a) => a.name)
        ));
        """
    )
    assert out == ["inspection_notice.pdf", "sitelogo.png"]


# --- attachments and .eml ----------------------------------------------


def test_attachments_are_extracted_from_the_mail_not_refetched() -> None:
    out = _json(
        write_mbox_js([("m1", multipart_message())])
        + """
        const render = require('./render');
        const thread = render.loadThread(mboxPath);
        const dest = path.join(dir, 'attachments', '20260105_scheduling');
        const written = render.extractAttachments(thread, dest);
        const again = render.extractAttachments(thread, dest);
        console.log(JSON.stringify({
          written: written.map((f) => [path.basename(f.path), f.size, f.created]),
          again: again.map((f) => f.created),
          bytes: fs.readFileSync(written[0].path).toString('binary'),
        }));
        """
    )
    assert out["written"] == [["inspection_notice.pdf", len(PDF_BYTES), True]]
    assert out["again"] == [False], "a second extraction rewrote a file already there"
    assert out["bytes"].encode("latin-1") == PDF_BYTES


def test_colliding_attachment_names_get_deterministic_suffixes() -> None:
    second = multipart_message(
        message_id="thread-1-c@example.com", date="Tue, 6 Jan 2026 08:00:00 -0800"
    )
    out = _json(
        write_mbox_js([("m1", multipart_message()), ("m2", second)])
        + """
        const render = require('./render');
        const thread = render.loadThread(mboxPath);
        const names = render.listAttachments(thread).map((a) => a.name);
        const again = render.listAttachments(render.loadThread(mboxPath)).map((a) => a.name);
        const stable = JSON.stringify(names) === JSON.stringify(again);
        console.log(JSON.stringify({names, stable}));
        """
    )
    assert out["names"] == ["inspection_notice.pdf", "inspection_notice_2.pdf"]
    assert out["stable"]


def test_an_oversized_attachment_is_reported_and_not_written() -> None:
    out = _json(
        write_mbox_js([("m1", multipart_message())])
        + """
        const render = require('./render');
        const thread = render.loadThread(mboxPath);
        const skipped = [];
        // A one-byte cap rather than a 25MB fixture.
        const written = render.extractAttachments(
          thread, path.join(dir, 'atts'),
          {maxBytes: 1, onSkip: (a) => skipped.push(a.originalName)}
        );
        const normal = render.extractAttachments(thread, path.join(dir, 'atts2'));
        console.log(JSON.stringify({
          written: written.length,
          skipped,
          normal: normal.length,
          cap: render.MAX_ATTACHMENT_BYTES,
        }));
        """
    )
    assert out["written"] == 0, "an oversized attachment was written anyway"
    assert out["skipped"] == ["Inspection Notice.pdf"]
    assert out["normal"] == 1, "the same part is written under the real cap"
    assert out["cap"] == 25 * 1024 * 1024, "Gmail's own send limit is the cap"


def test_one_message_comes_back_out_as_eml() -> None:
    """An .eml IS an RFC 822 message, so emitting one is a copy."""
    out = _json(
        write_mbox_js([("m1", multipart_message()), ("m2", plain_message())])
        + """
        const render = require('./render');
        const thread = render.loadThread(mboxPath);
        const dest = path.join(dir, 'out', 'second.eml');
        render.emitEml(thread, 2, dest);
        let error = null;
        try { render.emitEml(thread, 9, null); } catch (e) { error = e.message; }
        console.log(JSON.stringify({
          identical: fs.readFileSync(dest).equals(storedSecond()),
          error,
        }));
        function storedSecond() { return require('./mbox').readMessages(mboxPath)[1]; }
        """
    )
    assert out["identical"], ".eml emission changed the stored bytes"
    assert "no message 9" in out["error"]


def test_the_attachments_directory_is_derived_from_the_mbox() -> None:
    out = _json(
        """
        const render = require('./render');
        console.log(JSON.stringify({
          d: render.attachmentsDirFor('/m/assets/gmail/mbox/20260105_scheduling.mbox'),
        }));
        """
    )
    assert out["d"] == "/m/assets/gmail/attachments/20260105_scheduling"


# --- accounts and the ledger -------------------------------------------


def test_configured_accounts_default_to_one_unnamed_mailbox() -> None:
    out = _json(
        """
        const creds = require('./creds');
        console.log(JSON.stringify({
          none: creds.configuredAccounts({addresses: ['a@example.com']}),
          listed: creds.configuredAccounts({accounts: ['jane@example.com', 'service@example.com']}),
          keyNone: creds.accountKey(null),
          keyListed: creds.accountKey('Jane@Example.com'),
        }));
        """
    )
    assert out["none"] == [None]
    assert out["listed"] == ["jane@example.com", "service@example.com"]
    assert out["keyNone"] == "default"
    assert out["keyListed"] == "jane@example.com"


def test_the_first_account_inherits_the_pre_accounts_token(tmp_path: Path) -> None:
    """Adding a second mailbox costs one authorization, not two."""
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir()
    (creds_dir / "credentials.json").write_text("{}")
    out = _json(
        """
        const creds = require('./creds');
        console.log(JSON.stringify({
          primary: creds.tokenPath('jane@example.com', {primary: true}),
          second: creds.tokenPath('service@example.com', {primary: false}),
          legacy: creds.tokenPath(null),
          slug: creds.accountSlug('Service.Desk+mail@example.com'),
        }));
        """,
        env={"PROSAIC_GMAIL_CREDS_DIR": str(creds_dir)},
    )
    assert out["primary"] == str(creds_dir / "credentials.json")
    assert out["second"] == str(creds_dir / "credentials-service_example_com.json")
    assert out["legacy"] == str(creds_dir / "credentials.json")
    assert out["slug"] == "service_desk_mail_example_com"

    # Once the primary has a token of its own, it stops borrowing.
    (creds_dir / "credentials-jane_example_com.json").write_text("{}")
    out = _json(
        """
        const creds = require('./creds');
        console.log(JSON.stringify({
          primary: creds.tokenPath('jane@example.com', {primary: true}),
        }));
        """,
        env={"PROSAIC_GMAIL_CREDS_DIR": str(creds_dir)},
    )
    assert out["primary"] == str(creds_dir / "credentials-jane_example_com.json")


def test_two_accounts_keep_separate_thread_ledgers(tmp_path: Path) -> None:
    """Gmail thread ids are per-mailbox, so the same id means two threads."""
    matter = tmp_path / "matter"
    (matter / ".state").mkdir(parents=True)
    out = _json(
        f"""
        const pull = require('./pull');
        const path = require('path');
        const matter = {js_literal(str(matter))};
        const outDir = path.join(matter, 'assets', 'gmail');
        const state = pull.loadLedger(matter, 'jane@example.com');
        pull.ledgerFor(state, 'jane@example.com').threads['17abc'] = {{
          filename: '20260105_scheduling.pdf',
          messageCount: 2,
          mbox: 'mbox/20260105_scheduling.mbox',
        }};
        pull.ledgerFor(state, 'service@example.com').threads['17abc'] = {{
          filename: '20260105_scheduling_2.pdf',
          messageCount: 1,
          mbox: 'mbox/20260105_scheduling_2.mbox',
        }};
        console.log(JSON.stringify({{
          keys: Object.keys(state.accounts).sort(),
          jane: state.accounts['jane@example.com'].threads['17abc'].filename,
          service: state.accounts['service@example.com'].threads['17abc'].filename,
          claimed: [...pull.claimedFilenames(state, outDir)].sort(),
          version: state.version,
        }}));
        """
    )
    assert out["keys"] == ["jane@example.com", "service@example.com"]
    assert out["jane"] == "20260105_scheduling.pdf"
    assert out["service"] == "20260105_scheduling_2.pdf"
    assert out["claimed"] == [
        "20260105_scheduling.pdf",
        "20260105_scheduling_2.pdf",
    ]
    assert out["version"] == 2


def test_a_single_mailbox_ledger_migrates_under_the_primary(tmp_path: Path) -> None:
    """A matter that predates `accounts:` must not re-export its history."""
    matter = tmp_path / "matter"
    (matter / ".state").mkdir(parents=True)
    (matter / ".state" / "gmail.json").write_text(
        json.dumps(
            {
                "threads": {
                    "17abc": {
                        "historyId": "900",
                        "messageCount": 2,
                        "filename": "20260105_scheduling.pdf",
                    }
                }
            }
        )
    )
    out = _json(
        f"""
        const pull = require('./pull');
        const state = pull.loadLedger({js_literal(str(matter))}, 'jane@example.com');
        console.log(JSON.stringify({{
          topLevelThreads: state.threads === undefined,
          version: state.version,
          migrated: state.accounts['jane@example.com'].threads['17abc'],
        }}));
        """
    )
    assert out["topLevelThreads"], "the v1 threads map was left at the top level"
    assert out["version"] == 2
    assert out["migrated"]["filename"] == "20260105_scheduling.pdf"
    assert "mbox" not in out["migrated"], (
        "a migrated entry must have no mbox — --backfill-mbox is how it gets one"
    )


def test_the_default_key_is_used_when_no_accounts_are_configured(tmp_path: Path) -> None:
    matter = tmp_path / "matter"
    (matter / ".state").mkdir(parents=True)
    (matter / ".state" / "gmail.json").write_text(
        json.dumps({"threads": {"17abc": {"filename": "a.pdf"}}})
    )
    out = _json(
        f"""
        const pull = require('./pull');
        const creds = require('./creds');
        const state = pull.loadLedger({js_literal(str(matter))}, creds.accountKey(null));
        console.log(JSON.stringify({{keys: Object.keys(state.accounts)}}));
        """
    )
    assert out["keys"] == ["default"]


# --- argument handling --------------------------------------------------


def test_a_flag_value_is_not_mistaken_for_the_matter_directory() -> None:
    """`pull.js --limit 50 .` names one matter, not two."""
    out = _node(
        """
        const pull = require('./pull');
        process.argv = ['node', 'pull.js', '--backfill-mbox', '--limit', '50',
                        '--account', 'jane@example.com', '/tmp/matter'];
        console.log(JSON.stringify(pull.positionalArgs()));
        """
    )
    assert json.loads(out) == ["/tmp/matter"]


# --- capture -----------------------------------------------------------


def test_capture_fetches_raw_bytes_per_message_not_per_thread() -> None:
    """threads.get has no raw format; the bytes come from messages.get.

    A fake client records every call so the test pins both the thread
    view requested (minimal) and the per-message raw fetch, and the
    appended mbox reads back the exact bytes.
    """
    out = _json(
        r"""
        const fs = require('fs'); const os = require('os'); const path = require('path');
        const pull = require('./pull.js'); const mbox = require('./mbox.js');
        const raw = (n) => Buffer.from(
          'From: Jane Roe <jane@example.com>\r\nTo: John Smith <john@example.com>\r\n' +
          'Subject: capture ' + n + '\r\nMessage-ID: <cap-' + n + '@example.com>\r\n' +
          'Date: Mon, 01 Jan 2024 10:0' + n + ':00 +0000\r\n\r\nbody ' + n + '\r\n');
        const calls = [];
        const stubs = [{ id: 'm1', internalDate: '1' }, { id: 'm2', internalDate: '2' }];
        const gmail = { users: {
          threads: { get: async (p) => {
            calls.push(['threads.get', p.format]);
            return { data: { messages: stubs } };
          } },
          messages: { get: async (p) => {
            calls.push(['messages.get', p.format, p.id]);
            const n = p.id === 'm1' ? 1 : 2;
            const b64 = raw(n).toString('base64url');
            return { data: { id: p.id, internalDate: String(n), raw: b64 } };
          } },
        } };
        (async () => {
          const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cap-'));
          const mboxPath = path.join(dir, 'mbox', 't.mbox');
          const result = await pull.captureThread(gmail, 'thread-1', mboxPath);
          const stored = mbox.readMessages(mboxPath).map((b) => b.toString('binary'));
          const same = stored.length === 2
            && stored[0] === raw(1).toString('binary')
            && stored[1] === raw(2).toString('binary');
          console.log(JSON.stringify({ calls, added: result.added, total: result.total, same }));
        })();
        """
    )
    assert out["calls"][0] == ["threads.get", "minimal"]
    assert out["calls"][1:] == [["messages.get", "raw", "m1"], ["messages.get", "raw", "m2"]]
    assert out["added"] == ["m1", "m2"]
    assert out["total"] == 2
    assert out["same"], "the stored bytes must be the raw bytes, unchanged"


def test_a_thread_that_changed_without_growing_is_re_exported() -> None:
    """A deleted send replaced by another leaves the count alone.

    The ledger remembers which message ids it exported, so a changed id
    set re-exports even at the same count; an entry from before ids were
    recorded falls back to the count comparison.
    """
    out = _json(
        r"""
        const { threadChanged } = require('./pull.js');
        const prev = { messageCount: 1, messageIds: ['a'] };
        console.log(JSON.stringify({
          same: threadChanged(prev, { messageCount: 1, messageIds: ['a'] }),
          replaced: threadChanged(prev, { messageCount: 1, messageIds: ['b'] }),
          grown: threadChanged(prev, { messageCount: 2, messageIds: ['a', 'b'] }),
          shrunk: threadChanged({ messageCount: 2, messageIds: ['a', 'b'] },
                                { messageCount: 1, messageIds: ['a'] }),
          legacySame: threadChanged({ messageCount: 1 },
                                    { messageCount: 1, messageIds: ['b'] }),
          legacyGrown: threadChanged({ messageCount: 1 },
                                     { messageCount: 2, messageIds: ['a', 'b'] }),
          forced: threadChanged(prev, { messageCount: 1, messageIds: ['a'] }, true),
        }));
        """
    )
    assert out == {
        "same": False,
        "replaced": True,
        "grown": True,
        "shrunk": True,
        "legacySame": False,
        "legacyGrown": True,
        "forced": True,
    }
