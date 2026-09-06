#!/usr/bin/env node
//
// render.js — the gmail connector's presentation layer.
//
// Capture and presentation are separate steps (ADR-0038). Capture puts
// raw RFC 822 bytes in an mbox; this module turns one of those mboxes
// into the artifacts a matter reads — Gmail's print view as a PDF, the
// thread's attachments as files, a single message as .eml — and it
// does so as a pure function of (mbox, options). Nothing here talks to
// the Gmail API, so any stored thread can be re-rendered years later,
// with different options, from the bytes alone.
//
// Usage:
//   sc mail-render <thread.mbox> [options]
//   node render.js <thread.mbox> [options]      (the same thing)
//
//   --pdf <path>          write the print-view PDF
//   --html <path>         write the intermediate HTML
//   --quoted show|hide    include quoted reply chains (default: show)
//   --attachments [dir]   extract attachment parts (default: the
//                         sibling attachments/<stem>/ directory)
//   --eml <n>[:<path>]    write message n (1-based) as .eml (stdout
//                         when no path is given)
//   --list                list the messages and attachments
//   --subject <text>      override the thread subject
//   --account <identity>  the mailbox identity in the header line
//
// --quoted show is the default and is the difference between an
// archive and an exhibit: Gmail's own print view collapses a reply
// chain to "[Quoted text hidden]", which is fine for a person who can
// scroll the thread and useless as a record. --quoted hide reproduces
// Gmail's behavior for anyone who wants the familiar shape.

'use strict';

const fs = require('fs');
const path = require('path');

const cheerio = require('cheerio');

const mbox = require('./mbox');
const mime = require('./mime');

//: Gmail's own print view pulls its logo and file-type icons from
//: gstatic; keeping the same URLs keeps the output recognizable as a
//: Gmail printout. A render with no network loses the images and
//: nothing else.
const GMAIL_LOGO_URL =
  'https://ssl.gstatic.com/ui/v1/icons/mail/rfr/logo_gmail_server_1x.png';
const ICON_BASE = 'https://ssl.gstatic.com/docs/doclist/images';
const ICON_BY_EXTENSION = {
  pdf: `${ICON_BASE}/icon_10_pdf_list.png`,
  doc: `${ICON_BASE}/icon_10_word_list.png`,
  docx: `${ICON_BASE}/icon_10_word_list.png`,
  xls: `${ICON_BASE}/icon_10_excel_list.png`,
  xlsx: `${ICON_BASE}/icon_10_excel_list.png`,
  ppt: `${ICON_BASE}/icon_10_powerpoint_list.png`,
  pptx: `${ICON_BASE}/icon_10_powerpoint_list.png`,
  png: `${ICON_BASE}/icon_10_image_list.png`,
  jpg: `${ICON_BASE}/icon_10_image_list.png`,
  jpeg: `${ICON_BASE}/icon_10_image_list.png`,
  gif: `${ICON_BASE}/icon_10_image_list.png`,
};
const ICON_GENERIC = `${ICON_BASE}/icon_10_generic_list.png`;

//: Attachments over this size are listed in the PDF but not written
//: out. Gmail's own send limit is 25MB, so nothing legitimate exceeds
//: it and anything that does is a decompression surprise.
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;

const QUOTED_HIDDEN_HTML =
  '<div><font size="1" color="#888888">[Quoted text hidden]</font></div>';

const PDF_OPTIONS = {
  format: 'Letter',
  printBackground: true,
  displayHeaderFooter: false,
  margin: { top: '0.3in', bottom: '0.3in', left: '0.4in', right: '0.4in' },
};

const QUOTED_MODES = ['show', 'hide'];
const DEFAULT_QUOTED_MODE = 'show';

// --- small formatters -------------------------------------------------

function esc(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return esc(dateStr);
  const datePart = d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const timePart = d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
  return esc(`${datePart} at ${timePart}`);
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  return `${Math.round(bytes / 1024)}K`;
}

