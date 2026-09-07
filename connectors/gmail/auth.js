#!/usr/bin/env node
// gmail connector — one-time OAuth authorization, per mailbox.
//
// Usage: node auth.js [--account <email>]
//
// Prereq: create a Google Cloud OAuth client (Desktop app) with the
// Gmail API enabled, download the client-secret JSON, and save it as
//   $PROSAIC_GMAIL_CREDS_DIR/oauth-keys.json
//   (default ~/.config/prosaic/gmail/oauth-keys.json)
// This script opens a browser consent flow and stores the resulting
// token beside it: credentials.json without --account, or
// credentials-<account slug>.json with one. Re-run it whenever pulls
// start failing with invalid_grant (Google revoked/expired the token).
//
// --account is how a matter that watches two mailboxes authorizes the
// second. Pass the same address that appears in the matter's
// connectors.gmail.accounts list; the script verifies that the mailbox
// you consented to is that one, because consenting as the wrong Google
// account is the easy mistake and it fails silently — the pull would
// simply find nothing.

const fs = require('fs');
const path = require('path');
const { authenticate } = require('@google-cloud/local-auth');
const { google } = require('googleapis');

const {
  CREDS_DIR,
  OAUTH_KEYS_PATH,
  GMAIL_SCOPES,
  accountSlug,
  tokenPath,
} = require('./creds');

function argValue(name) {
  const i = process.argv.indexOf(name);
  if (i === -1) return null;
  const next = process.argv[i + 1];
  return next && !next.startsWith('--') ? next : null;
}

(async () => {
  const account = argValue('--account');
  if (process.argv.includes('--account') && !account) {
    console.error('--account needs an email address');
    process.exit(1);
  }
  if (!fs.existsSync(OAUTH_KEYS_PATH)) {
    console.error(`Missing OAuth client keys at ${OAUTH_KEYS_PATH} — see header comment.`);
    process.exit(1);
  }
  // An explicitly named account always gets its own token file: the
  // primary's fallback to credentials.json is a read-time convenience,
  // never a place to write a second mailbox's token.
  const destination = account
    ? path.join(CREDS_DIR, `credentials-${accountSlug(account)}.json`)
    : tokenPath(null);

  console.error(
    `Opening browser for Gmail authorization${account ? ` as ${account}` : ''}...`
  );
  const client = await authenticate({
    scopes: GMAIL_SCOPES,
    keyfilePath: OAUTH_KEYS_PATH,
  });

  if (account) {
    const profile = await google
      .gmail({ version: 'v1', auth: client })
      .users.getProfile({ userId: 'me' });
    const authorized = profile.data.emailAddress;
    if (authorized.toLowerCase() !== account.toLowerCase()) {
      console.error(
        `Authorized ${authorized}, but --account said ${account}. ` +
          'Nothing was saved; sign in as the account you named and retry.'
      );
      process.exit(1);
    }
  }

  fs.writeFileSync(destination, JSON.stringify(client.credentials));
  console.error(`Token saved to ${destination}`);
})();
