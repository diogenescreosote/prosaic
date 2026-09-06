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

/**
 * The token file for one account.
 *
 * `primary` marks the first configured account, which inherits the
 * pre-accounts token if it has not been authorized under its own name.
 */
function tokenPath(account, { primary = false } = {}) {
  if (!account) return LEGACY_TOKEN_PATH;
  const own = path.join(CREDS_DIR, `credentials-${accountSlug(account)}.json`);
  if (primary && !fs.existsSync(own) && fs.existsSync(LEGACY_TOKEN_PATH)) {
    return LEGACY_TOKEN_PATH;
  }
  return own;
}

/**
 * An authorized OAuth2 client for one account.
 *
 * Refreshed tokens are written back to the same file they came from,
 * so a long-lived matter keeps working without re-consent.
 */
function loadOAuthClient(account, options = {}) {
  const { google } = require('googleapis');
  const credentialsPath = options.credentialsPath || tokenPath(account, options);
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
  const creds = JSON.parse(fs.readFileSync(credentialsPath, 'utf-8'));
  const key = oauthKeys.web || oauthKeys.installed;
  const auth = new google.auth.OAuth2(
    key.client_id,
    key.client_secret,
    key.redirect_uris[0]
  );
  auth.setCredentials(creds);
  auth.on('tokens', (tokens) => {
    fs.writeFileSync(credentialsPath, JSON.stringify({ ...creds, ...tokens }));
  });
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
  loadOAuthClient,
  configuredAccounts,
  accountKey,
};
