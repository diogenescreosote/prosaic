// mime.js — a small RFC 822 / MIME reader for stored mail.
//
// The gmail connector's canonical record is raw RFC 822 bytes in an
// mbox (ADR-0038), so everything downstream — the print view, the
// attachment extractor, the .eml emitter — reads a message by parsing
// those bytes rather than by asking the Gmail API for a pre-chewed
// `payload` tree. This module is that parser.
//
// It is deliberately dependency-free. The connectors' package.json
// buys puppeteer, cheerio and googleapis; adding a mail-parsing
// library for the handful of grammar this needs would put a fourth
// upgrade treadmill under the one part of the system that must still
// read a 2015 message in 2035. What is implemented here is the part of
// RFC 2045/2046/2047/2231 that real mail actually uses:
//
//   - header unfolding and repeated headers
//   - Content-Type / Content-Disposition parameters, including the
//     RFC 2231 continuation + charset forms mailers use for long or
//     non-ASCII filenames
//   - encoded-words (=?utf-8?B?...?=) in any header value
//   - base64 and quoted-printable transfer decoding
//   - multipart/* recursion on the boundary parameter
//
// Anything it does not understand degrades to "a leaf part with these
// raw bytes", which is the honest answer and never loses content.

'use strict';

const DEFAULT_MIME_TYPE = 'text/plain';
const DEFAULT_CHARSET = 'utf-8';

// Where a header block ends: the first empty line, either line ending.
const HEADER_BODY_SPLIT = /\r?\n\r?\n/;

function splitHeadersAndBody(buf) {
  const text = buf.toString('binary'); // byte-preserving; charset comes later
  const m = HEADER_BODY_SPLIT.exec(text);
  if (!m) return { headerText: text, body: Buffer.alloc(0) };
  const headerText = text.slice(0, m.index);
  const body = Buffer.from(text.slice(m.index + m[0].length), 'binary');
  return { headerText, body };
}

// Unfold (RFC 5322 §2.2.3) and split into ordered {name, value} pairs.
// Repeated headers are kept in order; getHeader returns the first.
function parseHeaders(headerText) {
  const headers = [];
  let current = null;
  for (const line of headerText.split(/\r?\n/)) {
    if (/^[ \t]/.test(line) && current) {
      current.value += ' ' + line.trim();
      continue;
    }
    const idx = line.indexOf(':');
    if (idx <= 0) continue;
    current = { name: line.slice(0, idx).trim(), value: line.slice(idx + 1).trim() };
    headers.push(current);
  }
  return headers;
}

function headerValue(headers, name) {
  const lower = name.toLowerCase();
  const hit = headers.find((h) => h.name.toLowerCase() === lower);
  return hit ? hit.value : undefined;
}

// --- RFC 2047 encoded-words ------------------------------------------

const ENCODED_WORD = /=\?([^?]+)\?([BbQq])\?([^?]*)\?=/g;

