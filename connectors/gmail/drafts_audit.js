// drafts_audit.js — find drafts in the mail record, and move them out.
//
// A draft is not mail (ADR-0049). The connector now never captures
// one, but captures made before that rule rendered drafts exactly like
// sent mail: a PDF of "1 message", From the mailbox owner, To the other
// side, with nothing on its face to say it never left Drafts. This
// module finds them.
//
//   node pull.js <matter> --audit-drafts            report only
//   node pull.js <matter> --audit-drafts --apply    move them out
//   sc mail-audit-drafts [matter] [--apply]         the same, plus a
//                                                   mail-index rebuild
//
// What it compares. Every draft the mailbox holds now (drafts.list and
// the DRAFT label, metadata only: Subject, Date, Message-ID and Gmail's
// snippet) and every captured thread's current state in Gmail
// (threads.get, metadata: each message's Message-ID and labels) against
// what the matter holds:
//
//   1. a ledger entry's mbox: each stored message's Message-ID is
//      looked up. A draft's Message-ID is a draft in the record. A
//      message the Gmail thread no longer has at all is reported as
//      UNVERIFIED (a deleted message, or an earlier saved version of a
//      draft) and is never acted on;
//   2. a ledger entry with a PDF and no mbox: the thread's drafts are
//      matched by the opening words of Gmail's snippet against the
//      rendered text (the .txt beside the PDF, or its derived/text
//      sidecar), and a thread that holds nothing but drafts is a
//      draft-only render;
//   3. an mbox no ledger entry names: Message-IDs, as in 1;
//   4. a PDF no ledger entry names: a draft's own date and subject give
//      the filename the connector would have written for it, and the
//      opening words of its snippet must appear in the rendered text.
//
// What it reports. One line per captured render: DRAFT-ONLY (every
// message in it is a draft), MIXED (a real thread that also carries a
// draft) or UNVERIFIED, with every file that belongs to the render
// (PDF, .txt, mbox, attachments directory, derived/ text, OCR and
// thread-body files), the Markdown files that mention it, and the
// evidence. The report names files and Gmail ids, never a draft's
// subject or words: a draft is private by default.
//
// --apply. Draft-only renders and everything beside them move to
// <matter>/.private/gmail_drafts/<stem>/, path structure kept, with a
// manifest (evidence, sha256 of every file moved, the ledger entry), and
// the ledger entry is dropped. A mixed thread's files move the same
// way, and the thread is rebuilt without its drafts: from its own mbox
// when there is one (every non-draft message byte-identical; the
// original mbox, draft and all, is what moved), otherwise captured
// afresh from Gmail, which never fetches a draft. The new PDF and
// attachments get NEW lines so triage sees them. UNVERIFIED renders are
// never touched. Nothing is ever deleted, and .private/ is added to the
// matter's .gitignore before anything moves into it.

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const mboxlib = require('./mbox');

//: Where drafts moved out of the record go. Never committed, never
//: searched by the record's tools: everything under a dot directory is
//: outside sc find, the text audit and the mail index.
const PRIVATE_DRAFTS_DIR = path.join('.private', 'gmail_drafts');
const GITIGNORE_LINE = '.private/';
const GITIGNORE_COMMENT =
  '# Private material kept out of the record (drafts moved by sc mail-audit-drafts, ...)';

//: Message-IDs of known drafts, for the mail index's guard. Written by
//: --apply only; a report run writes nothing anywhere.
const DRAFT_STATE = 'gmail_drafts';

//: How much of a draft's snippet must appear in a rendered text to
//: count as a match, and the least that counts at all: a snippet of a
//: few words matches too much of any mailbox to be evidence.
const SNIPPET_KEY_CHARS = 60;
const SNIPPET_MIN_CHARS = 16;

//: Matter directories searched for a render's files. Moves happen only
//: under the connector's out_dir and derived/; a copy anywhere else
//: under assets/ is reported, never moved.
const SEARCH_ROOTS = ['assets', 'derived'];
const MOVABLE_ROOTS = ['derived'];
const SKIP_DIRS = new Set(['.git', '.private', '.state', 'node_modules', 'out', '.venv']);

const DAY_MS = 86400000;
const METADATA_CONCURRENCY = 8;

// --- text matching -----------------------------------------------------

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', '#39': "'" };

