#!/usr/bin/env node
//
// gmail connector — capture threads as raw mail, render them as PDFs.
//
// Usage:  node pull.js <matter_dir> [--dry-run] [--force]
//                                   [--backfill-mbox [--limit N]]
//                                   [--account <email>] [--concurrency N] [--full]
//
// Config (matter.yaml, connectors.gmail; legacy envelopes.yaml
// gmail_addresses: also read):
//   gmail:
//     accounts:             # optional; one OAuth token per mailbox
//       - jane@example.com
//       - service@example.com
//     addresses:            # plain address, bare domain, or {address, after, before}
//       - opposing@example.com
//       - examplefirm.com
//       - address: someone@example.com
//         after: 2024/04/01
//     quoted: show          # show (default) | hide, in the rendered PDF
//     ignore_unlisted:      # addresses/domains never reported as unlisted
//       - newsletter.example
//
// The address list is the only capture criterion. What the connector
// adds beside it is a WATCH on the list's edges, never a second net:
//   - after each listing it reads the metadata (To/Cc/Date/Subject,
//     never a body) of the mailbox owner's SENT messages in the same
//     window and writes every recipient the list does not cover to
//     .state/gmail_unlisted.json, so a correspondent the owner has
//     written to but nobody listed is named in the brief instead of
//     silently absent from the record;
//   - a thread's unsent drafts are counted in its ledger entry
//     (draftCount, latestDraftAt) so the brief can say a reply is
//     still sitting in Drafts.
//
// Credentials: OAuth client keys + one token per account live in
// $PROSAIC_GMAIL_CREDS_DIR (default ~/.config/prosaic/gmail/); see
// creds.js. Run `node auth.js [--account <email>]` once per mailbox.
//
// WHAT THIS WRITES (ADR-0038 — the raw message is the record):
//
//   <matter>/assets/gmail/mbox/<stem>.mbox     the thread, verbatim
//   <matter>/assets/gmail/<stem>.pdf           the print view, rendered
//   <matter>/assets/gmail/attachments/<stem>/  parts extracted from it
//
// The mbox holds every captured message as the Gmail API returned it
// for format=raw: RFC 822 bytes, headers, MIME structure, quoted
// chains and attachment payloads, in mboxrd (see mbox.js). It is the
// canonical record and is append-only. The PDF is a *rendering* of it
// (render.js) and can be regenerated at any time, with different
// options, without touching the network — which is the point: a
// presentation that hides content is a poor evidentiary record, and
// one whose source was never stored cannot be corrected.
//
// stdout carries "NEW <abs path>" for the PDF and each attachment, and
// nothing else. The mbox is deliberately NOT announced: it is the
// source the announced PDF was rendered from, not a second document,
// and a NEW line would put a duplicate row in the matter's catalog for
// the same evidence.
//
// Incrementality: a durable ledger in .state/gmail.json, keyed by
// account and then by Gmail thread id — thread ids are per-mailbox, so
// two accounts watching the same correspondence cannot collide:
//
//   { "version": 2, "accounts": { "<account>": { "identity": ...,
//       "threads": { "<threadId>": { historyId, messageCount, filename,
//          mbox, exportedAt, attachments: [{name, size}] } } } } }
//
// Each run lists matching threads (cheap; the list stub carries a
// per-thread historyId that changes whenever the thread changes) and:
//   - skips a thread outright when its historyId matches the ledger
//     (no fetch, no render, no NEW) — so a broad domain filter doesn't
//     re-examine the whole history every 12h;
//   - re-exports a thread only when it has GROWN (a new message), so an
//     updated thread is re-triaged, while a mere label/read-state change
//     just refreshes the stored historyId;
//   - on first run against a matter that already has assets/gmail/ PDFs
//     from before this ledger existed, absorbs those into the ledger
//     without re-exporting (no mass re-triage).
// Because a thread is remembered by id, downstream triage may move or
// rename the exported PDF and it will NOT be re-pulled. Pulls are
// idempotent (connector contract, docs/connectors.md).
//
// --backfill-mbox is the one-time catch-up for threads exported before
// the mbox existed: it fetches raw mail for ledger entries that have no
// mbox yet, writes it, and stops. It renders nothing and prints no NEW
// lines, so a matter's triage is not re-run for PDFs it already has.
// --limit N bounds a run, per account (Gmail's per-user quota is
// finite) and the ledger is written after each thread, so the next run
// resumes where this one stopped.

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
const os = require('os');
const path = require('path');

const { connectorConfig, loadState, saveState } = require('../core/config');
const { google } = require('googleapis');

const creds = require('./creds');
const mboxlib = require('./mbox');
const render = require('./render');

//: Ledger format. v1 was a bare {threads:{}} for one mailbox; v2 nests
//: threads under an account key because Gmail thread ids are scoped to
//: a mailbox and two accounts can hand out the same id.
const LEDGER_VERSION = 2;

//: Pause between threads during a backfill. The quota this respects is
//: a per-user rate limit, not a daily cap; a small sleep keeps a long
//: catch-up from tripping it.
const BACKFILL_PAUSE_MS = 200;

