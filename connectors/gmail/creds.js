// creds.js — where the gmail connector's OAuth material lives.
//
// One person can have more than one mailbox, and evidence does not
// care which one a message landed in: a notice sent from a second
// account is as much a part of the record as one sent from the first.
// So the connector authorizes per account, and this module is the
// single place that knows how an account's name becomes a token path.
//
//   $PROSAIC_GMAIL_CREDS_DIR/              (default ~/.config/prosaic/gmail)
//     oauth-keys.json                      the OAuth client (shared)
//     credentials.json                     the single-mailbox token
//     credentials-<account slug>.json      one token per configured account
//
// Backward compatibility, deliberately: a matter with no `accounts:`
// key uses credentials.json exactly as before, and the FIRST account
// in an `accounts:` list falls back to credentials.json when it has no
// token of its own. Adding a second mailbox therefore costs one
// authorization, not two, and never invalidates the first.
//
// A token file is written in exactly two places, both here: auth.js
// after consent (saveAuthorized) and the OAuth client's 'tokens' event
// after a refresh (loadOAuthClient). Both MERGE into the file as it is
// on disk at that moment, never into a snapshot taken when the run
// began, and a refresh_token is never dropped: Google sends one only
// at consent, so a file that loses it stops working when the access
// token expires an hour later and every pull fails with invalid_grant
// until someone re-authorizes. Writes are atomic (temp file, rename)
// and private (0600).
//
// Each file records the mailbox it authorizes (`account`, written by
// auth.js after it checks the profile, or by the first pull that reads
// the profile). The primary account's own file and credentials.json are
// two names for one mailbox's token, so they are kept in step: a
// refresh is written to both, unless credentials.json is recorded as a
// different mailbox or holds a separate grant of its own.

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const CREDS_DIR =
  process.env.PROSAIC_GMAIL_CREDS_DIR ||
  path.join(os.homedir(), '.config/prosaic/gmail');
const OAUTH_KEYS_PATH = path.join(CREDS_DIR, 'oauth-keys.json');
const LEGACY_TOKEN_PATH = path.join(CREDS_DIR, 'credentials.json');

const GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly'];

//: The ledger key and token-filename stem for an unconfigured
//: (single-mailbox) matter — the shape every matter had before
//: `accounts:` existed.
const DEFAULT_ACCOUNT_KEY = 'default';

/** "Jane.Roe+mail@example.com" -> "jane_roe_mail_example_com". */
function accountSlug(account) {
  return String(account)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

//: Fields of a token file that are ours, not the OAuth library's.
const ACCOUNT_FIELD = 'account';

function ownTokenPath(account) {
  return path.join(CREDS_DIR, `credentials-${accountSlug(account)}.json`);
}

/** A token file's contents, or null when absent or unreadable. */
function readToken(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf-8'));
  } catch {
    return null;
  }
}

function writeToken(file, data) {
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data), { mode: 0o600 });
  fs.renameSync(tmp, file);
}

function sameAccount(a, b) {
  return !!a && !!b && String(a).toLowerCase() === String(b).toLowerCase();
}

/**
 * Merge new tokens into a token file's current contents. Empty values
 * never overwrite, and a refresh_token present in either the file or
 * the caller's copy survives unless `tokens` brings a new one.
 */
function mergeTokens(onDisk, inMemory, tokens) {
  const out = { ...(inMemory || {}), ...(onDisk || {}) };
  for (const [k, v] of Object.entries(tokens || {})) {
    if (v !== undefined && v !== null && v !== '') out[k] = v;
  }
  if (!out.refresh_token) {
    const kept = (onDisk && onDisk.refresh_token) || (inMemory && inMemory.refresh_token);
    if (kept) out.refresh_token = kept;
  }
  return out;
}

/**
 * Write tokens into a file without losing what is there. A file whose
 * refresh_token differs from the one this process holds was
 * re-authorized after the process read it (or is a separate grant);
 * a refresh carrying no new refresh_token leaves it alone.
 */
function saveTokens(file, inMemory, tokens) {
  const onDisk = readToken(file);
  const held = inMemory && inMemory.refresh_token;
  if (onDisk && onDisk.refresh_token && held && onDisk.refresh_token !== held && !(tokens && tokens.refresh_token)) {
    return false;
  }
  writeToken(file, mergeTokens(onDisk, inMemory, tokens));
  return true;
}

/**
 * Is credentials.json the primary account's token too? Yes unless it
 * is recorded as another mailbox: the pre-accounts token is by
 * definition the first configured account's (the same fact pull.js's
 * loadLedger relies on to migrate a single-mailbox ledger).
 */
function legacyIsAlias(account) {
  const legacy = readToken(LEGACY_TOKEN_PATH);
  return !!legacy && (!legacy[ACCOUNT_FIELD] || sameAccount(legacy[ACCOUNT_FIELD], account));
}

/**
 * The token file for one account.
 *
 * `primary` marks the first configured account, which inherits the
 * pre-accounts token if it has not been authorized under its own name,
 * or if its own file has lost its refresh_token and credentials.json
 * still has one.
 */