function decodeCharset(buf, charset) {
  const label = (charset || DEFAULT_CHARSET).toLowerCase().replace(/^["']|["']$/g, '');
  try {
    return new TextDecoder(label, { fatal: false }).decode(buf);
  } catch {
    return buf.toString('utf-8');
  }
}

function decodeQuotedPrintable(text, { underscoreIsSpace = false } = {}) {
  let s = text.replace(/=\r?\n/g, '');
  if (underscoreIsSpace) s = s.replace(/_/g, ' ');
  const out = [];
  for (let i = 0; i < s.length; i++) {
    if (s[i] === '=' && /^[0-9A-Fa-f]{2}$/.test(s.slice(i + 1, i + 3))) {
      out.push(parseInt(s.slice(i + 1, i + 3), 16));
      i += 2;
    } else {
      out.push(s.charCodeAt(i) & 0xff);
    }
  }
  return Buffer.from(out);
}

// "=?utf-8?Q?Fran=C3=A7ois?= <jane@example.com>" -> "François <jane@example.com>"
function decodeWords(value) {
  if (!value || value.indexOf('=?') === -1) return value || '';
  return value.replace(ENCODED_WORD, (whole, charset, enc, payload) => {
    try {
      const bytes =
        enc.toUpperCase() === 'B'
          ? Buffer.from(payload, 'base64')
          : decodeQuotedPrintable(payload, { underscoreIsSpace: true });
      return decodeCharset(bytes, charset);
    } catch {
      return whole;
    }
  });
}

// --- structured header values ----------------------------------------

// "multipart/mixed; boundary=\"abc\"" -> {value, params:{boundary:'abc'}}
// Handles RFC 2231: name*0="a"; name*1="b"  and  name*=utf-8''a%20b
function parseParameterized(raw) {
  if (!raw) return { value: '', params: {} };
  const segments = splitOnUnquoted(raw, ';');
  const value = (segments.shift() || '').trim().toLowerCase();
  const continued = {};
  const params = {};
  for (const seg of segments) {
    const eq = seg.indexOf('=');
    if (eq === -1) continue;
    let key = seg.slice(0, eq).trim().toLowerCase();
    let val = seg.slice(eq + 1).trim().replace(/^"|"$/g, '');
    const extended = key.endsWith('*');
    if (extended) key = key.slice(0, -1);
    const cont = key.match(/^(.*)\*(\d+)$/);
    if (cont) {
      const [, base, index] = cont;
      (continued[base] = continued[base] || [])[Number(index)] = { val, extended };
      continue;
    }
    params[key] = extended ? decodeExtendedParameter(val) : val;
  }
  for (const [base, pieces] of Object.entries(continued)) {
    let charset = null;
    let text = '';
    for (const piece of pieces) {
      if (!piece) continue;
      if (piece.extended) {
        const m = piece.val.match(/^([^']*)'([^']*)'(.*)$/);
        if (m) {
          charset = charset || m[1];
          text += m[3];
        } else {
          text += piece.val;
        }
      } else {
        text += piece.val;
      }
    }
    const encoded = Boolean(charset) || /%[0-9A-Fa-f]{2}/.test(text);
    params[base] = encoded ? percentDecode(text, charset) : text;
  }
  return { value, params };
}

function decodeExtendedParameter(val) {
  const m = val.match(/^([^']*)'([^']*)'(.*)$/);
  return m ? percentDecode(m[3], m[1]) : percentDecode(val, null);
}

function percentDecode(text, charset) {
  const bytes = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '%' && /^[0-9A-Fa-f]{2}$/.test(text.slice(i + 1, i + 3))) {
      bytes.push(parseInt(text.slice(i + 1, i + 3), 16));
      i += 2;
    } else {
      bytes.push(text.charCodeAt(i) & 0xff);
    }
  }
  return decodeCharset(Buffer.from(bytes), charset || DEFAULT_CHARSET);
}

function splitOnUnquoted(text, sep) {
  const out = [];
  let buf = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') quoted = !quoted;
    if (c === sep && !quoted) {
      out.push(buf);
      buf = '';
      continue;
    }
    buf += c;
  }
  out.push(buf);
  return out;
}

// --- transfer decoding ------------------------------------------------

function decodeTransfer(body, encoding) {
  const enc = (encoding || '7bit').trim().toLowerCase();
  if (enc === 'base64') {
    return Buffer.from(body.toString('binary').replace(/[^A-Za-z0-9+/=]/g, ''), 'base64');
  }
  if (enc === 'quoted-printable') {
    return decodeQuotedPrintable(body.toString('binary'));
  }
  return body;
}

// --- the tree ---------------------------------------------------------

/**
 * Parse one RFC 822 message into a part tree.
 *
 * Every node carries: headers[], getHeader(), mimeType, charset,
 * filename, contentId, disposition, size (decoded bytes), content
 * (decoded Buffer, leaves only), raw (the node's undecoded body), and
 * parts[] for multipart nodes.
 */
function parseMessage(buf) {
  const source = Buffer.isBuffer(buf) ? buf : Buffer.from(String(buf), 'utf-8');
  const { headerText, body } = splitHeadersAndBody(source);
  return buildNode(parseHeaders(headerText), body, source);
}

function buildNode(headers, body, raw) {
  const ct = parseParameterized(headerValue(headers, 'content-type') || DEFAULT_MIME_TYPE);
  const cd = parseParameterized(headerValue(headers, 'content-disposition') || '');
  const cidHeader = headerValue(headers, 'content-id');
  const filename = decodeWords(cd.params.filename || ct.params.name || '') || null;

  const node = {
    headers,
    raw,
    mimeType: ct.value || DEFAULT_MIME_TYPE,
    charset: ct.params.charset || DEFAULT_CHARSET,
    boundary: ct.params.boundary || null,
    disposition: cd.value || null,
    filename,
    contentId: cidHeader ? cidHeader.trim().replace(/^<|>$/g, '') : null,
    encoding: headerValue(headers, 'content-transfer-encoding') || null,
    parts: [],
    content: null,
    size: 0,
    getHeader(name) {
      return headerValue(this.headers, name);
    },
    header(name) {
      return decodeWords(headerValue(this.headers, name) || '');
    },
  };

  if (node.mimeType.startsWith('multipart/') && node.boundary) {
    node.parts = splitMultipart(body, node.boundary).map((chunk) => {
      const split = splitHeadersAndBody(chunk);
      return buildNode(parseHeaders(split.headerText), split.body, chunk);
    });
    return node;
  }

  node.content = decodeTransfer(body, node.encoding);
  node.size = node.content.length;
  return node;
}

// Split a multipart body on its boundary. Line-based rather than
// index-based: a boundary only counts at the start of a line, the RFC
// allows transport padding after it, and rejoining the kept lines with
// "\n" preserves each line's own terminator byte-for-byte. The CRLF
// immediately before a delimiter belongs to the delimiter, so it is
// dropped from the part it follows.
function splitMultipart(body, boundary) {
  const text = body.toString('binary');
  const delimiter = '--' + boundary;
  const chunks = [];
  let current = null;
  for (const line of text.split('\n')) {
    const trimmed = line.replace(/[ \t\r]+$/, '');
    if (trimmed === delimiter) {
      if (current) chunks.push(current);
      current = [];
      continue;
    }
    if (trimmed === delimiter + '--') {
      if (current) chunks.push(current);
      current = null;
      break;
    }
    if (current) current.push(line);
  }
  if (current) chunks.push(current);
  return chunks.map((lines) =>
    Buffer.from(lines.join('\n').replace(/\r$/, ''), 'binary')
  );
}

/** Depth-first walk over a part tree, root included. */
function walk(node, visit) {
  if (!node) return;
  visit(node);
  for (const part of node.parts) walk(part, visit);
}

/** Decoded text of a leaf, honoring its charset. */
function partText(node) {
  return node && node.content ? decodeCharset(node.content, node.charset) : '';
}

/**
 * The body a reader is meant to see: the richest alternative available.
 *
 * multipart/alternative offers the same content twice; the last part is
 * the richest by RFC 2046, and in practice that is the HTML. Anything
 * with a filename is an attachment and is never a body, however its
 * mime type reads.
 */
function findBody(node) {
  let text = '';
  let html = '';
  walk(node, (part) => {
    if (part.parts.length || part.filename) return;
    if (!html && part.mimeType === 'text/html') html = partText(part);
    else if (!text && part.mimeType === 'text/plain') text = partText(part);
  });
  return { text, html };
}

/** Every part carrying a Content-ID, keyed by that id (inline images). */
function inlineParts(node) {
  const byCid = {};
  walk(node, (part) => {
    if (part.contentId && !part.parts.length) byCid[part.contentId] = part;
  });
  return byCid;
}

/**
 * The parts a reader would call attachments.
 *
 * A part is an attachment when it has a filename and its bytes did not
 * land in the rendered body. Judging by Content-ID or an inline
 * disposition alone loses real documents: mailers stamp both onto
 * genuine attachments, and a header-based rule silently drops them. So
 * the caller passes the set of content-ids the renderer actually
 * embedded, and everything else with a filename is an attachment.
 */
function attachmentParts(node, embeddedCids) {
  const found = [];
  walk(node, (part) => {
    if (part.parts.length || !part.filename || !part.size) return;
    if (part.contentId && embeddedCids && embeddedCids.has(part.contentId)) return;
    found.push(part);
  });
  return found;
}

module.exports = {
  parseMessage,
  parseHeaders,
  headerValue,
  parseParameterized,
  decodeWords,
  decodeCharset,
  decodeQuotedPrintable,
  decodeTransfer,
  walk,
  partText,
  findBody,
  inlineParts,
  attachmentParts,
};