function snakeCase(str) {
  return str
    .replace(/^(?:re):\s*/gi, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .substring(0, 80);
}

//: Per-request timeout and retry for the Gmail API. A raw fetch of a
//: large message has hung indefinitely in practice (0% CPU, no error);
//: googleapis forwards these options to gaxios, so a stalled socket
//: becomes a retryable error instead of a stuck run.
const API_TIMEOUT_MS = 60 * 1000;
const API_ATTEMPTS = 3;

async function apiCall(fn, label) {
  let lastErr;
  for (let attempt = 1; attempt <= API_ATTEMPTS; attempt++) {
    try {
      return await fn({ timeout: API_TIMEOUT_MS });
    } catch (err) {
      lastErr = err;
      const status = err && err.code;
      const text = String((err && err.message) || '');
      const transient =
        !status ||
        status === 'ETIMEDOUT' ||
        status === 'ECONNRESET' ||
        status === 'ECONNREFUSED' ||
        status === 'ENOTFOUND' ||
        status === 'EAI_AGAIN' ||
        //: the OAuth refresh runs inside the client and surfaces a DNS
        //: or socket failure as a plain FetchError; treat it the same.
        /ENOTFOUND|EAI_AGAIN|ECONNRESET|ETIMEDOUT|socket hang up/.test(text) ||
        status === 429 ||
        (Number(status) >= 500 && Number(status) < 600);
      if (!transient || attempt === API_ATTEMPTS) break;
      console.error(`  retry ${attempt}/${API_ATTEMPTS - 1} ${label}: ${err.message}`);
      await sleep(1000 * attempt);
    }
  }
  throw lastErr;
}

//: Concurrency. Every message is its own round trip, and a mailbox of
//: hundreds of threads is thousands of them; done one at a time that is
//: the whole wall clock. Gmail allows 250 quota units per user per
//: second and a raw messages.get costs 5, so the ceiling is ~50/s; these
//: defaults stay well under it and 429s fall back on apiCall's retry.
const MESSAGE_CONCURRENCY = 6; // raw fetches in flight per thread
const THREAD_CONCURRENCY = 4; // threads in flight during a backfill
const METADATA_CONCURRENCY = 8; // threads.get(metadata) in flight while deciding

/**
 * Run fn over items with at most `limit` in flight. Results keep the
 * input order; the first rejection rejects the whole map once the
 * in-flight work has settled (so callers see one error, not a flood).
 */
async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  let firstError = null;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      if (firstError) return;
      try {
        results[i] = await fn(items[i], i);
      } catch (err) {
        if (!firstError) firstError = err;
        return;
      }
    }
  };
  const n = Math.max(1, Math.min(limit, items.length));
  await Promise.all(Array.from({ length: n }, worker));
  if (firstError) throw firstError;
  return results;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getHeader(headers, name) {
  return headers.find((h) => h.name.toLowerCase() === name.toLowerCase())?.value;
}

// A gmail addresses entry is either a plain string (address or bare
// domain) or an object with per-address constraints:
//   - address: someone@example.com
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
  const bounds = [
    entry.after && `after:${entry.after}`,
    entry.before && `before:${entry.before}`,
  ]
    .filter(Boolean)
    .join(' ');
  return bounds ? `${entry.address} (${bounds})` : entry.address;
}

/**
 * The listing query. With `newerThanDays`, only threads that received a
 * message inside the window are listed — Gmail's newer_than: applies
 * per message, and a thread is returned when any message matches — so
 * a routine run touches O(recent threads), not the whole history.
 */
function listingQuery(addresses, { newerThanDays } = {}) {
  const clauses = addresses.map(addressClause).join(' OR ');
  return newerThanDays ? `(${clauses}) newer_than:${newerThanDays}d` : clauses;
}

async function searchThreads(gmail, addresses, opts = {}) {
  const query = listingQuery(addresses, opts);
  const threads = [];
  let pageToken;
  do {
    const res = await apiCall(
      (o) => gmail.users.threads.list({ userId: 'me', q: query, maxResults: 100, pageToken }, o),
      'threads.list'
    );
    if (res.data.threads) threads.push(...res.data.threads);
    pageToken = res.data.nextPageToken;
  } while (pageToken);
  return threads;
}

//: How often to re-list the whole history. The incremental window
//: catches every thread with a NEW message; what it cannot see is a
//: message removed from a thread with nothing added, so a full pass
//: runs periodically (or on --full) to reconcile message sets.
const FULL_LIST_EVERY_DAYS = 7;
const WINDOW_SLACK_DAYS = 2;
const MIN_WINDOW_DAYS = 3;

/**
 * Decide how much of the mailbox this run lists. Pure: the ledger's
 * lastRunAt / lastFullListAt stamps and the clock decide.
 */
function listingPlan(ledger, now = new Date(), { full = false } = {}) {
  const day = 86400000;
  if (full || !ledger.lastFullListAt) return { full: true };
  const sinceFull = (now - Date.parse(ledger.lastFullListAt)) / day;
  if (!(sinceFull < FULL_LIST_EVERY_DAYS)) return { full: true };
  const last = ledger.lastRunAt ? Date.parse(ledger.lastRunAt) : Date.parse(ledger.lastFullListAt);
  const sinceRun = Math.max(0, (now - last) / day);
  return {
    full: false,
    newerThanDays: Math.max(MIN_WINDOW_DAYS, Math.ceil(sinceRun) + WINDOW_SLACK_DAYS),
  };
}

// --- the ledger -------------------------------------------------------

/**
 * Read the ledger, lifting a v1 single-mailbox ledger into v2.
 *
 * A v1 ledger's threads belong to whichever mailbox the pre-accounts
 * token authorized, which is the same mailbox `accounts:` names first
 * (creds.js gives that account the legacy token). Migrating them under
 * the primary's key is therefore the fact, not a guess — and it is
 * what keeps adding a second account from re-exporting the first
 * account's entire history.
 */
