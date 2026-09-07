// mbox.js — the gmail connector's storage layer: raw messages in mboxrd.
//
// One mbox per thread, at <matter>/assets/gmail/mbox/<pdf stem>.mbox.
// The bytes inside are exactly what the Gmail API returned for
// `format=raw` — the RFC 822 message as it was transmitted, headers,
// MIME structure, attachments and all — wrapped in the mbox envelope
// and nothing more. See ADR-0038 for why the raw message, rather than
// the rendered PDF, is the record.
//
// mboxrd, not mboxo or mboxcl2. The mbox family differs only in how it
// keeps a body line that begins "From " from being mistaken for the
// next message's separator. mboxrd prefixes ">" to any line matching
// /^>*From /, which is the only variant that is losslessly reversible:
// ">From " unquotes to "From ", ">>From " to ">From ", and a message
// that never contained such a line is stored byte-identical. mboxo
// (quote "From " only) cannot tell an original ">From " from a quoted
// one, and mboxcl2 needs a Content-Length header that a text editor or
// a partial write silently invalidates.
//
// Append-only. A thread that grows gets its new messages appended; the
// bytes already written are never rewritten, so an mbox that has been
// backed up or hashed stays valid as a prefix of its successor.

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const { parseHeaders, headerValue } = require('./mime');

//: Directory under the connector's out_dir that holds the mboxes.
const MBOX_DIR_NAME = 'mbox';
const MBOX_EXTENSION = '.mbox';

//: The envelope sender written into a From_ line when a message has no
//: parsable From address. The traditional mbox placeholder.
const UNKNOWN_SENDER = 'MAILER-DAEMON';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/** The mbox path for a thread whose PDF is named `<stem>.pdf`. */
function mboxPathFor(outDir, pdfFilename) {
  const stem = pdfFilename.replace(/\.pdf$/i, '');
  return path.join(outDir, MBOX_DIR_NAME, stem + MBOX_EXTENSION);
}

// --- the mboxrd envelope ---------------------------------------------

/** Prefix ">" to every line that could be read as a From_ separator. */
function escapeBody(text) {
  return text.replace(/^(>*From )/gm, '>$1');
}

/** The exact inverse of escapeBody. */
function unescapeBody(text) {
  return text.replace(/^>(>*From )/gm, '$1');
}

// asctime in UTC: "Thu Jan  1 00:00:00 2026". UTC rather than local
// time so that the same message stored on two machines produces the
// same bytes — a stored record whose contents depend on the reader's
// timezone is not a record.
function asctimeUTC(date) {
  const d = isNaN(date && date.getTime()) ? new Date(0) : date;
  const pad = (n) => String(n).padStart(2, '0');
  return (
    `${DAYS[d.getUTCDay()]} ${MONTHS[d.getUTCMonth()]} ` +
    `${String(d.getUTCDate()).padStart(2, ' ')} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} ` +
    `${d.getUTCFullYear()}`
  );
}

/** "jane@example.com" out of "Jane Roe <jane@example.com>". */
function envelopeSender(fromHeader) {
  if (!fromHeader) return UNKNOWN_SENDER;
  const angled = fromHeader.match(/<([^>]+)>/);
  const bare = (angled ? angled[1] : fromHeader).trim().split(/\s+/).pop();
  return bare && bare.includes('@') ? bare : UNKNOWN_SENDER;
}

function headersOf(raw) {
  const text = raw.toString('binary');
  const end = /\r?\n\r?\n/.exec(text);
  return parseHeaders(end ? text.slice(0, end.index) : text);
}

/**
 * The dedup key for one raw message.
 *
 * Message-ID is the identifier the sender assigned and the one that
 * survives being re-fetched, re-labelled, or pulled from a second
 * mailbox, so it is the primary key. A message without one (rare, and
 * always malformed) falls back to a digest of its own bytes, which
 * dedups an identical re-fetch and nothing else — the honest limit.
 */
function messageKey(raw) {
  const id = headerValue(headersOf(raw), 'message-id');
  if (id) return id.trim().toLowerCase();
  return 'sha256:' + crypto.createHash('sha256').update(raw).digest('hex');
}

