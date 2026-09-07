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
  const msgs = (res.data.messages || []).filter(isNotDraft);
  if (msgs.length === 0) return null;
  const firstMsg = msgs[0];
  const subject = getHeader(firstMsg.payload.headers, 'Subject') || 'no_subject';
  const dateStr = getHeader(firstMsg.payload.headers, 'Date');
  const date = dateStr ? new Date(dateStr) : new Date();
  const yyyymmdd = date.toISOString().slice(0, 10).replace(/-/g, '');
  return {
    threadId: t.id,
    historyId: t.historyId,
    subject,
    messageCount: msgs.length,
    messageIds: msgs.map((m) => m.id),
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
  const unchanged = (t) => {
    const prev = ledger.threads[t.id];
    return (
      !force &&
      prev &&
      prev.historyId != null &&
      t.historyId != null &&
      String(prev.historyId) === String(t.historyId)
    );
  };
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
        };
        if (!dryRun) saveState(ctx.matterDir, 'gmail', state);
      }
      continue;
    }

    // New to the ledger. If a matching export already sits on disk from
    // a pre-ledger pull, absorb it without re-triaging. It has no mbox;
    // --backfill-mbox is how it gets one.
    if (!force && existingFiles.has(meta.defaultFilename)) {
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
async function backfillAccount(ctx, account) {
  const { gmail, outDir, state, dryRun } = ctx;
  const key = creds.accountKey(account);
  const ledger = ledgerFor(state, key);
  const pending = Object.entries(ledger.threads).filter(
    ([, entry]) => entry && entry.filename && !entry.mbox
  );
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
      console.error(`  ${entry.filename} FAIL (${err.message})`);
    }
    await sleep(BACKFILL_PAUSE_MS);
  });
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
};

if (require.main === module) {
  main().catch((err) => {
    console.error('Fatal:', err.message);
    process.exit(1);
  });
}