function loadLedger(matterDir, primaryKey) {
  const state = loadState(matterDir, 'gmail', {});
  if (!state.accounts) state.accounts = {};
  if (state.threads) {
    const target = (state.accounts[primaryKey] = state.accounts[primaryKey] || {
      threads: {},
    });
    target.threads = { ...state.threads, ...(target.threads || {}) };
    delete state.threads;
  }
  state.version = LEDGER_VERSION;
  return state;
}

function ledgerFor(state, key) {
  if (!state.accounts[key]) state.accounts[key] = { threads: {} };
  if (!state.accounts[key].threads) state.accounts[key].threads = {};
  return state.accounts[key];
}

/** Every PDF filename any account has claimed, plus what is on disk. */
function claimedFilenames(state, outDir) {
  const claimed = new Set(fs.existsSync(outDir) ? fs.readdirSync(outDir) : []);
  for (const account of Object.values(state.accounts)) {
    for (const entry of Object.values(account.threads || {})) {
      if (entry && entry.filename) claimed.add(entry.filename);
    }
  }
  return claimed;
}

// --- one thread, one filename ---------------------------------------------

/** Is this PDF filename already the record of a DIFFERENT thread? */
function filenameClaimedByAnother(state, filename, threadId) {
  for (const account of Object.values(state.accounts || {})) {
    for (const [id, entry] of Object.entries(account.threads || {})) {
      if (id !== threadId && entry && entry.filename === filename) return true;
    }
  }
  return false;
}

/**
 * Two threads must never share a filename: the mbox path follows the
 * filename, so a shared name mixed two threads' messages into one
 * record and let one thread's PDF stand for another. Pre-ledger PDFs
 * absorbed by subject-and-date collided this way. For each group of
 * entries on one filename, the first keeps it; the rest get a unique
 * name and no PDF (the backfill renders theirs afresh); every member
 * loses its mbox record and the mixed file is deleted so the backfill
 * recaptures each thread into its own file. Returns the renames.
 */
function repairSharedFilenames(ledger, outDir, uniqueName, { dryRun = false } = {}) {
  const byName = new Map();
  for (const [id, entry] of Object.entries(ledger.threads)) {
    if (!entry || !entry.filename) continue;
    if (!byName.has(entry.filename)) byName.set(entry.filename, []);
    byName.get(entry.filename).push(id);
  }
  const renames = [];
  for (const [filename, ids] of byName) {
    if (ids.length < 2) continue;
    const mixed = mboxlib.mboxPathFor(outDir, filename);
    for (const [i, id] of ids.entries()) {
      const entry = ledger.threads[id];
      const to = i === 0 ? filename : uniqueName(filename);
      renames.push({ threadId: id, from: filename, to });
      if (dryRun) continue;
      ledger.threads[id] = {
        ...entry,
        filename: to,
        ...(i === 0 ? {} : { exportedAt: null, renamedFrom: filename }),
      };
      delete ledger.threads[id].mbox;
      delete ledger.threads[id].messageIds;
    }
    if (!dryRun && fs.existsSync(mixed)) fs.unlinkSync(mixed);
  }
  return renames;
}

// --- drafts --------------------------------------------------------------

//: A draft is not mail. Gmail keeps unsent drafts (including scheduled
//: sends) inside the thread they belong to, and threads.get returns
//: them beside the real messages. An earlier export rendered a
//: scheduled-then-cancelled draft as though it had been sent; the
//: matter's record then said a message went out that never did. So a
//: message carrying the DRAFT label is never captured, counted or
//: rendered.
function isNotDraft(message) {
  return !(message.labelIds || []).includes('DRAFT');
}

// --- change detection --------------------------------------------------

/**
 * Can a listed thread be skipped from its list stub alone? Only when the
 * ledger's historyId matches AND the entry already carries a draft
 * count: an entry recorded before drafts were counted is examined once
 * (one metadata fetch) so the brief's draft report is true from the
 * first run rather than after the thread happens to change.
 */
function entryCurrent(prev, t, force = false) {
  return (
    !force &&
    !!prev &&
    prev.historyId != null &&
    t.historyId != null &&
    String(prev.historyId) === String(t.historyId) &&
    prev.draftCount !== undefined
  );
}

/**
 * Has a known thread changed in a way that needs a re-export?
 *
 * Growth is the common case. But a thread can change without growing:
 * a superseded send deleted from the mailbox after the connector
 * exported it, and its replacement threaded in beside it, leaves the
 * count where it was while the content is different. So when the
 * ledger knows which message ids it exported, any difference in the
 * id SET re-exports. An entry from before ids were recorded falls back
 * to the count comparison; it gains ids on its next export or backfill.
 */
function threadChanged(prev, meta, force = false) {
  if (force) return true;
  if ((meta.messageCount || 0) > (prev.messageCount || 0)) return true;
  if (Array.isArray(prev.messageIds) && Array.isArray(meta.messageIds)) {
    const before = new Set(prev.messageIds);
    const after = new Set(meta.messageIds);
    if (before.size !== after.size) return true;
    for (const id of after) if (!before.has(id)) return true;
  }
  return false;
}

// --- one thread -------------------------------------------------------

/**
 * Fetch a thread's raw messages and append them to its mbox.
 *
 * Returns {mboxPath, added, total}. `added` is the Gmail message ids
 * actually written; a re-fetch of an unchanged thread adds nothing,
 * because mbox.js dedups on Message-ID.
 */