function decodeEntities(text) {
  return String(text || '')
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&([a-z]+|#39);/gi, (m, name) => ENTITIES[name.toLowerCase()] ?? m);
}

/** Lowercase letters and digits, single-spaced: what survives a print view. */
function normalizeText(text) {
  return decodeEntities(text)
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

/** The opening words of a snippet, or null when too short to be evidence. */
function snippetKey(snippet) {
  const n = normalizeText(snippet);
  if (n.length < SNIPPET_MIN_CHARS) return null;
  if (n.length <= SNIPPET_KEY_CHARS) return n;
  const cut = n.slice(0, SNIPPET_KEY_CHARS);
  const space = cut.lastIndexOf(' ');
  return space >= SNIPPET_MIN_CHARS ? cut.slice(0, space) : cut;
}

function textHasSnippet(text, key) {
  return !!key && !!text && normalizeText(text).includes(key);
}

/** "3 messages" / "1 message" in a print view's text, or null. */
function printedMessageCount(text) {
  const m = /^\s*(\d+)\s+messages?\s*$/im.exec(String(text || ''));
  return m ? Number(m[1]) : null;
}

// --- filenames ---------------------------------------------------------

/** The connector's subject slug (pull.js snakeCase), repeated here to stay pure. */
function snakeCase(str) {
  return String(str || '')
    .replace(/^(?:re):\s*/gi, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .substring(0, 80);
}

function yyyymmdd(date) {
  return date.toISOString().slice(0, 10).replace(/-/g, '');
}

/**
 * The stems the connector could have given a render whose first message
 * is this draft: its UTC date (what pull.js uses) and the day either
 * side (an earlier version named files by local date), its subject's
 * slug, and any collision suffix.
 */
function candidateStemPattern(draft) {
  const parsed = draft.date ? new Date(draft.date) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) return null;
  const days = [-1, 0, 1].map((d) => yyyymmdd(new Date(parsed.getTime() + d * DAY_MS)));
  const slug = snakeCase(draft.subject || 'no_subject') || 'no_subject';
  const esc = slug.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^(?:${days.join('|')})_${esc}(?:_\\d+)?$`);
}

// --- one stored thread -------------------------------------------------

/**
 * Classify a stored thread's messages, by Message-ID.
 *
 * `draftKeys`: Message-IDs of drafts. `liveRealKeys`: Message-IDs of the
 * thread's non-draft messages in Gmail now, or null when that is
 * unknown (an mbox no ledger entry names). Returns the indexes of
 * drafts and of unverified messages, and the render's kind.
 */
function classifyStoredThread(keys, { draftKeys, liveRealKeys = null }) {
  const drafts = [];
  const unverified = [];
  keys.forEach((key, i) => {
    if (draftKeys.has(key)) drafts.push(i);
    else if (liveRealKeys && !liveRealKeys.has(key)) unverified.push(i);
  });
  let kind = null;
  if (drafts.length) kind = drafts.length === keys.length ? 'draft-only' : 'mixed';
  else if (unverified.length) kind = 'unverified';
  return { kind, drafts, unverified, total: keys.length };
}

// --- the matter's files ------------------------------------------------

function walk(root, rel, out) {
  let entries;
  try {
    entries = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    if (SKIP_DIRS.has(e.name)) continue;
    const r = rel ? path.join(rel, e.name) : e.name;
    out.push({ rel: r, dir: e.isDirectory() });
    if (e.isDirectory()) walk(root, r, out);
  }
}

/** Every path under the search roots, relative to the matter. */
function indexMatter(matterDir) {
  const out = [];
  for (const root of SEARCH_ROOTS) {
    if (fs.existsSync(path.join(matterDir, root))) {
      out.push({ rel: root, dir: true });
      walk(matterDir, root, out);
    }
  }
  return out;
}

function belongsToStem(basename, stem) {
  return basename === stem || basename.startsWith(`${stem}.`) || basename.startsWith(`${stem}_ocr.`);
}

/**
 * The files and directories that are one render: every path whose
 * basename is the stem (a directory such as attachments/<stem>/) or
 * the stem plus an extension (<stem>.pdf, <stem>.txt, <stem>.pdf.txt,
 * <stem>.mbox, <stem>_ocr.pdf). Movable ones sit under the connector's
 * out_dir or derived/; any other match is a copy, reported only.
 */
function filesForStem(index, stem, outRel) {
  const movable = [];
  const copies = [];
  const roots = [outRel, ...MOVABLE_ROOTS].map((r) => r.split(path.sep).join('/'));
  for (const item of index) {
    if (!belongsToStem(path.basename(item.rel), stem)) continue;
    const rel = item.rel.split(path.sep).join('/');
    if (movable.some((m) => rel.startsWith(`${m}/`))) continue; // inside a matched dir
    const under = roots.some((r) => rel === r || rel.startsWith(`${r}/`));
    (under ? movable : copies).push(rel);
  }
  return { movable: movable.sort(), copies: copies.sort() };
}

/** Markdown files that mention a stem, as "path:line". */
function referencesTo(matterDir, mdFiles, stem) {
  const out = [];
  for (const rel of mdFiles) {
    let text;
    try {
      text = fs.readFileSync(path.join(matterDir, rel), 'utf-8');
    } catch {
      continue;
    }
    if (!text.includes(stem)) continue;
    text.split('\n').forEach((line, i) => {
      if (line.includes(stem)) out.push(`${rel}:${i + 1}`);
    });
  }
  return out;
}

function markdownFiles(matterDir) {
  const out = [];
  const visit = (rel) => {
    let entries;
    try {
      entries = fs.readdirSync(path.join(matterDir, rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (SKIP_DIRS.has(e.name) || (rel === '' && e.name === 'derived')) continue;
      const r = rel ? path.join(rel, e.name) : e.name;
      if (e.isDirectory()) visit(r);
      else if (e.name.toLowerCase().endsWith('.md')) out.push(r);
    }
  };
  visit('');
  return out;
}

/** The rendered text of a PDF: the .txt beside it, else its derived/text sidecar. */
function renderedText(matterDir, outDir, stem) {
  const outRel = path.relative(matterDir, outDir);
  const candidates = [
    path.join(outDir, `${stem}.txt`),
    path.join(matterDir, 'derived', 'text', outRel, `${stem}.pdf.txt`),
  ];
  for (const c of candidates) {
    try {
      return fs.readFileSync(c, 'utf-8');
    } catch {
      /* next */
    }
  }
  return null;
}

// --- the audit ---------------------------------------------------------

/**
 * Compare the mailbox's drafts and threads against the record. Pure over
 * the data handed in plus a read of the matter's files.
 *
 *   drafts:  [{gmailId, threadId, key, subject, date, snippet}]
 *   live:    Map threadId -> {exists, realKeys:Set, realIds:Set,
 *                             draftKeys:Set, draftIds:Set}
 *   ledgerThreads: {threadId: entry}   (this account's ledger)
 *
 * Returns {findings, drafts, inRecord:Set gmailId, unmatched:[draft]}.
 */
function auditRecord({ matterDir, outDir, ledgerThreads, drafts, live }) {
  const draftKeys = new Set(drafts.map((d) => d.key).filter(Boolean));
  for (const lv of live.values()) for (const k of (lv && lv.draftKeys) || []) draftKeys.add(k);
  const draftByKey = new Map(drafts.filter((d) => d.key).map((d) => [d.key, d]));
  const byThread = new Map();
  for (const d of drafts) {
    if (!byThread.has(d.threadId)) byThread.set(d.threadId, []);
    byThread.get(d.threadId).push(d);
  }

  const findings = [];
  const inRecord = new Set();
  const seenMbox = new Set();
  const seenStems = new Set();

  const fromMbox = (mboxPath, stem, threadId, entry, lv) => {
    const keys = mboxlib.readMessages(mboxPath).map(mboxlib.messageKey);
    const c = classifyStoredThread(keys, {
      draftKeys,
      liveRealKeys: lv && lv.exists ? lv.realKeys : null,
    });
    if (!c.kind) return;
    const evidence = [];
    for (const i of c.drafts) {
      const d = draftByKey.get(keys[i]);
      if (d) inRecord.add(d.gmailId);
      evidence.push(
        `mbox message ${i + 1} of ${c.total} has the Message-ID of a Gmail draft` +
          (d ? ` (draft message ${d.gmailId})` : '')
      );
    }
    for (const i of c.unverified) {
      evidence.push(
        `mbox message ${i + 1} of ${c.total} is not in the Gmail thread now ` +
          '(deleted, or an earlier saved version of a draft): needs human review'
      );
    }
    findings.push({
      stem,
      threadId,
      kind: c.kind,
      source: 'mbox',
      mbox: path.relative(outDir, mboxPath),
      draftIndexes: c.drafts,
      unverifiedIndexes: c.unverified,
      total: c.total,
      draftGmailIds: c.drafts.map((i) => draftByKey.get(keys[i])).filter(Boolean).map((d) => d.gmailId),
      evidence,
    });
  };

  for (const [threadId, entry] of Object.entries(ledgerThreads || {})) {
    if (!entry || !entry.filename) continue;
    const stem = entry.filename.replace(/\.pdf$/i, '');
    seenStems.add(stem);
    const lv = live.get(threadId);
    const mboxPath = entry.mbox
      ? path.join(outDir, entry.mbox)
      : mboxlib.mboxPathFor(outDir, entry.filename);
    if (fs.existsSync(mboxPath) && fs.statSync(mboxPath).size > 0) {
      seenMbox.add(path.resolve(mboxPath));
      fromMbox(mboxPath, stem, threadId, entry, lv);
      continue;
    }
    // A render with no mbox: only its text can say what it holds.
    const threadDrafts = byThread.get(threadId) || [];
    if (!threadDrafts.length) continue;
    const text = renderedText(matterDir, outDir, stem);
    const hits = threadDrafts.filter((d) => textHasSnippet(text, snippetKey(d.snippet)));
    const onlyDrafts = !!(lv && lv.exists && lv.realIds.size === 0);
    if (!hits.length && !onlyDrafts) continue;
    const printed = printedMessageCount(text);
    const evidence = [];
    if (onlyDrafts) evidence.push(`Gmail thread ${threadId} holds nothing but drafts (${threadDrafts.length})`);
    for (const d of hits) evidence.push(`rendered text contains the opening words of Gmail draft message ${d.gmailId}`);
    const ledgerHasDraftId = threadDrafts.filter((d) => (entry.messageIds || []).includes(d.gmailId));
    for (const d of ledgerHasDraftId) evidence.push(`ledger records draft message ${d.gmailId} as exported`);
    const unmatchable = threadDrafts.filter((d) => !snippetKey(d.snippet)).length;
    if (!hits.length && unmatchable) {
      evidence.push(`${unmatchable} draft(s) too short to match against the text`);
    }
    evidence.push(
      printed === null ? 'message count not printed in the text' : `print view says ${printed} message(s)`
    );
    // A render with no mbox is rebuilt by recapturing the thread, which
    // brings back only what Gmail still holds. If it prints more messages
    // than Gmail now has, real mail was deleted since and the PDF is its
    // only record: a person decides, nothing is moved.
    let kind = onlyDrafts ? 'draft-only' : 'mixed';
    const holds = (lv && lv.exists ? lv.realIds.size : 0) + (onlyDrafts ? threadDrafts.length : hits.length);
    if (printed !== null && printed > holds) {
      kind = 'unverified';
      evidence.push(
        `more messages printed than Gmail now holds (${holds}): some were deleted, and this PDF may be their only record`
      );
    }
    for (const d of onlyDrafts ? threadDrafts : hits) inRecord.add(d.gmailId);
    findings.push({
      stem,
      threadId,
      kind,
      source: 'pdf',
      draftGmailIds: (onlyDrafts ? threadDrafts : hits).map((d) => d.gmailId),
      evidence,
    });
  }

  // mboxes no ledger entry names
  const mboxDir = path.join(outDir, mboxlib.MBOX_DIR_NAME);
  if (fs.existsSync(mboxDir)) {
    for (const name of fs.readdirSync(mboxDir).sort()) {
      if (!name.endsWith(mboxlib.MBOX_EXTENSION)) continue;
      const p = path.resolve(mboxDir, name);
      if (seenMbox.has(p)) continue;
      const stem = name.slice(0, -mboxlib.MBOX_EXTENSION.length);
      seenStems.add(stem);
      fromMbox(p, stem, null, null, null);
    }
  }

  // PDFs no ledger entry names, by the filename a draft would have had
  const loosePdfs = (fs.existsSync(outDir) ? fs.readdirSync(outDir) : [])
    .filter((n) => n.toLowerCase().endsWith('.pdf') && !n.endsWith('_ocr.pdf'))
    .map((n) => n.slice(0, -4))
    .filter((stem) => !seenStems.has(stem));
  const looseHits = new Map();
  for (const d of drafts) {
    if (inRecord.has(d.gmailId)) continue;
    const pattern = candidateStemPattern(d);
    const key = snippetKey(d.snippet);
    if (!pattern || !key) continue;
    for (const stem of loosePdfs) {
      if (!pattern.test(stem)) continue;
      if (!textHasSnippet(renderedText(matterDir, outDir, stem), key)) continue;
      if (!looseHits.has(stem)) looseHits.set(stem, []);
      looseHits.get(stem).push(d);
      inRecord.add(d.gmailId);
    }
  }
  for (const [stem, ds] of looseHits) {
    const n = printedMessageCount(renderedText(matterDir, outDir, stem));
    const draftOnly = n !== null && n <= ds.length;
    findings.push({
      stem,
      threadId: null,
      kind: draftOnly ? 'draft-only' : 'mixed',
      source: 'pdf',
      draftGmailIds: ds.map((d) => d.gmailId),
      evidence: [
        ...ds.map(
          (d) =>
            `filename is the date and subject of Gmail draft message ${d.gmailId}, ` +
            'and the rendered text contains its opening words'
        ),
        n === null
          ? 'message count not printed in the text'
          : `print view says ${n} message(s); ${ds.length} matched a draft`,
      ],
    });
  }

  // Every file each render owns, and what mentions it.
  const index = indexMatter(matterDir);
  const md = markdownFiles(matterDir);
  const outRel = path.relative(matterDir, outDir);
  for (const f of findings) {
    const { movable, copies } = filesForStem(index, f.stem, outRel);
    f.files = movable;
    f.copies = copies;
    f.references = referencesTo(matterDir, md, f.stem);
  }

  const order = { 'draft-only': 0, mixed: 1, unverified: 2 };
  findings.sort((a, b) => order[a.kind] - order[b.kind] || a.stem.localeCompare(b.stem));
  return {
    findings,
    drafts,
    inRecord,
    unmatched: drafts.filter((d) => !inRecord.has(d.gmailId)),
  };
}

// --- the report --------------------------------------------------------

function formatReport(result, { matterDir, account, applied = null }) {
  const by = (k) => result.findings.filter((f) => f.kind === k);
  const lines = [];
  lines.push(`Gmail drafts audit: ${matterDir}`);
  lines.push(`account: ${account}`);
  lines.push(`mode: ${applied ? 'APPLIED' : 'report only (nothing was changed)'}`);
  lines.push('');
  lines.push(`drafts in the mailbox now:        ${result.drafts.length}`);
  lines.push(`  found in the record:            ${result.inRecord.size}`);
  lines.push(`  not in the record:              ${result.unmatched.length}`);
  lines.push(`draft-only renders:               ${by('draft-only').length}`);
  lines.push(`mixed renders (real + draft):     ${by('mixed').length}`);
  lines.push(`unverified (not in Gmail now):    ${by('unverified').length}`);
  const sections = [
    ['draft-only', 'DRAFT-ONLY: every message in the render is a draft'],
    ['mixed', 'MIXED: a real thread that also carries a draft'],
    ['unverified', 'UNVERIFIED: stored messages Gmail no longer has (needs human review; never moved)'],
  ];
  for (const [kind, title] of sections) {
    const fs_ = by(kind);
    if (!fs_.length) continue;
    lines.push('', `== ${title} (${fs_.length})`);
    for (const f of fs_) {
      lines.push('', `${f.stem}` + (f.threadId ? `  [thread ${f.threadId}]` : '  [no ledger entry]'));
      for (const e of f.evidence) lines.push(`    evidence: ${e}`);
      for (const p of f.files || []) lines.push(`    file: ${p}`);
      for (const p of f.copies || []) lines.push(`    copy (not moved): ${p}`);
      for (const r of f.references || []) lines.push(`    mentioned in: ${r}`);
      if (applied && applied.get(f.stem)) lines.push(`    applied: ${applied.get(f.stem)}`);
    }
  }
  lines.push('');
  return lines.join('\n');
}

// --- collecting from Gmail ---------------------------------------------

function header(headers, name) {
  const h = (headers || []).find((x) => x.name.toLowerCase() === name.toLowerCase());
  return h ? h.value : undefined;
}

function keyOf(messageId) {
  return messageId ? messageId.trim().toLowerCase() : null;
}

/** Every draft in the mailbox: drafts.list and the DRAFT label, metadata only. */
async function listDrafts(gmail, { apiCall, mapLimit }) {
  const stubs = new Map();
  let pageToken;
  do {
    const res = await apiCall(
      (o) => gmail.users.drafts.list({ userId: 'me', maxResults: 500, pageToken }, o),
      'drafts.list'
    );
    for (const d of res.data.drafts || []) {
      if (d.message && d.message.id) stubs.set(d.message.id, d.message.threadId);
    }
    pageToken = res.data.nextPageToken;
  } while (pageToken);
  pageToken = undefined;
  do {
    const res = await apiCall(
      (o) => gmail.users.messages.list({ userId: 'me', labelIds: ['DRAFT'], maxResults: 500, pageToken }, o),
      'messages.list DRAFT'
    );
    for (const m of res.data.messages || []) stubs.set(m.id, m.threadId);
    pageToken = res.data.nextPageToken;
  } while (pageToken);

  const ids = [...stubs.keys()];
  const metas = await mapLimit(ids, METADATA_CONCURRENCY, async (id) => {
    try {
      const res = await apiCall(
        (o) =>
          gmail.users.messages.get(
            { userId: 'me', id, format: 'metadata', metadataHeaders: ['Subject', 'Date', 'Message-ID'] },
            o
          ),
        `messages.get ${id}`
      );
      const h = (res.data.payload && res.data.payload.headers) || [];
      return {
        gmailId: id,
        threadId: res.data.threadId || stubs.get(id),
        key: keyOf(header(h, 'Message-ID')),
        subject: header(h, 'Subject') || '',
        date: header(h, 'Date') || (res.data.internalDate ? new Date(Number(res.data.internalDate)).toUTCString() : ''),
        snippet: res.data.snippet || '',
      };
    } catch (err) {
      return { gmailId: id, threadId: stubs.get(id), key: null, subject: '', date: '', snippet: '', error: err.message };
    }
  });
  return metas;
}

const GONE_RE = /Requested entity was not found|notFound|404/i;

/** A thread as Gmail holds it now: Message-IDs of its real messages and of its drafts. */
async function liveThread(gmail, threadId, { apiCall }) {
  try {
    const res = await apiCall(
      (o) =>
        gmail.users.threads.get(
          { userId: 'me', id: threadId, format: 'metadata', metadataHeaders: ['Message-ID'] },
          o
        ),
      `threads.get ${threadId}`
    );
    const lv = { exists: true, realKeys: new Set(), realIds: new Set(), draftKeys: new Set(), draftIds: new Set() };
    for (const m of res.data.messages || []) {
      const key = keyOf(header((m.payload && m.payload.headers) || [], 'Message-ID'));
      const isDraft = (m.labelIds || []).includes(mboxlib.DRAFT_LABEL);
      (isDraft ? lv.draftIds : lv.realIds).add(m.id);
      if (key) (isDraft ? lv.draftKeys : lv.realKeys).add(key);
    }
    return lv;
  } catch (err) {
    if (GONE_RE.test(String(err.message)) || err.code === 404) return { exists: false };
    return { exists: null, error: err.message };
  }
}

// --- applying ----------------------------------------------------------

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

/** Add `.private/` to the matter's .gitignore unless something there already covers it. */
function ensurePrivateIgnored(matterDir) {
  const gi = path.join(matterDir, '.gitignore');
  const text = fs.existsSync(gi) ? fs.readFileSync(gi, 'utf-8') : '';
  const covered = text.split('\n').some((l) => /^\/?\.private(\/(\*\*?)?)?\s*$/.test(l.trim()));
  if (covered) return false;
  const sep = text && !text.endsWith('\n') ? '\n' : '';
  fs.writeFileSync(gi, `${text}${sep}\n${GITIGNORE_COMMENT}\n${GITIGNORE_LINE}\n`);
  return true;
}

function uniqueDir(base) {
  if (!fs.existsSync(base)) return base;
  let i = 2;
  while (fs.existsSync(`${base}_${i}`)) i++;
  return `${base}_${i}`;
}

/** Move a render's files under .private/gmail_drafts/<stem>/, keeping their paths. */
function moveOut(matterDir, finding) {
  const dest = uniqueDir(path.join(matterDir, PRIVATE_DRAFTS_DIR, finding.stem));
  const moved = [];
  for (const rel of finding.files || []) {
    const src = path.join(matterDir, rel);
    if (!fs.existsSync(src)) continue;
    const to = path.join(dest, rel);
    const record = { from: rel };
    if (fs.statSync(src).isFile()) record.sha256 = sha256(src);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.renameSync(src, to);
    moved.push(record);
  }
  return { dest, moved };
}

/**
 * Apply one finding. ctx: {matterDir, outDir, ledger (this account's),
 * gmail, captureThread, render, quoted, identity, tmpDir}. Returns a
 * one-line description of what was done, and prints NEW lines for
 * anything re-rendered.
 */
async function applyFinding(finding, ctx) {
  if (finding.kind === 'unverified') return 'not touched (unverified)';
  const { matterDir, outDir, ledger } = ctx;
  const entry = finding.threadId ? ledger.threads[finding.threadId] : null;
  const mboxPath = mboxlib.mboxPathFor(outDir, `${finding.stem}.pdf`);
  const { dest, moved } = moveOut(matterDir, finding);
  const manifest = {
    movedAt: new Date().toISOString(),
    reason: finding.kind,
    rule: 'A draft is not mail (ADR-0049); moved out of the record by sc mail-audit-drafts --apply.',
    threadId: finding.threadId,
    draftGmailIds: finding.draftGmailIds || [],
    evidence: finding.evidence,
    moved,
    ledgerEntry: entry || null,
    rebuilt: null,
  };
  let done;
  if (finding.kind === 'draft-only') {
    if (finding.threadId) delete ledger.threads[finding.threadId];
    done = `moved to ${path.relative(matterDir, dest)}`;
  } else {
    // mixed: rebuild the thread without its drafts
    const movedMbox = path.join(dest, path.relative(matterDir, mboxPath));
    if (finding.source === 'mbox' && fs.existsSync(movedMbox)) {
      const drop = new Set(finding.draftIndexes || []);
      const keep = mboxlib.readMessages(movedMbox).filter((_, i) => !drop.has(i));
      mboxlib.appendMessages(mboxPath, keep.map((raw) => ({ id: null, raw })));
    } else if (finding.threadId && ctx.gmail && ctx.captureThread) {
      await ctx.captureThread(ctx.gmail, finding.threadId, mboxPath);
    } else {
      fs.writeFileSync(path.join(dest, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
      return `moved to ${path.relative(matterDir, dest)}; NOT rebuilt (no mbox and no thread id)`;
    }
    const messages = fs.existsSync(mboxPath) ? ctx.render.loadThread(mboxPath) : [];
    if (!messages.length) {
      if (finding.threadId) delete ledger.threads[finding.threadId];
      done = `moved to ${path.relative(matterDir, dest)}; nothing but drafts remained`;
    } else {
      const pdfPath = path.join(outDir, `${finding.stem}.pdf`);
      await ctx.render.renderMboxToPdf(mboxPath, pdfPath, {
        messages,
        subject: ctx.render.threadSubject(messages),
        account: ctx.identity,
        quoted: ctx.quoted,
        tmpDir: ctx.tmpDir,
      });
      console.log(`NEW ${pdfPath}`);
      const written = ctx.render.extractAttachments(messages, ctx.render.attachmentsDirFor(mboxPath), {});
      for (const f of written) if (f.created) console.log(`NEW ${f.path}`);
      if (finding.threadId && entry) {
        const drafts = new Set(finding.draftGmailIds || []);
        const next = { ...entry };
        delete next.draftCount;
        delete next.latestDraftAt;
        next.messageCount = messages.length;
        if (Array.isArray(entry.messageIds)) next.messageIds = entry.messageIds.filter((id) => !drafts.has(id));
        next.mbox = path.relative(outDir, mboxPath);
        next.filename = `${finding.stem}.pdf`;
        next.exportedAt = new Date().toISOString();
        next.attachments = written.map((f) => ({ name: f.name, size: f.size }));
        ledger.threads[finding.threadId] = next;
      }
      manifest.rebuilt = { messages: messages.length, pdf: path.relative(matterDir, pdfPath) };
      done = `moved to ${path.relative(matterDir, dest)}; rebuilt with ${messages.length} message(s)`;
    }
  }
  fs.writeFileSync(path.join(dest, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  return done;
}

module.exports = {
  PRIVATE_DRAFTS_DIR,
  DRAFT_STATE,
  normalizeText,
  snippetKey,
  textHasSnippet,
  printedMessageCount,
  candidateStemPattern,
  classifyStoredThread,
  filesForStem,
  indexMatter,
  auditRecord,
  formatReport,
  listDrafts,
  liveThread,
  ensurePrivateIgnored,
  moveOut,
  applyFinding,
};
