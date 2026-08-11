#!/usr/bin/env node
//
// gmail connector — export Gmail threads to PDF matching Gmail's print view.
//
// Usage:  node pull.js <matter_dir> [--dry-run] [--force]
//
// Config (matter.yaml, connectors.gmail; legacy envelopes.yaml
// gmail_addresses: also read):
//   gmail:
//     addresses:            # plain address, bare domain, or {address, after, before}
//       - opposing@example.com
//       - examplefirm.com
//       - address: expartner@example.com
//         after: 2024/04/01
//
// Credentials: OAuth client keys + token live in
// $PROSAIC_GMAIL_CREDS_DIR (default ~/.config/prosaic/gmail/) as
// oauth-keys.json + credentials.json. Run `node auth.js` once to
// authorize (browser consent).
//
// Output: <matter>/assets/gmail/YYYYMMDD_<subject>.pdf per thread;
// "NEW <abs path>" lines on stdout; progress on stderr.
//
// Incrementality / dedup: a durable ledger in .state/gmail.json records
// every thread this connector has exported, keyed by Gmail thread id:
//
//   { "threads": { "<threadId>": {
//        historyId, messageCount, filename, exportedAt } } }
//
// Each run lists matching threads (cheap; the list stub carries a
// per-thread historyId that changes whenever the thread changes) and:
//   - skips a thread outright when its historyId matches the ledger
//     (no metadata fetch, no render, no NEW) — so a broad domain filter
//     doesn't re-examine the whole history every 12h;
//   - re-exports a thread only when it has GROWN (a new message), so an
//     updated thread is re-triaged, while a mere label/read-state change
//     just refreshes the stored historyId;
//   - on first run against a matter that already has assets/gmail/ PDFs
//     from before this ledger existed, absorbs those into the ledger
//     without re-exporting (no mass re-triage).
// Because a thread is remembered by id, downstream triage may move or
// rename the exported PDF out of assets/gmail/ and it will NOT be
// re-pulled. Pulls are idempotent (connector contract, docs/connectors.md).

// Suppress the punycode deprecation warning (DEP0040) emitted from deep
// inside googleapis' dependency chain (tr46/whatwg-url). Not fixable
// locally; it only pollutes terminal output and launchd logs. All other
// warnings still surface.
const _emitWarning = process.emitWarning;
process.emitWarning = function (warning, ...args) {
  const code = args[0] && typeof args[0] === 'object' ? args[0].code : args[1];
  if (code === 'DEP0040') return;
  return _emitWarning.call(process, warning, ...args);
};

const fs = require('fs');
const path = require('path');
const { connectorConfig, loadState, saveState } = require('../core/config');
const { google } = require('googleapis');
const puppeteer = require('puppeteer');

const cheerio = require('cheerio');

const CREDS_DIR =
  process.env.PROSAIC_GMAIL_CREDS_DIR ||
  path.join(require('os').homedir(), '.config/prosaic/gmail');
const CREDENTIALS_PATH = path.join(CREDS_DIR, 'credentials.json');
const OAUTH_KEYS_PATH = path.join(CREDS_DIR, 'oauth-keys.json');
const GMAIL_LOGO_URL =
  'https://ssl.gstatic.com/ui/v1/icons/mail/rfr/logo_gmail_server_1x.png';

function snakeCase(str) {
  return str
    .replace(/^(?:re):\s*/gi, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .substring(0, 80);
}

function esc(s) {
  if (!s) return '';
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function loadAuth() {
  const oauthKeys = JSON.parse(fs.readFileSync(OAUTH_KEYS_PATH, 'utf-8'));
  const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf-8'));
  const key = oauthKeys.web || oauthKeys.installed;
  const auth = new google.auth.OAuth2(
    key.client_id,
    key.client_secret,
    key.redirect_uris[0]
  );
  auth.setCredentials(creds);
  auth.on('tokens', (tokens) => {
    const merged = { ...creds, ...tokens };
    fs.writeFileSync(CREDENTIALS_PATH, JSON.stringify(merged));
  });
  google.options({ auth });
}

function getHeader(headers, name) {
  return headers.find((h) => h.name.toLowerCase() === name.toLowerCase())
    ?.value;
}

// A gmail_addresses entry is either a plain string (address or bare
// domain) or an object with per-address constraints:
//   - address: expartner@example.com
//     after: 2024/04/01        # optional; Gmail after: syntax
//     before: 2026/01/01       # optional; Gmail before: syntax
function addressClause(entry) {
  const a = typeof entry === 'string' ? entry : entry.address;
  let clause = `(from:${a} OR to:${a})`;
  if (typeof entry === 'object') {
    const bounds = [];
    if (entry.after) bounds.push(`after:${entry.after}`);
    if (entry.before) bounds.push(`before:${entry.before}`);
    if (bounds.length) clause = `(${clause} ${bounds.join(' ')})`;
  }
  return clause;
}

function addressDisplay(entry) {
  if (typeof entry === 'string') return entry;
  const bounds = [entry.after && `after:${entry.after}`, entry.before && `before:${entry.before}`]
    .filter(Boolean)
    .join(' ');
  return bounds ? `${entry.address} (${bounds})` : entry.address;
}

async function searchThreads(gmail, addresses) {
  const query = addresses.map(addressClause).join(' OR ');
  const threads = [];
  let pageToken;
  do {
    const res = await gmail.users.threads.list({
      userId: 'me',
      q: query,
      maxResults: 100,
      pageToken,
    });
    if (res.data.threads) threads.push(...res.data.threads);
    pageToken = res.data.nextPageToken;
  } while (pageToken);
  return threads;
}

function fmtDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d)) return esc(dateStr);
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