function tokenPath(account, { primary = false } = {}) {
  if (!account) return LEGACY_TOKEN_PATH;
  const own = ownTokenPath(account);
  if (!primary || !fs.existsSync(LEGACY_TOKEN_PATH) || !legacyIsAlias(account)) return own;
  if (!fs.existsSync(own)) return LEGACY_TOKEN_PATH;
  const ownToken = readToken(own);
  const legacyToken = readToken(LEGACY_TOKEN_PATH);
  if (!(ownToken && ownToken.refresh_token) && legacyToken && legacyToken.refresh_token) {
    return LEGACY_TOKEN_PATH;
  }
  return own;
}

/** Every file that names this account's token: the one in use, then its alias. */
function tokenFiles(account, options = {}) {
  const used = options.credentialsPath || tokenPath(account, options);
  const files = [used];
  if (account && options.primary && legacyIsAlias(account)) {
    const alias = used === LEGACY_TOKEN_PATH ? ownTokenPath(account) : LEGACY_TOKEN_PATH;
    if (fs.existsSync(alias)) files.push(alias);
  }
  return files;
}

/**
 * Record which mailbox a token file authorizes, once known (a pull
 * reads the profile anyway). Only fills a missing field; never
 * rewrites one.
 */
function recordAccount(file, email) {
  const t = readToken(file);
  if (!t || !email || t[ACCOUNT_FIELD]) return false;
  writeToken(file, { ...t, [ACCOUNT_FIELD]: email });
  return true;
}

/**
 * Save the token auth.js obtained. Merged into the destination when it
 * already authorizes the same mailbox, so a consent that returns no
 * new refresh_token keeps the old one; copied to the per-account file
 * of the same mailbox (or to credentials.json, when it is recorded as
 * that mailbox) so the two never disagree.
 */
function saveAuthorized(destination, credentials, email) {
  const prior = readToken(destination);
  const base = prior && sameAccount(prior[ACCOUNT_FIELD], email) ? prior : null;
  const saved = mergeTokens(base, null, { ...credentials, [ACCOUNT_FIELD]: email });
  writeToken(destination, saved);
  const written = [destination];
  const alias =
    destination === LEGACY_TOKEN_PATH
      ? ownTokenPath(email)
      : sameAccount((readToken(LEGACY_TOKEN_PATH) || {})[ACCOUNT_FIELD], email)
        ? LEGACY_TOKEN_PATH
        : null;
  if (alias && fs.existsSync(alias)) {
    writeToken(alias, mergeTokens(readToken(alias), null, saved));
    written.push(alias);
  }
  return written;
}

/**
 * An authorized OAuth2 client for one account.
 *
 * Refreshed tokens are merged back into the file they came from (and
 * its alias), so a long-lived matter keeps working without re-consent.
 * `auth.prosaicTokenPath` names the file in use.
 */
function loadOAuthClient(account, options = {}) {
  const { google } = require('googleapis');
  const files = tokenFiles(account, options);
  const credentialsPath = files[0];
  if (!fs.existsSync(OAUTH_KEYS_PATH)) {
    throw new Error(`missing OAuth client keys at ${OAUTH_KEYS_PATH}`);
  }
  if (!fs.existsSync(credentialsPath)) {
    throw new Error(
      `no token at ${credentialsPath} — run: node auth.js` +
        (account ? ` --account ${account}` : '')
    );
  }
  const oauthKeys = JSON.parse(fs.readFileSync(OAUTH_KEYS_PATH, 'utf-8'));
  const stored = JSON.parse(fs.readFileSync(credentialsPath, 'utf-8'));
  if (!stored.refresh_token) {
    console.error(
      `warning: ${credentialsPath} has no refresh_token; it stops working when the ` +
        'access token expires. Re-run: node auth.js' + (account ? ` --account ${account}` : '')
    );
  }
  const key = oauthKeys.web || oauthKeys.installed;
  const auth = new google.auth.OAuth2(
    key.client_id,
    key.client_secret,
    key.redirect_uris[0]
  );
  const { [ACCOUNT_FIELD]: _account, ...creds } = stored;
  auth.setCredentials(creds);
  auth.on('tokens', (tokens) => {
    try {
      for (const file of files) saveTokens(file, stored, tokens);
    } catch (err) {
      console.error(`warning: could not save the refreshed token: ${err.message}`);
    }
  });
  auth.prosaicTokenPath = credentialsPath;
  return auth;
}

/**
 * The accounts a matter's gmail config names, in order.
 *
 * `[null]` — one unnamed mailbox — when `accounts:` is absent, which
 * is how every matter written before this key behaves.
 */
function configuredAccounts(cfg) {
  const listed = cfg && cfg.accounts;
  if (!Array.isArray(listed) || !listed.length) return [null];
  return listed.map((entry) =>
    typeof entry === 'string' ? entry : entry && entry.address
  ).filter(Boolean);
}

/** The ledger key for an account: its address, or "default". */
function accountKey(account) {
  return account ? String(account).toLowerCase() : DEFAULT_ACCOUNT_KEY;
}

module.exports = {
  CREDS_DIR,
  OAUTH_KEYS_PATH,
  LEGACY_TOKEN_PATH,
  GMAIL_SCOPES,
  DEFAULT_ACCOUNT_KEY,
  accountSlug,
  tokenPath,
  tokenFiles,
  readToken,
  mergeTokens,
  saveTokens,
  saveAuthorized,
  recordAccount,
  loadOAuthClient,
  configuredAccounts,
  accountKey,
};