async function captureThread(gmail, threadId, mboxPath, { known = [] } = {}) {
  //: threads.get does not accept format=raw (only full, metadata,
  //: minimal); the raw RFC 822 bytes come from messages.get, one call
  //: per message. Ids come from the cheapest thread view.
  const res = await apiCall(
    (opts) => gmail.users.threads.get({ userId: 'me', id: threadId, format: 'minimal' }, opts),
    `threads.get ${threadId}`
  );
  const stubs = (res.data.messages || []).filter(isNotDraft);
  //: Fetch only what the mbox does not already hold. `known` is the
  //: ledger's record of Gmail ids stored for this thread; it is trusted
  //: only while the mbox it describes exists.
  const have = new Set(fs.existsSync(mboxPath) ? known : []);
  const wanted = stubs.filter((stub) => !have.has(stub.id));
  const messages = await mapLimit(wanted, MESSAGE_CONCURRENCY, async (stub) => {
    const msg = await apiCall(
      (opts) => gmail.users.messages.get({ userId: 'me', id: stub.id, format: 'raw' }, opts),
      `messages.get ${stub.id}`
    );
    return {
      id: msg.data.id || stub.id,
      internalDate: msg.data.internalDate || stub.internalDate,
      raw: Buffer.from(msg.data.raw, 'base64url'),
    };
  });
  const result = mboxlib.appendMessages(mboxPath, messages);
  return {
    mboxPath,
    added: result.added,
    fetched: messages.length,
    total: stubs.length,
    ids: stubs.map((m) => m.id),
  };
}

// --- unlisted correspondents -------------------------------------------
//
// The address list defines the corpus (spec promise 6) and nothing here
// widens it. But a list is only as complete as the last person who
// edited it, and the mailbox owner writing to someone is the strongest
// signal that the someone belongs on it. So each run looks at the
// owner's SENT messages in the same window — headers only, never a
// body, nothing exported — and reports every recipient the list does
// not cover. The brief prints the report; a human edits matter.yaml.

const UNLISTED_STATE = 'gmail_unlisted';
const UNLISTED_LIMIT = 200; // sent messages examined per run
const NOISE_LOCALS = /^(no-?reply|noreply|do-?not-?reply|donotreply|notifications?|mailer-daemon|postmaster|bounce|alerts?)([+.-]|$)/i;