function decodeBody(part) {
  if (!part) return { text: '', html: '' };
  if (part.body?.data) {
    const decoded = Buffer.from(part.body.data, 'base64url').toString('utf-8');
    if (part.mimeType === 'text/html') return { text: '', html: decoded };
    return { text: decoded, html: '' };
  }
  if (part.parts) {
    let text = '',
      html = '';
    const textPart = part.parts.find((p) => p.mimeType === 'text/plain');
    const htmlPart = part.parts.find((p) => p.mimeType === 'text/html');
    if (textPart?.body?.data)
      text = Buffer.from(textPart.body.data, 'base64url').toString('utf-8');
    if (htmlPart?.body?.data)
      html = Buffer.from(htmlPart.body.data, 'base64url').toString('utf-8');
    if (text || html) return { text, html };
    for (const sub of part.parts) {
      const r = decodeBody(sub);
      if (r.text || r.html) return r;
    }
  }
  return { text: '', html: '' };
}

function collectInlineImages(part) {
  const images = {};
  if (!part) return images;
  if (part.mimeType?.startsWith('image/') && part.headers) {
    const cid = part.headers.find(
      (h) => h.name.toLowerCase() === 'content-id'
    );
    if (cid) {
      const id = cid.value.replace(/^<|>$/g, '');
      images[id] = {
        mimeType: part.mimeType,
        attachmentId: part.body?.attachmentId,
        data: part.body?.data,
      };
    }
  }
  if (part.parts)
    for (const sub of part.parts) Object.assign(images, collectInlineImages(sub));
  return images;
}

async function resolveInlineImages(gmail, messageId, html, payload) {
  const images = collectInlineImages(payload);
  const cidRefs = [...html.matchAll(/src=["']cid:([^"']+)["']/gi)];
  if (cidRefs.length === 0) return html;

  for (const match of cidRefs) {
    const cid = match[1];
    const img = images[cid];
    if (!img) continue;

    let b64;
    if (img.data) {
      b64 = img.data.replace(/-/g, '+').replace(/_/g, '/');
    } else if (img.attachmentId) {
      const att = await gmail.users.messages.attachments.get({
        userId: 'me',
        messageId,
        id: img.attachmentId,
      });
      b64 = att.data.data.replace(/-/g, '+').replace(/_/g, '/');
    } else {
      continue;
    }
    html = html.replace(
      new RegExp(`src=["']cid:${cid.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["']`, 'gi'),
      `src="data:${img.mimeType};base64,${b64}"`
    );
  }
  return html;
}

function getAttachments(part) {
  const atts = [];
  if (!part) return atts;
  const isInline =
    part.headers?.some(
      (h) => h.name.toLowerCase() === 'content-disposition' && h.value.startsWith('inline')
    ) ||
    part.headers?.some((h) => h.name.toLowerCase() === 'content-id');
  if (part.filename && part.body?.size > 0 && !isInline)
    atts.push({ name: part.filename, size: part.body.size });
  if (part.parts)
    for (const sub of part.parts) atts.push(...getAttachments(sub));
  return atts;
}