function parseSender(from) {
  const m = String(from || '').match(/^(.+?)\s*<(.+?)>$/);
  if (m) return { name: m[1].replace(/"/g, '').trim(), email: m[2] };
  return { name: from || '', email: from || '' };
}

/**
 * A saved attachment keeps its own name, sanitized the way subjects
 * are (lowercase, runs of non-alphanumerics to _), extension
 * preserved. Unlike a subject it does NOT lose a leading "re:" — that
 * rule is about reply subjects, and a filename is not a subject.
 */
function safeAttachmentName(filename) {
  const m = String(filename || '').match(/^(.*?)(\.[A-Za-z0-9]{1,8})?$/);
  const stem =
    (m[1] || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '')
      .substring(0, 80) || 'attachment';
  return stem + (m[2] || '').toLowerCase();
}

// --- quoted-reply suppression (--quoted hide only) ---------------------

// keepAll: the message is itself a FORWARD (subject Fw:/Fwd:) --- its
// body IS the forwarded material, including any From:/Sent: header
// blocks and interior reply chains, none of which duplicates other
// thread content. Strip nothing.
function stripQuotedHtml(html, keepAll) {
  if (keepAll) return html;
  const $ = cheerio.load(html, { xmlMode: false, decodeEntities: false });

  // Gmail web replies. A FORWARD's body also lives inside gmail_quote,
  // and unlike a reply quote (which duplicates an earlier message of the
  // same thread) forwarded content exists nowhere else in the export ---
  // hiding it destroys the only copy. Keep any quote block that opens as
  // a forwarded message, including its gmail_attr header block
  // (From/Date/Subject/To of the original sender is evidence).
  const FWD = /-{5,}\s*Forwarded message\s*-{5,}/;
  // True when el sits inside a forwarded-message block that is being
  // kept; no stripping rule may fire in there --- the forward's interior
  // ("On ... wrote:" lines included) is unique content, not duplication.
  function insideForward(el) {
    const q = $(el).closest('div.gmail_quote');
    return q.length > 0 && FWD.test(q.text());
  }
  $('div.gmail_quote').each(function () {
    if (FWD.test($(this).text())) return;
    if (insideForward(this)) return;
    $(this).replaceWith(QUOTED_HIDDEN_HTML);
  });
  $('div.gmail_attr').each(function () {
    if (FWD.test($(this).text())) return;
    $(this).remove();
  });
  $('div.gmail_extra').each(function () {
    if (FWD.test($(this).text())) return;
    $(this).replaceWith(QUOTED_HIDDEN_HTML);
  });

  // Actual reply-style blockquotes. Do not hide all blockquotes globally:
  // some messages use blockquote purely for indentation/formatting rather than
  // quoted reply content. Reply HTML commonly marks quoted sections with
  // type="cite" (Apple Mail, Thunderbird, etc.).
  $('blockquote[type="cite"]').each(function () {
    if (insideForward(this)) return;
    $(this).replaceWith(QUOTED_HIDDEN_HTML);
  });

  // Rule-then-header replies: <hr> followed by a From/Sent/To block.
  $('hr').each(function () {
    if (insideForward(this)) return;
    const next = $(this).next();
    const nextText = next.text().trim();
    if (/^From:/.test(nextText) || next.find('b').first().text().trim() === 'From:') {
      $(this).nextAll().remove();
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // The divRplyFwdMsg / appendonsend pattern.
  $('[id*="divRplyFwdMsg"], [id*="appendonsend"]').each(function () {
    if (insideForward(this)) return;
    $(this).nextAll().remove();
    $(this).replaceWith(QUOTED_HIDDEN_HTML);
  });

  // "On [date] ... wrote:" followed by quoted content
  $('div, span, p').each(function () {
    if (insideForward(this)) return;
    const t = $(this).text().trim();
    if (/^On\s.+wrote:$/.test(t)) {
      $(this).nextAll().remove();
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // Inline reply header: "On [date], at [time], [name] wrote:"
  $('div, span, p').each(function () {
    if (insideForward(this)) return;
    const t = $(this).text().trim();
    if (/^On\s.+,\s+at\s+.+,\s+.+wrote:$/.test(t)) {
      $(this).nextAll().remove();
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // Generic: any element containing only "> " prefixed lines (plain-text quotes in HTML)
  $('div, p, pre').each(function () {
    if (insideForward(this)) return;
    const lines = $(this).text().split('\n');
    if (lines.length > 2 && lines.every((l) => l.trim() === '' || l.startsWith('>'))) {
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // Collapse consecutive markers
  let result = $.html();
  const marker = QUOTED_HIDDEN_HTML.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  result = result.replace(new RegExp(`(\\s*${marker}\\s*){2,}`, 'g'), QUOTED_HIDDEN_HTML);
  return result;
}

function stripQuotedText(text, keepAll) {
  if (keepAll) return text;
  const lines = String(text).split('\n');
  const out = [];
  let inQuote = false;
  for (const line of lines) {
    const isQuoteLine =
      line.startsWith('>') || (/^On .+ wrote:/.test(line) && !inQuote);
    if (isQuoteLine) {
      if (!inQuote) {
        out.push('[Quoted text hidden]');
        inQuote = true;
      }
    } else if (line.trim() === '' && inQuote) {
      // skip blank lines inside quotes
    } else {
      inQuote = false;
      out.push(line);
    }
  }
  return out.join('\n');
}

// --- one message ------------------------------------------------------

/**
 * Substitute cid: references with data: URIs from the message's own
 * parts. Returns {html, embeddedCids}: anything NOT in that set is not
 * in the PDF, however its MIME headers label it, and is therefore a
 * real attachment.
 */
function embedInlineImages(html, node) {
  const byCid = mime.inlineParts(node);
  const embeddedCids = new Set();
  const refs = [...html.matchAll(/src=["']cid:([^"']+)["']/gi)];
  for (const match of refs) {
    const cid = match[1];
    const part = byCid[cid];
    if (!part || !part.content) continue;
    html = html.replace(
      new RegExp(`src=["']cid:${cid.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["']`, 'gi'),
      `src="data:${part.mimeType};base64,${part.content.toString('base64')}"`
    );
    embeddedCids.add(cid);
  }
  return { html, embeddedCids };
}

function renderBody(body, keepAll, quoted) {
  const hide = quoted === 'hide';
  if (body.html) {
    let clean = body.html
      .replace(/<html[^>]*>/gi, '')
      .replace(/<\/html>/gi, '')
      .replace(/<head[^>]*>[\s\S]*?<\/head>/gi, '')
      .replace(/<body[^>]*>/gi, '')
      .replace(/<\/body>/gi, '');
    if (hide) clean = stripQuotedHtml(clean, keepAll);
    return clean;
  }
  const text = hide ? stripQuotedText(body.text, keepAll) : body.text;
  return `<div dir="ltr">${esc(text).replace(/\n/g, '<br>')}</div>`;
}

function attachmentRows(attachments) {
  if (!attachments.length) return '';
  const rows = attachments
    .map((a) => {
      const ext = (a.name.match(/\.(\w+)$/) || ['', ''])[1].toLowerCase();
      const iconUrl = ICON_BY_EXTENSION[ext] || ICON_GENERIC;
      return `<tr><td style="padding:4px 0;">
        <table cellpadding="0" cellspacing="0" border="0"><tr>
          <td valign="top" style="padding-right:6px;"><img src="${iconUrl}" width="16" height="16"></td>
          <td><font size="-1"><b>${esc(a.name)}</b><br><span style="color:#666">${fmtSize(a.size)}</span></font></td>
        </tr></table>
      </td></tr>`;
    })
    .join('\n');
  return `<tr><td colspan="2" style="padding: 4px 12px;">
    <table cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #ddd;padding-top:8px;margin-top:6px;width:100%">
    <tr><td><font size="-1"><b>${attachments.length} attachment${
    attachments.length > 1 ? 's' : ''
  }</b></font></td></tr>
    ${rows}
    </table>
  </td></tr>`;
}

// --- the thread -------------------------------------------------------

/** Parse an mbox into the message list every function here consumes. */
function loadThread(mboxPath) {
  return mbox.readMessages(mboxPath).map((raw, index) => ({
    index,
    raw,
    node: mime.parseMessage(raw),
  }));
}

/** The thread's subject: the first message's, as Gmail titles it. */
function threadSubject(messages) {
  for (const m of messages) {
    const subject = m.node.header('Subject');
    if (subject) return subject;
  }
  return 'no_subject';
}

/**
 * Every attachment in the thread, in thread order then part order,
 * with the collision-suffixed name it is written under.
 *
 * The suffixes (_2, _3 …) are deterministic — messages are stored in
 * thread order and parts are walked depth-first — so a re-render
 * resolves each attachment to the same path as the run before it.
 */
function listAttachments(messages) {
  const taken = new Set();
  const out = [];
  for (const message of messages) {
    const body = mime.findBody(message.node);
    let embeddedCids = new Set();
    if (body.html) embeddedCids = embedInlineImages(body.html, message.node).embeddedCids;
    for (const part of mime.attachmentParts(message.node, embeddedCids)) {
      let name = safeAttachmentName(part.filename);
      if (taken.has(name)) {
        const m = name.match(/^(.*?)(\.[a-z0-9]+)?$/);
        let i = 2;
        while (taken.has(`${m[1]}_${i}${m[2] || ''}`)) i++;
        name = `${m[1]}_${i}${m[2] || ''}`;
      }
      taken.add(name);
      out.push({
        name,
        originalName: part.filename,
        size: part.size,
        messageIndex: message.index,
        part,
      });
    }
  }
  return out;
}

/**
 * Render the thread as Gmail's print view.
 *
 * Pure: same messages plus same options, same HTML, every time.
 */
function renderThreadHtml(messages, options = {}) {
  const quoted = options.quoted || DEFAULT_QUOTED_MODE;
  const subject = options.subject || threadSubject(messages);
  const account = options.account || '';
  const identity = parseSender(account);

  let msgHtml = '';
  for (const message of messages) {
    const node = message.node;
    const from = node.header('From');
    const to = node.header('To');
    const cc = node.header('Cc');
    const dateStr = node.getHeader('Date');
    const { name: senderName, email: senderEmail } = parseSender(from);
    // A forwarded message's body IS forwarded material: Gmail wraps it
    // in gmail_quote (handled in stripQuotedHtml), but other mailers
    // forward as a plain From:/Sent: block the reply-strippers would
    // truncate. Subject is the reliable tell. Only matters under
    // --quoted hide, where anything is stripped at all.
    const msgSubject = node.header('Subject') || subject || '';
    const isForward = /^\s*(fwd?|fw)\s*:/i.test(msgSubject);

    const body = mime.findBody(node);
    let embeddedCids = new Set();
    if (body.html) {
      const resolved = embedInlineImages(body.html, node);
      body.html = resolved.html;
      embeddedCids = resolved.embeddedCids;
    }
    const atts = mime
      .attachmentParts(node, embeddedCids)
      .map((part) => ({ name: part.filename, size: part.size }));

    msgHtml += `<hr>
<table width="100%" cellpadding="0" cellspacing="0" border="0" class="message">
<tbody>
<tr>
  <td><font size="-1"><b>${esc(senderName)} </b>&lt;${esc(senderEmail)}&gt;</font></td>
  <td align="right"><font size="-1">${fmtDate(dateStr)}</font></td>
</tr>
<tr><td colspan="2" style="padding-bottom: 4px;">
  <font size="-1" class="recipient"><div>To: ${esc(to)}</div>${
      cc ? `<div>Cc: ${esc(cc)}</div>` : ''
    }</font>
</td></tr>
<tr><td colspan="2">
  <table width="100%" cellpadding="12" cellspacing="0" border="0">
  <tbody><tr><td>
    <div style="overflow: hidden;"><font size="-1">${renderBody(
      body,
      isForward,
      quoted
    )}</font></div>
  </td></tr></tbody>
  </table>
</td></tr>
${attachmentRows(atts)}
</tbody></table>`;
  }

  const msgCount = messages.length;
  const html = `<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "https://www.w3.org/TR/html4/strict.dtd">
<html lang="en"><head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<style type="text/css">
body,td,div,p,a,input{font-family:arial,sans-serif}
body,td{font-size:13px}
a:link,a:active{color:#1155CC;text-decoration:none}
a:hover{text-decoration:underline;cursor:pointer}
a:visited{color:#6611CC}
img{border:0px}
pre{white-space:pre;white-space:-moz-pre-wrap;white-space:-o-pre-wrap;white-space:pre-wrap;word-wrap:break-word;max-width:800px;overflow:auto}
.logo{left:-7px;position:relative}
@media print{.message{page-break-inside:avoid}}
</style>
</head><body>
<div class="bodycontainer">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tbody><tr height="14px">
  <td width="143"><img src="${GMAIL_LOGO_URL}" width="143" height="59" alt="Gmail" class="logo"></td>
  <td align="right"><font size="-1" color="#777"><b>${esc(identity.name)}${
    identity.email ? ` &lt;${esc(identity.email)}&gt;` : ''
  }</b></font></td>
</tr></tbody></table>
<hr>
<div class="maincontent">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tbody><tr><td>
  <font size="+1"><b>${esc(subject)}</b></font><br>
  <font size="-1" color="#777">${msgCount} message${msgCount !== 1 ? 's' : ''}</font>
</td></tr></tbody></table>
${msgHtml}
</div></div>
</body></html>`;
  return html;
}

// --- artifacts --------------------------------------------------------

let _browser = null;
let _page = null;

async function ensureBrowser() {
  if (!_browser) {
    const puppeteer = require('puppeteer');
    _browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
    _page = await _browser.newPage();
  }
  return _page;
}

async function closeBrowser() {
  if (_browser) await _browser.close();
  _browser = null;
  _page = null;
}

async function htmlToPdf(htmlPath, pdfPath) {
  const page = await ensureBrowser();
  await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle2', timeout: 15000 });
  await page.pdf({ path: pdfPath, ...PDF_OPTIONS });
}

/** Render one stored thread to a PDF. Returns the path written. */
async function renderMboxToPdf(mboxPath, pdfPath, options = {}) {
  const os = require('os');
  // `options.messages` lets a caller that has already parsed the mbox
  // hand the messages over rather than paying for a second parse; the
  // rendering is the same either way.
  const messages = options.messages || loadThread(mboxPath);
  const html = renderThreadHtml(messages, options);
  const tmpDir = options.tmpDir || fs.mkdtempSync(path.join(os.tmpdir(), 'gmail-'));
  const htmlPath = path.join(tmpDir, path.basename(mboxPath) + '.html');
  fs.writeFileSync(htmlPath, html);
  try {
    fs.mkdirSync(path.dirname(pdfPath), { recursive: true });
    await htmlToPdf(htmlPath, pdfPath);
  } finally {
    if (!options.tmpDir) fs.rmSync(tmpDir, { recursive: true, force: true });
  }
  return pdfPath;
}

/** Where a thread's attachments live, given its mbox. */
function attachmentsDirFor(mboxPath) {
  const stem = path.basename(mboxPath).replace(/\.mbox$/i, '');
  const gmailDir = path.dirname(path.dirname(mboxPath));
  return path.join(gmailDir, 'attachments', stem);
}

/**
 * Write the thread's attachment parts into `destDir`.
 *
 * Returns [{name, size, path, created}] — `created` false when the file
 * was already there at the expected size, so a caller announcing NEW
 * lines does not re-announce what it wrote last time. Parts over
 * `maxBytes` are reported through `onSkip` and omitted.
 */
function extractAttachments(messages, destDir, options = {}) {
  const maxBytes = options.maxBytes || MAX_ATTACHMENT_BYTES;
  const found = listAttachments(messages);
  if (!found.length) return [];
  fs.mkdirSync(destDir, { recursive: true });
  const written = [];
  for (const att of found) {
    if (att.size > maxBytes) {
      if (options.onSkip) options.onSkip(att);
      continue;
    }
    const dest = path.join(destDir, att.name);
    if (fs.existsSync(dest) && fs.statSync(dest).size === att.size) {
      written.push({ name: att.name, size: att.size, path: dest, created: false });
      continue;
    }
    fs.writeFileSync(dest, att.part.content);
    written.push({ name: att.name, size: att.size, path: dest, created: true });
  }
  return written;
}

/**
 * One stored message as .eml: the raw bytes, unchanged.
 *
 * An .eml file *is* an RFC 822 message, so emitting one is a copy out
 * of the mbox, never a re-serialization — which is what makes the mbox
 * rebuildable into per-message files on demand rather than only
 * readable by mail clients.
 */
function emitEml(messages, oneBasedIndex, destPath) {
  const message = messages[oneBasedIndex - 1];
  if (!message) throw new Error(`no message ${oneBasedIndex} in this thread`);
  if (!destPath) return message.raw;
  fs.mkdirSync(path.dirname(destPath), { recursive: true });
  fs.writeFileSync(destPath, message.raw);
  return message.raw;
}

// --- CLI --------------------------------------------------------------

function usage() {
  const lines = fs.readFileSync(__filename, 'utf-8').split('\n');
  const help = lines
    .slice(1, lines.findIndex((l) => l.startsWith("'use strict'")))
    .map((l) => l.replace(/^\/\/ ?/, ''));
  process.stderr.write(help.join('\n'));
}

//: Flags that take a value. `--attachments` takes an optional one, so
//: it is listed here too: a following non-flag argument is its
//: directory, never the mbox path.
const VALUE_FLAGS = new Set([
  '--pdf', '--html', '--quoted', '--attachments', '--eml', '--subject', '--account',
]);

function flagValue(argv, name, fallback) {
  const i = argv.indexOf(name);
  if (i === -1) return fallback;
  const next = argv[i + 1];
  return next && !next.startsWith('--') ? next : true;
}

function positionalArgs(argv) {
  const out = [];
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith('--')) {
      out.push(argv[i]);
      continue;
    }
    if (VALUE_FLAGS.has(argv[i]) && argv[i + 1] && !argv[i + 1].startsWith('--')) i++;
  }
  return out;
}

function stringOrUndefined(value) {
  return typeof value === 'string' ? value : undefined;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

async function main(argv) {
  const mboxPath = positionalArgs(argv)[0];
  if (!mboxPath || argv.includes('--help') || argv.includes('-h')) {
    usage();
    process.exit(mboxPath ? 0 : 1);
  }
  if (!fs.existsSync(mboxPath)) fail(`no such mbox: ${mboxPath}`);

  const quoted = flagValue(argv, '--quoted', DEFAULT_QUOTED_MODE);
  if (!QUOTED_MODES.includes(quoted)) fail(`--quoted must be one of ${QUOTED_MODES.join('|')}`);
  const options = {
    quoted,
    subject: stringOrUndefined(flagValue(argv, '--subject', undefined)),
    account: stringOrUndefined(flagValue(argv, '--account', undefined)),
  };
  const messages = loadThread(mboxPath);
  let did = false;

  if (argv.includes('--list')) {
    did = true;
    console.log(`${messages.length} message(s) in ${path.basename(mboxPath)}`);
    console.log(`subject: ${options.subject || threadSubject(messages)}`);
    messages.forEach((m, i) => {
      console.log(
        `  ${i + 1}. ${m.node.header('Date')} — ${m.node.header('From')}`
      );
    });
    for (const att of listAttachments(messages)) {
      console.log(
        `  attachment: ${att.name} (${fmtSize(att.size)}) ` +
          `from message ${att.messageIndex + 1}`
      );
    }
  }

  const html = flagValue(argv, '--html', null);
  if (html === true) fail('--html needs a path');
  if (typeof html === 'string') {
    did = true;
    fs.mkdirSync(path.dirname(path.resolve(html)), { recursive: true });
    fs.writeFileSync(html, renderThreadHtml(messages, options));
    console.error(`wrote ${html}`);
  }

  const pdf = flagValue(argv, '--pdf', null);
  if (pdf === true) fail('--pdf needs a path');
  if (typeof pdf === 'string') {
    did = true;
    await renderMboxToPdf(mboxPath, path.resolve(pdf), options);
    console.error(`wrote ${pdf}`);
    await closeBrowser();
  }

  const attachments = flagValue(argv, '--attachments', null);
  if (attachments) {
    did = true;
    const dir =
      typeof attachments === 'string' ? attachments : attachmentsDirFor(mboxPath);
    const written = extractAttachments(messages, dir, {
      onSkip: (att) =>
        console.error(
          `  SKIPPED ${att.originalName} (${fmtSize(att.size)} exceeds ` +
            `${fmtSize(MAX_ATTACHMENT_BYTES)} cap)`
        ),
    });
    for (const file of written) console.error(`  ${file.created ? 'wrote' : 'have'} ${file.path}`);
    if (!written.length) console.error('  (no attachments)');
  }

  const eml = flagValue(argv, '--eml', null);
  if (eml === true) fail('--eml needs a message number, e.g. --eml 2:out.eml');
  if (typeof eml === 'string') {
    did = true;
    const [n, dest] = eml.split(':');
    const raw = emitEml(messages, Number(n), dest);
    if (!dest) process.stdout.write(raw);
    else console.error(`wrote ${dest}`);
  }

  if (!did) {
    usage();
    process.exit(1);
  }
}

module.exports = {
  GMAIL_LOGO_URL,
  MAX_ATTACHMENT_BYTES,
  QUOTED_MODES,
  DEFAULT_QUOTED_MODE,
  esc,
  fmtDate,
  fmtSize,
  parseSender,
  safeAttachmentName,
  stripQuotedHtml,
  stripQuotedText,
  embedInlineImages,
  loadThread,
  threadSubject,
  listAttachments,
  renderThreadHtml,
  renderMboxToPdf,
  attachmentsDirFor,
  extractAttachments,
  emitEml,
  closeBrowser,
};

if (require.main === module) {
  main(process.argv.slice(2)).catch((err) => {
    console.error('Fatal:', err.message);
    process.exit(1);
  });
}