function messageDate(raw) {
  const value = headerValue(headersOf(raw), 'date');
  const parsed = value ? new Date(value) : null;
  return parsed && !isNaN(parsed.getTime()) ? parsed : null;
}

// --- reading ----------------------------------------------------------

/**
 * Every message in an mbox, as the raw bytes that were appended.
 *
 * Splits on a From_ line at the start of a line and reverses the mboxrd
 * quoting, so `readMessages(f)[i]` is byte-identical to the buffer that
 * `appendMessages` was given.
 */
function readMessages(mboxPath) {
  if (!fs.existsSync(mboxPath)) return [];
  return splitMbox(fs.readFileSync(mboxPath).toString('binary')).map((body) =>
    Buffer.from(unescapeBody(body), 'binary')
  );
}

//: A From_ separator: the literal "From ", a non-space envelope
//: sender, and the rest of the line — recognized only at the start of
//: a line, which is what the ">From " quoting exists to guarantee.
const FROM_LINE = /(^|\n)From \S[^\n]*\n/g;

/** The still-escaped body region of each message in an mbox's text. */
function splitMbox(text) {
  const marks = [];
  FROM_LINE.lastIndex = 0;
  let match;
  while ((match = FROM_LINE.exec(text)) !== null) {
    marks.push({
      lineStart: match.index + match[1].length,
      bodyStart: match.index + match[0].length,
    });
    FROM_LINE.lastIndex = match.index + match[0].length;
  }
  return marks.map((mark, i) => {
    const end = i + 1 < marks.length ? marks[i + 1].lineStart : text.length;
    const region = text.slice(mark.bodyStart, end);
    // appendMessages writes exactly "\n\n" after each message: one to
    // end its last line, one for the blank line mbox readers expect
    // before the next From_. Both belong to the envelope.
    if (region.endsWith('\n\n')) return region.slice(0, -2);
    if (region.endsWith('\n')) return region.slice(0, -1);
    return region;
  });
}

/** The dedup keys already stored in an mbox. */
function storedKeys(mboxPath) {
  return new Set(readMessages(mboxPath).map(messageKey));
}

// --- writing ----------------------------------------------------------

/**
 * Append raw messages to a thread's mbox, skipping ones already there.
 *
 * `messages` is [{raw: Buffer, id}] where `id` is the Gmail message id
 * (recorded by the caller in the ledger; never written into the file,
 * because the stored bytes are the message and nothing else). Returns
 * {added, skipped, keys} — `added` being the ids actually written, so
 * the caller can tell a grown thread from an unchanged one.
 */
function appendMessages(mboxPath, messages) {
  fs.mkdirSync(path.dirname(mboxPath), { recursive: true });
  const seen = storedKeys(mboxPath);
  const added = [];
  const skipped = [];
  let chunk = '';
  for (const message of messages) {
    const raw = Buffer.isBuffer(message.raw)
      ? message.raw
      : Buffer.from(String(message.raw), 'binary');
    const key = messageKey(raw);
    if (seen.has(key)) {
      skipped.push(message.id);
      continue;
    }
    seen.add(key);
    const date = messageDate(raw) || (message.internalDate
      ? new Date(Number(message.internalDate))
      : new Date(0));
    const from = envelopeSender(headerValue(headersOf(raw), 'from'));
    chunk +=
      `From ${from} ${asctimeUTC(date)}\n` +
      escapeBody(raw.toString('binary')) +
      '\n\n';
    added.push(message.id);
  }
  if (chunk) fs.appendFileSync(mboxPath, Buffer.from(chunk, 'binary'));
  return { added, skipped, keys: [...seen] };
}

module.exports = {
  MBOX_DIR_NAME,
  MBOX_EXTENSION,
  mboxPathFor,
  escapeBody,
  unescapeBody,
  asctimeUTC,
  envelopeSender,
  messageKey,
  messageDate,
  readMessages,
  splitMbox,
  storedKeys,
  appendMessages,
};