function parseSender(from) {
  const m = from.match(/^(.+?)\s*<(.+?)>$/);
  if (m) return { name: m[1].replace(/"/g, ''), email: m[2] };
  return { name: from, email: from };
}

const QUOTED_HIDDEN_HTML = '<div><font size="1" color="#888888">[Quoted text hidden]</font></div>';

function stripQuotedHtml(html) {
  const $ = cheerio.load(html, { xmlMode: false, decodeEntities: false });

  // Gmail web replies
  $('div.gmail_quote').replaceWith(QUOTED_HIDDEN_HTML);
  $('div.gmail_attr').remove();
  $('div.gmail_extra').replaceWith(QUOTED_HIDDEN_HTML);

  // Actual reply-style blockquotes. Do not hide all blockquotes globally:
  // some messages use blockquote purely for indentation/formatting rather than
  // quoted reply content. Reply HTML commonly marks quoted sections with
  // type="cite" (Apple Mail, Thunderbird, etc.).
  $('blockquote[type="cite"]').replaceWith(QUOTED_HIDDEN_HTML);

  // Gmail forwarded messages: "---------- Forwarded message ---------"
  $('*').each(function () {
    const t = $(this).text().trim();
    if (/^-{5,}\s*Forwarded message\s*-{5,}$/.test(t)) {
      $(this).nextAll().remove();
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // Outlook-style replies: <hr> or horizontal rule followed by From/Sent/To block
  $('hr').each(function () {
    const next = $(this).next();
    const nextText = next.text().trim();
    if (/^From:/.test(nextText) || next.find('b').first().text().trim() === 'From:') {
      $(this).nextAll().remove();
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // Outlook divRplyFwdMsg pattern
  $('[id*="divRplyFwdMsg"], [id*="appendonsend"]').each(function () {
    $(this).nextAll().remove();
    $(this).replaceWith(QUOTED_HIDDEN_HTML);
  });

  // "On [date] ... wrote:" followed by quoted content
  $('div, span, p').each(function () {
    const t = $(this).text().trim();
    if (/^On\s.+wrote:$/.test(t)) {
      $(this).nextAll().remove();
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // Apple Mail inline reply: "On [date], at [time], [name] wrote:"
  $('div, span, p').each(function () {
    const t = $(this).text().trim();
    if (/^On\s.+,\s+at\s+.+,\s+.+wrote:$/.test(t)) {
      $(this).nextAll().remove();
      $(this).replaceWith(QUOTED_HIDDEN_HTML);
    }
  });

  // Generic: any element containing only "> " prefixed lines (plain-text quotes in HTML)
  $('div, p, pre').each(function () {
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

function stripQuotedText(text) {
  const lines = text.split('\n');
  const out = [];
  let inQuote = false;
  for (const line of lines) {
    const isQuoteLine =
      line.startsWith('>') ||
      (/^On .+ wrote:/.test(line) && !inQuote);
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

function renderBody(body) {
  if (body.html) {
    let clean = body.html
      .replace(/<html[^>]*>/gi, '')
      .replace(/<\/html>/gi, '')
      .replace(/<head[^>]*>[\s\S]*?<\/head>/gi, '')
      .replace(/<body[^>]*>/gi, '')
      .replace(/<\/body>/gi, '');
    clean = stripQuotedHtml(clean);
    return clean;
  }
  const stripped = stripQuotedText(body.text);
  return `<div dir="ltr">${esc(stripped).replace(/\n/g, '<br>')}</div>`;
}

async function renderThread(gmail, subject, messages, userEmail) {
  const msgCount = messages.length;
  const sender = parseSender(userEmail);

  let msgHtml = '';
  for (const msg of messages) {
    const h = msg.payload.headers;
    const from = getHeader(h, 'From') || '';
    const to = getHeader(h, 'To') || '';
    const cc = getHeader(h, 'Cc');
    const dateStr = getHeader(h, 'Date');
    const { name: senderName, email: senderEmail } = parseSender(from);

    const body = decodeBody(msg.payload);
    if (body.html) {
      body.html = await resolveInlineImages(gmail, msg.id, body.html, msg.payload);
    }
    const atts = getAttachments(msg.payload);

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
    <div style="overflow: hidden;"><font size="-1">${renderBody(body)}</font></div>
  </td></tr></tbody>
  </table>
</td></tr>
${
  atts.length
    ? `<tr><td colspan="2" style="padding: 4px 12px;">
    <table cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid #ddd;padding-top:8px;margin-top:6px;width:100%">
    <tr><td><font size="-1"><b>${atts.length} attachment${atts.length > 1 ? 's' : ''}</b></font></td></tr>
    ${atts.map((a) => {
      const ext = (a.name.match(/\.(\w+)$/) || ['', ''])[1].toLowerCase();
      const iconUrl = {
        pdf: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_pdf_list.png',
        doc: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_word_list.png',
        docx: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_word_list.png',
        xls: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_excel_list.png',
        xlsx: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_excel_list.png',
        ppt: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_powerpoint_list.png',
        pptx: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_powerpoint_list.png',
        png: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_image_list.png',
        jpg: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_image_list.png',
        jpeg: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_image_list.png',
        gif: 'https://ssl.gstatic.com/docs/doclist/images/icon_10_image_list.png',
      }[ext] || 'https://ssl.gstatic.com/docs/doclist/images/icon_10_generic_list.png';
      return `<tr><td style="padding:4px 0;">
        <table cellpadding="0" cellspacing="0" border="0"><tr>
          <td valign="top" style="padding-right:6px;"><img src="${iconUrl}" width="16" height="16"></td>
          <td><font size="-1"><b>${esc(a.name)}</b><br><span style="color:#666">${fmtSize(a.size)}</span></font></td>
        </tr></table>
      </td></tr>`;
    }).join('\n')}
    </table>
  </td></tr>`
    : ''
}
</tbody></table>`;
  }

  return `<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "https://www.w3.org/TR/html4/strict.dtd">
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
  <td align="right"><font size="-1" color="#777"><b>${esc(sender.name)} &lt;${esc(sender.email)}&gt;</b></font></td>
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
}

let _browser = null;
let _page = null;

async function ensureBrowser() {
  if (!_browser) {
    _browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox'],
    });
    _page = await _browser.newPage();
  }
  return _page;
}

async function closeBrowser() {
  if (_browser) await _browser.close();
}

async function htmlToPdf(htmlPath, pdfPath) {
  const page = await ensureBrowser();
  await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle2', timeout: 15000 });
  await page.pdf({
    path: pdfPath,
    format: 'Letter',
    printBackground: true,
    displayHeaderFooter: false,
    margin: { top: '0.3in', bottom: '0.3in', left: '0.4in', right: '0.4in' },
  });
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');
  const force = process.argv.includes('--force');

  const matterDir = process.argv.find((a, i) => i >= 2 && !a.startsWith('--')) || process.cwd();
  const cfg = connectorConfig(matterDir, 'gmail');
  const addresses = cfg && cfg.addresses;
  if (!addresses || !addresses.length) {
    console.error('gmail connector not configured (needs addresses); nothing to do');
    return;
  }

  const outDir = path.resolve(matterDir, cfg.out_dir || 'assets/gmail');
  fs.mkdirSync(outDir, { recursive: true });

  loadAuth();
  const gmail = google.gmail({ version: 'v1' });

  const profile = await gmail.users.getProfile({ userId: 'me' });
  const userEmail = profile.data.emailAddress;

  let userDisplayEmail = userEmail;

  // Durable ledger of exported threads (see the header comment).
  const state = loadState(matterDir, 'gmail', { threads: {} });
  if (!state.threads) state.threads = {};

  // Filenames already taken — on disk and claimed by the ledger — so a
  // new thread never overwrites another thread's export.
  const existingFiles = new Set(fs.readdirSync(outDir));
  const claimedNames = new Set(existingFiles);
  for (const id of Object.keys(state.threads)) {
    const f = state.threads[id] && state.threads[id].filename;
    if (f) claimedNames.add(f);
  }
  function uniqueName(base) {
    let name = base;
    if (claimedNames.has(name)) {
      const stem = base.replace(/\.pdf$/, '');
      let i = 2;
      while (claimedNames.has(`${stem}_${i}.pdf`)) i++;
      name = `${stem}_${i}.pdf`;
    }
    claimedNames.add(name);
    return name;
  }

  console.error(`Querying threads for: ${addresses.map(addressDisplay).join(', ')}`);
  const threadList = await searchThreads(gmail, addresses);
  const seen = new Set();
  const uniqueThreads = threadList.filter((t) => {
    if (seen.has(t.id)) return false;
    seen.add(t.id);
    return true;
  });
  console.error(`Found ${uniqueThreads.length} threads.`);
  if (uniqueThreads.length === 0) return;

  // Decide which threads need a (re)export. Unchanged threads (historyId
  // matches the ledger) are skipped without a metadata fetch.
  const toExport = [];
  let skippedUnchanged = 0;
  let seeded = 0;
  for (const t of uniqueThreads) {
    const prev = state.threads[t.id];
    if (
      !force &&
      prev &&
      prev.historyId != null &&
      t.historyId != null &&
      String(prev.historyId) === String(t.historyId)
    ) {
      skippedUnchanged++;
      continue;
    }

    // Fetch metadata to learn the subject/date and current message count.
    let meta;
    try {
      const res = await gmail.users.threads.get({
        userId: 'me',
        id: t.id,
        format: 'metadata',
        metadataHeaders: ['Subject', 'Date'],
      });
      const msgs = res.data.messages || [];
      const firstMsg = msgs[0];
      const subject =
        getHeader(firstMsg.payload.headers, 'Subject') || 'no_subject';
      const dateStr = getHeader(firstMsg.payload.headers, 'Date');
      const date = dateStr ? new Date(dateStr) : new Date();
      const yyyymmdd = date.toISOString().slice(0, 10).replace(/-/g, '');
      meta = {
        threadId: t.id,
        historyId: t.historyId,
        subject,
        messageCount: msgs.length,
        defaultFilename: `${yyyymmdd}_${snakeCase(subject)}.pdf`,
      };
    } catch (err) {
      console.error(`  warning: skipping thread ${t.id}: ${err.message}`);
      continue;
    }

    if (prev) {
      // Known thread whose historyId moved. Re-export only if it grew;
      // otherwise a label/read-state change — just refresh the ledger.
      if (force || meta.messageCount > (prev.messageCount || 0)) {
        meta.filename = prev.filename || uniqueName(meta.defaultFilename);
        toExport.push(meta);
      } else {
        state.threads[t.id] = {
          ...prev,
          historyId: meta.historyId,
          messageCount: meta.messageCount,
        };
        if (!dryRun) saveState(matterDir, 'gmail', state);
      }
      continue;
    }

    // New to the ledger. If a matching export already sits on disk from a
    // pre-ledger pull, absorb it without re-triaging.
    if (!force && existingFiles.has(meta.defaultFilename)) {
      state.threads[t.id] = {
        historyId: meta.historyId,
        messageCount: meta.messageCount,
        filename: meta.defaultFilename,
        exportedAt: null,
        migrated: true,
      };
      if (!dryRun) saveState(matterDir, 'gmail', state);
      seeded++;
      continue;
    }

    // Genuinely new thread.
    meta.filename = uniqueName(meta.defaultFilename);
    toExport.push(meta);
  }

  console.error(
    `${toExport.length} to export, ${skippedUnchanged} unchanged (skipped), ` +
      `${seeded} pre-existing absorbed.`
  );

  if (dryRun || toExport.length === 0) {
    if (dryRun) {
      console.error('\n-- dry run --');
      for (const m of toExport)
        console.error(`  ${m.filename}  (${m.messageCount} msg)`);
      if (toExport.length === 0) console.error('  (nothing new)');
    }
    return;
  }

  const tmpDir = fs.mkdtempSync(path.join(require('os').tmpdir(), 'gmail-'));
  let exported = 0;

  try {
    for (const meta of toExport) {
      process.stderr.write(`  ${meta.filename} ... `);
      try {
        const res = await gmail.users.threads.get({
          userId: 'me',
          id: meta.threadId,
          format: 'full',
        });
        if (userDisplayEmail === userEmail) {
          for (const m of res.data.messages) {
            const from = getHeader(m.payload.headers, 'From') || '';
            if (from.includes(userEmail) && from.includes('<')) {
              userDisplayEmail = from;
              break;
            }
          }
        }
        const html = await renderThread(gmail, meta.subject, res.data.messages, userDisplayEmail);
        const htmlPath = path.join(tmpDir, `${meta.threadId}.html`);
        const pdfPath = path.join(outDir, meta.filename);
        fs.writeFileSync(htmlPath, html);
        await htmlToPdf(htmlPath, pdfPath);
        exported++;
        console.error('ok');
        console.log(`NEW ${pdfPath}`);
        // Record incrementally so a crash mid-batch never re-exports
        // what already succeeded (connector contract).
        state.threads[meta.threadId] = {
          historyId: meta.historyId,
          messageCount: meta.messageCount,
          filename: meta.filename,
          exportedAt: new Date().toISOString(),
        };
        saveState(matterDir, 'gmail', state);
      } catch (err) {
        console.error(`FAIL (${err.message})`);
      }
    }
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    await closeBrowser();
  }

  console.error(
    `\nDone. ${exported}/${toExport.length} exported to ${outDir}`
  );
}

main().catch((err) => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