/** Every address in a To/Cc header value, lowercased. */
function parseAddresses(headerValue) {
  if (!headerValue) return [];
  const out = [];
  const re = /<([^<>\s]+@[^<>\s]+)>|([^\s<>,;"']+@[^\s<>,;"']+)/g;
  let m;
  while ((m = re.exec(headerValue))) out.push((m[1] || m[2]).toLowerCase().replace(/[.,;]+$/, ''));
  return out;
}

/** Gmail treats dots and +tags in the local part as the same mailbox. */
function canonicalAddress(address) {
  const a = String(address || '').toLowerCase().trim();
  const at = a.lastIndexOf('@');
  if (at === -1) return a;
  let local = a.slice(0, at);
  const domain = a.slice(at + 1);
  if (domain === 'gmail.com' || domain === 'googlemail.com') {
    local = local.split('+')[0].replace(/\./g, '');
    return `${local}@gmail.com`;
  }
  return `${local.split('+')[0]}@${domain}`;
}

/**
 * Does a configured entry (address, bare domain, or {address}) cover
 * this recipient? A bare domain covers the domain and its subdomains,
 * exactly as Gmail's from:/to: domain match does.
 */
function addressCovered(address, entries) {
  const a = canonicalAddress(address);
  const domain = a.slice(a.lastIndexOf('@') + 1);
  for (const entry of entries || []) {
    const e = String(typeof entry === 'string' ? entry : entry && entry.address).toLowerCase().trim();
    if (!e) continue;
    if (e.includes('@')) {
      if (canonicalAddress(e) === a) return true;
    } else if (domain === e || domain.endsWith(`.${e}`)) {
      return true;
    }
  }
  return false;
}

/** Automated senders and the owner's own mailboxes are never "correspondents". */
function isNoiseAddress(address, ownAddresses = []) {
  const a = canonicalAddress(address);
  if (ownAddresses.some((o) => canonicalAddress(o) === a)) return true;
  return NOISE_LOCALS.test(a.slice(0, a.lastIndexOf('@')));
}

/**
 * Recipients of the owner's sent mail that no configured entry covers,
 * newest first, one row per address. Pure over the injected client:
 * messages.list for `in:sent` in the window, then metadata-only
 * messages.get (To, Cc, Date, Subject). No body is ever requested.
 */
async function collectUnlisted(gmail, { addresses, ignore = [], ownAddresses = [], newerThanDays, limit = UNLISTED_LIMIT }) {
  const ids = [];
  let pageToken;
  const q = `in:sent newer_than:${newerThanDays}d`;
  do {
    const res = await apiCall(
      (o) => gmail.users.messages.list({ userId: 'me', q, maxResults: Math.min(100, limit - ids.length), pageToken }, o),
      'messages.list in:sent'
    );
    for (const m of res.data.messages || []) if (ids.length < limit) ids.push(m);
    pageToken = ids.length < limit ? res.data.nextPageToken : undefined;
  } while (pageToken);

  const found = new Map();
  const metas = await mapLimit(ids, METADATA_CONCURRENCY, async (stub) => {
    const res = await apiCall(
      (o) => gmail.users.messages.get({ userId: 'me', id: stub.id, format: 'metadata', metadataHeaders: ['To', 'Cc', 'Date', 'Subject'] }, o),
      `messages.get ${stub.id}`
    );
    return res.data;
  });
  for (const msg of metas) {
    const headers = (msg.payload && msg.payload.headers) || [];
    const dateStr = getHeader(headers, 'Date');
    const date = dateStr && !Number.isNaN(Date.parse(dateStr)) ? new Date(dateStr).toISOString() : null;
    const subject = getHeader(headers, 'Subject') || 'no_subject';
    const recipients = [...parseAddresses(getHeader(headers, 'To')), ...parseAddresses(getHeader(headers, 'Cc'))];
    for (const address of recipients) {
      if (isNoiseAddress(address, ownAddresses)) continue;
      if (addressCovered(address, addresses) || addressCovered(address, ignore)) continue;
      const prev = found.get(address);
      if (prev && prev.date && date && prev.date >= date) continue;
      found.set(address, {
        address,
        domain: address.slice(address.lastIndexOf('@') + 1),
        date,
        subject,
        threadId: msg.threadId || null,
      });
    }
  }
  return [...found.values()].sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
}

/**
 * Merge this run's findings into .state/gmail_unlisted.json. An address
 * already recorded keeps its newest sighting; one the list now covers
 * (someone edited matter.yaml) or that ignore_unlisted names is dropped,
 * so the report only ever names what is still uncaptured.
 */
function mergeUnlisted(previous, rows, { addresses, ignore = [], windowDays }) {
  const byAddress = {};
  for (const row of Object.values((previous && previous.correspondents) || {})) {
    if (row && row.address && !addressCovered(row.address, addresses) && !addressCovered(row.address, ignore)) {
      byAddress[row.address] = row;
    }
  }
  for (const row of rows) {
    const prev = byAddress[row.address];
    if (!prev || !prev.date || (row.date && row.date > prev.date)) byAddress[row.address] = row;
  }
  return {
    version: 1,
    updatedAt: new Date().toISOString(),
    windowDays,
    correspondents: byAddress,
  };
}

async function reportUnlisted(ctx, gmail, userEmail, windowDays) {
  const { cfg, matterDir, dryRun } = ctx;
  const ownAddresses = [userEmail, ...(cfg.accounts || []).filter((a) => typeof a === 'string')];
  let rows;
  try {
    rows = await collectUnlisted(gmail, {
      addresses: cfg.addresses,
      ignore: cfg.ignore_unlisted || [],
      ownAddresses,
      newerThanDays: windowDays,
    });
  } catch (err) {
    console.error(`[${userEmail}] unlisted-correspondent check failed: ${err.message}`);
    return null;
  }
  const previous = loadState(matterDir, UNLISTED_STATE, {});
  const merged = mergeUnlisted(previous, rows, {
    addresses: cfg.addresses,
    ignore: cfg.ignore_unlisted || [],
    windowDays,
  });
  const n = Object.keys(merged.correspondents).length;
  console.error(
    `[${userEmail}] ${n} correspondent(s) the address list does not cover` +
      (n ? ` (see .state/${UNLISTED_STATE}.json; add to connectors.gmail.addresses to capture)` : '')
  );
  if (!dryRun) saveState(matterDir, UNLISTED_STATE, merged);
  return merged;
}

// --- main -------------------------------------------------------------

//: Flags that take a value, so the value is not mistaken for the
//: matter directory: `pull.js --limit 50 .` names one matter, not two.
const VALUE_FLAGS = new Set(['--account', '--limit', '--concurrency']);

function flagValue(name, fallback) {
  const i = process.argv.indexOf(name);
  if (i === -1) return fallback;
  const next = process.argv[i + 1];
  return next && !next.startsWith('--') ? next : fallback;
}

function positionalArgs() {
  const argv = process.argv.slice(2);
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

/**
 * One thread's decision inputs: subject, date-derived filename, count
 * and ids of its non-draft messages. Null for a draft-only thread.
 */
async function fetchThreadMeta(gmail, t) {
  const res = await apiCall(
    (opts) =>
      gmail.users.threads.get(
        {
          userId: 'me',
          id: t.id,
          format: 'metadata',
          metadataHeaders: ['Subject', 'Date'],
          //: labelIds ride along with metadata; isNotDraft needs them.
        },
        opts
      ),
    `threads.get ${t.id}`
  );
  const all = res.data.messages || [];
  const msgs = all.filter(isNotDraft);
  if (msgs.length === 0) return null;
  const firstMsg = msgs[0];
  const subject = getHeader(firstMsg.payload.headers, 'Subject') || 'no_subject';
  const dateStr = getHeader(firstMsg.payload.headers, 'Date');
  const date = dateStr ? new Date(dateStr) : new Date();
  const yyyymmdd = date.toISOString().slice(0, 10).replace(/-/g, '');
  //: Drafts are not mail (see isNotDraft), but a reply that never left
  //: Drafts is a fact the matter needs: the record would otherwise show
  //: a letter answered when nothing went out. Counted, never captured.
  const drafts = all.filter((m) => !isNotDraft(m));
  const draftDates = drafts
    .map((m) => getHeader((m.payload && m.payload.headers) || [], 'Date'))
    .filter(Boolean)
    .map((s) => new Date(s))
    .filter((d) => !Number.isNaN(d.getTime()));
  return {
    threadId: t.id,
    historyId: t.historyId,
    subject,
    messageCount: msgs.length,
    messageIds: msgs.map((m) => m.id),
    draftCount: drafts.length,
    latestDraftAt: draftDates.length
      ? new Date(Math.max(...draftDates.map((d) => d.getTime()))).toISOString()
      : null,
    defaultFilename: `${yyyymmdd}_${snakeCase(subject)}.pdf`,
  };
}

async function pullAccount(ctx, account) {
  const runCtx = { ...ctx };
  const exported = await pullAccountListed(runCtx, account);
  if (!ctx.dryRun) {
    const ledger = ledgerFor(ctx.state, creds.accountKey(account));
    const now = new Date().toISOString();
    ledger.lastRunAt = now;
    if (runCtx.plan && runCtx.plan.full) ledger.lastFullListAt = now;
    saveState(ctx.matterDir, 'gmail', ctx.state);
  }
  return exported;
}

async function pullAccountListed(ctx, account) {
  const { gmail, cfg, outDir, state, uniqueName, dryRun, force } = ctx;
  const key = creds.accountKey(account);
  const ledger = ledgerFor(state, key);
  const existingFiles = new Set(fs.readdirSync(outDir));

  const profile = await gmail.users.getProfile({ userId: 'me' });
  const userEmail = profile.data.emailAddress;
  let identity = ledger.identity || userEmail;

  const plan = listingPlan(ledger, new Date(), { full: ctx.full });
  ctx.plan = plan;
  console.error(
    `[${userEmail}] ${plan.full ? 'full listing' : `incremental listing (newer_than:${plan.newerThanDays}d)`}` +
      ` for: ` +
      cfg.addresses.map(addressDisplay).join(', ')
  );
  const threadList = await searchThreads(
    gmail,
    cfg.addresses,
    plan.full ? {} : { newerThanDays: plan.newerThanDays }
  );
  //: The watch on the list's edges. A full listing has no window; the
  //: sent-mail check then looks back one full-listing period.
  await reportUnlisted(ctx, gmail, userEmail, plan.full ? FULL_LIST_EVERY_DAYS : plan.newerThanDays);
  const seen = new Set();
  const uniqueThreads = threadList.filter((t) => {
    if (seen.has(t.id)) return false;
    seen.add(t.id);
    return true;
  });
  console.error(`[${userEmail}] found ${uniqueThreads.length} threads.`);
  if (uniqueThreads.length === 0) return 0;

  // Decide which threads need a (re)export. Unchanged threads
  // (historyId matches the ledger) are skipped without a metadata fetch.
  const toExport = [];
  let skippedUnchanged = 0;
  let seeded = 0;
  const unchanged = (t) => entryCurrent(ledger.threads[t.id], t, force);
  // Metadata for every thread that might need work, fetched concurrently
  // up front; the decisions below stay sequential so ledger writes keep
  // their order.
  const needMeta = uniqueThreads.filter((t) => !unchanged(t));
  const metaById = new Map();
  await mapLimit(needMeta, METADATA_CONCURRENCY, async (t) => {
    try {
      metaById.set(t.id, { meta: await fetchThreadMeta(gmail, t) });
    } catch (err) {
      metaById.set(t.id, { error: err });
    }
  });
  for (const t of uniqueThreads) {
    const prev = ledger.threads[t.id];
    if (unchanged(t)) {
      skippedUnchanged++;
      continue;
    }

    const fetched = metaById.get(t.id);
    if (fetched && fetched.error) {
      console.error(`  warning: skipping thread ${t.id}: ${fetched.error.message}`);
      continue;
    }
    if (!fetched || !fetched.meta) {
      // A thread that is nothing but a draft is not mail yet.
      continue;
    }
    const meta = fetched.meta;

    if (prev) {
      // Known thread whose historyId moved. Re-export only if its
      // message set changed (see threadChanged); a label or read-state
      // change just refreshes the stored historyId. An entry that
      // predates the mbox is left alone: giving it one is
      // --backfill-mbox's job precisely so that a PDF the matter has
      // already triaged is not announced a second time.
      if (threadChanged(prev, meta, force)) {
        meta.filename = prev.filename || uniqueName(meta.defaultFilename);
        meta.previous = prev;
        toExport.push(meta);
      } else {
        ledger.threads[t.id] = {
          ...prev,
          historyId: meta.historyId,
          messageCount: meta.messageCount,
          messageIds: meta.messageIds,
          draftCount: meta.draftCount || 0,
          latestDraftAt: meta.latestDraftAt || null,
        };
        if (!dryRun) saveState(ctx.matterDir, 'gmail', state);
      }
      continue;
    }

    // New to the ledger. If a matching export already sits on disk from
    // a pre-ledger pull, absorb it without re-triaging. It has no mbox;
    // --backfill-mbox is how it gets one.
    if (
      !force &&
      existingFiles.has(meta.defaultFilename) &&
      !filenameClaimedByAnother(state, meta.defaultFilename, t.id)
    ) {
      ledger.threads[t.id] = {
        historyId: meta.historyId,
        messageCount: meta.messageCount,
        filename: meta.defaultFilename,
        exportedAt: null,
        migrated: true,
      };
      if (!dryRun) saveState(ctx.matterDir, 'gmail', state);
      seeded++;
      continue;
    }

    meta.filename = uniqueName(meta.defaultFilename);
    toExport.push(meta);
  }

  console.error(
    `[${userEmail}] ${toExport.length} to export, ${skippedUnchanged} unchanged ` +
      `(skipped), ${seeded} pre-existing absorbed.`
  );

  if (dryRun) {
    console.error('  -- dry run --');
    for (const m of toExport) console.error(`  ${m.filename}  (${m.messageCount} msg)`);
    if (toExport.length === 0) console.error('  (nothing new)');
    return 0;
  }
  if (toExport.length === 0) return 0;

  let exported = 0;
  for (const meta of toExport) {
    process.stderr.write(`  ${meta.filename} ... `);
    try {
      const mboxPath = mboxlib.mboxPathFor(outDir, meta.filename);
      await captureThread(gmail, meta.threadId, mboxPath, {
        known: (meta.previous && meta.previous.messageIds) || [],
      });
      const messages = render.loadThread(mboxPath);

      // The identity in the print view's header line: the mailbox, with
      // whatever display name it uses in its own messages.
      if (identity === userEmail) {
        for (const message of messages) {
          const from = message.node.header('From');
          if (from && from.includes(userEmail) && from.includes('<')) {
            identity = from;
            break;
          }
        }
      }

      const pdfPath = path.join(outDir, meta.filename);
      await render.renderMboxToPdf(mboxPath, pdfPath, {
        messages,
        subject: meta.subject,
        account: identity,
        quoted: ctx.quoted,
        tmpDir: ctx.tmpDir,
      });
      exported++;
      console.error('ok');
      console.log(`NEW ${pdfPath}`);

      const written = render.extractAttachments(
        messages,
        render.attachmentsDirFor(mboxPath),
        {
          onSkip: (att) =>
            console.error(
              `  SKIPPED ${att.originalName} (${render.fmtSize(att.size)} exceeds ` +
                `${render.fmtSize(render.MAX_ATTACHMENT_BYTES)} cap)`
            ),
        }
      );
      for (const file of written) if (file.created) console.log(`NEW ${file.path}`);

      // Record incrementally so a crash mid-batch never re-exports what
      // already succeeded (connector contract).
      ledger.identity = identity;
      ledger.threads[meta.threadId] = {
        historyId: meta.historyId,
        messageCount: meta.messageCount,
        messageIds: meta.messageIds,
        draftCount: meta.draftCount || 0,
        latestDraftAt: meta.latestDraftAt || null,
        subject: meta.subject,
        filename: meta.filename,
        mbox: path.relative(outDir, mboxPath),
        exportedAt: new Date().toISOString(),
        attachments: written.map((f) => ({ name: f.name, size: f.size })),
      };
      saveState(ctx.matterDir, 'gmail', state);
    } catch (err) {
      console.error(`FAIL (${err.message})`);
    }
  }
  return exported;
}

/**
 * Give already-exported threads the mbox they predate.
 *
 * Opt-in, because it costs one raw fetch per thread in the ledger and
 * a matter with years of correspondence has a lot of them. It renders
 * nothing and announces nothing: the PDFs it would announce are
 * already in the matter and already triaged.
 */
/** Ledger entries still owed an mbox: exported, not yet captured, not gone from Gmail. */
function pendingBackfill(ledger) {
  return Object.entries(ledger.threads).filter(
    ([, entry]) => entry && entry.filename && !entry.mbox && !entry.gone
  );
}

/** Entries whose mbox exists but whose PDF is not on disk (a repaired collision). */
function threadsNeedingPdf(ledger, outDir) {
  return Object.entries(ledger.threads).filter(
    ([, entry]) =>
      entry &&
      entry.mbox &&
      entry.filename &&
      fs.existsSync(path.join(outDir, entry.mbox)) &&
      //: an mbox with no messages (a thread that was only drafts) has
      //: nothing to render; an empty PDF would only be noise to triage.
      fs.statSync(path.join(outDir, entry.mbox)).size > 0 &&
      !fs.existsSync(path.join(outDir, entry.filename))
  );
}

const GONE_RE = /Requested entity was not found|notFound/i;

async function backfillAccount(ctx, account) {
  const { gmail, outDir, state, dryRun } = ctx;
  const key = creds.accountKey(account);
  const ledger = ledgerFor(state, key);
  const renames = repairSharedFilenames(ledger, outDir, ctx.uniqueName, { dryRun });
  for (const r of renames) {
    if (r.from !== r.to) console.error(`  [${key}] ${r.from} was also thread ${r.threadId}: now ${r.to}`);
  }
  if (renames.length && !dryRun) saveState(ctx.matterDir, 'gmail', state);
  const pending = pendingBackfill(ledger);
  const limit = ctx.limit ? Math.min(ctx.limit, pending.length) : pending.length;
  console.error(
    `[${key}] backfill: ${pending.length} thread(s) without an mbox` +
      (limit < pending.length ? `, doing ${limit} this run` : '')
  );
  if (dryRun) {
    for (const [id, entry] of pending.slice(0, limit))
      console.error(`  ${entry.filename} (${id})`);
    return 0;
  }

  let done = 0;
  await mapLimit(pending.slice(0, limit), ctx.concurrency || THREAD_CONCURRENCY, async ([threadId, entry]) => {
    try {
      const mboxPath = mboxlib.mboxPathFor(outDir, entry.filename);
      const result = await captureThread(gmail, threadId, mboxPath);
      ledger.threads[threadId] = {
        ...entry,
        mbox: path.relative(outDir, mboxPath),
        messageCount: Math.max(entry.messageCount || 0, result.total),
        messageIds: result.ids,
      };
      saveState(ctx.matterDir, 'gmail', state);
      done++;
      console.error(`  ${entry.filename} ok (${result.total} msg)`);
    } catch (err) {
      if (GONE_RE.test(String(err.message))) {
        // The thread no longer exists in the mailbox; the PDF already on
        // disk is its only record. Remember that, so it is not retried.
        ledger.threads[threadId] = { ...entry, gone: new Date().toISOString() };
        saveState(ctx.matterDir, 'gmail', state);
        console.error(`  ${entry.filename} gone from Gmail; PDF is the record`);
      } else {
        console.error(`  ${entry.filename} FAIL (${err.message})`);
      }
    }
    await sleep(BACKFILL_PAUSE_MS);
  });

  // Rendering shares one browser page and must run one at a time. A
  // thread whose PDF is not on disk (a repaired collision) gets its own
  // rendering from the mbox; that PDF is new to the matter, so it is
  // announced.
  for (const [threadId, entry] of threadsNeedingPdf(ledger, outDir)) {
    const mboxPath = path.join(outDir, entry.mbox);
    const pdfPath = path.join(outDir, entry.filename);
    try {
      const messages = render.loadThread(mboxPath);
      await render.renderMboxToPdf(mboxPath, pdfPath, {
        messages,
        subject: render.threadSubject(messages),
        account: ledger.identity || key,
        quoted: ctx.quoted,
        tmpDir: ctx.tmpDir,
      });
      console.log(`NEW ${pdfPath}`);
      const written = render.extractAttachments(messages, render.attachmentsDirFor(mboxPath), {});
      for (const file of written) if (file.created) console.log(`NEW ${file.path}`);
      ledger.threads[threadId].exportedAt = new Date().toISOString();
      saveState(ctx.matterDir, 'gmail', state);
      console.error(`  ${entry.filename} rendered`);
    } catch (err) {
      console.error(`  ${entry.filename} RENDER FAIL (${err.message})`);
    }
  }
  return done;
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');
  const force = process.argv.includes('--force');
  const backfill = process.argv.includes('--backfill-mbox');
  const onlyAccount = flagValue('--account', null);
  const concurrency = Number(flagValue('--concurrency', 0)) || 0;
  const full = process.argv.includes('--full');
  const limit = Number(flagValue('--limit', 0)) || 0;

  const matterDir = positionalArgs()[0] || process.cwd();
  const cfg = connectorConfig(matterDir, 'gmail');
  if (!cfg || !cfg.addresses || !cfg.addresses.length) {
    console.error('gmail connector not configured (needs addresses); nothing to do');
    return;
  }

  const outDir = path.resolve(matterDir, cfg.out_dir || 'assets/gmail');
  fs.mkdirSync(outDir, { recursive: true });

  const configured = creds.configuredAccounts(cfg);
  // The primary is the first CONFIGURED account, not the first one this
  // run happens to touch: --account must not promote a second mailbox
  // into the primary's fallback to the pre-accounts token.
  const primaryKey = creds.accountKey(configured[0]);
  let accounts = configured;
  if (onlyAccount) {
    accounts = accounts.filter(
      (a) => a && a.toLowerCase() === onlyAccount.toLowerCase()
    );
    if (!accounts.length) {
      console.error(`--account ${onlyAccount} is not in connectors.gmail.accounts`);
      process.exit(1);
    }
  }

  const state = loadLedger(matterDir, primaryKey);
  const claimed = claimedFilenames(state, outDir);
  const ctx = {
    matterDir,
    cfg,
    outDir,
    state,
    dryRun,
    force,
    limit,
    quoted: cfg.quoted || render.DEFAULT_QUOTED_MODE,
    tmpDir: fs.mkdtempSync(path.join(os.tmpdir(), 'gmail-')),
    uniqueName(base) {
      let name = base;
      if (claimed.has(name)) {
        const stem = base.replace(/\.pdf$/, '');
        let i = 2;
        while (claimed.has(`${stem}_${i}.pdf`)) i++;
        name = `${stem}_${i}.pdf`;
      }
      claimed.add(name);
      return name;
    },
    concurrency,
    full,
  };

  if (!render.QUOTED_MODES.includes(ctx.quoted)) {
    console.error(
      `connectors.gmail.quoted must be one of ${render.QUOTED_MODES.join('|')}`
    );
    process.exit(1);
  }

  let total = 0;
  try {
    for (const account of accounts) {
      const auth = creds.loadOAuthClient(account, {
        primary: creds.accountKey(account) === primaryKey,
      });
      const gmail = google.gmail({ version: 'v1', auth });
      const accountCtx = { ...ctx, gmail };
      total += backfill
        ? await backfillAccount(accountCtx, account)
        : await pullAccount(accountCtx, account);
    }
  } finally {
    fs.rmSync(ctx.tmpDir, { recursive: true, force: true });
    await render.closeBrowser();
  }

  console.error(
    backfill
      ? `\nDone. ${total} thread(s) backfilled under ${outDir}`
      : `\nDone. ${total} thread(s) exported to ${outDir}`
  );
}

module.exports = {
  captureThread,
  threadChanged,
  isNotDraft,
  mapLimit,
  filenameClaimedByAnother,
  repairSharedFilenames,
  pendingBackfill,
  threadsNeedingPdf,
  listingQuery,
  listingPlan,
  searchThreads,
  snakeCase,
  addressClause,
  addressDisplay,
  positionalArgs,
  loadLedger,
  ledgerFor,
  claimedFilenames,
  fetchThreadMeta,
  entryCurrent,
  parseAddresses,
  canonicalAddress,
  addressCovered,
  isNoiseAddress,
  collectUnlisted,
  mergeUnlisted,
};

if (require.main === module) {
  main().catch((err) => {
    console.error('Fatal:', err.message);
    process.exit(1);
  });
}
