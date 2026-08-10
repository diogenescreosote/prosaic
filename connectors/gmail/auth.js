#!/usr/bin/env node
// gmail connector — one-time OAuth authorization.
//
// Usage: node auth.js
//
// Prereq: create a Google Cloud OAuth client (Desktop app) with the
// Gmail API enabled, download the client-secret JSON, and save it as
//   $PROSAIC_GMAIL_CREDS_DIR/oauth-keys.json
//   (default ~/.config/prosaic/gmail/oauth-keys.json)
// This script opens a browser consent flow and stores the resulting
// token alongside it as credentials.json. Re-run it whenever pulls
// start failing with invalid_grant (Google revoked/expired the token).

const fs = require('fs');
const os = require('os');
const path = require('path');
const { authenticate } = require('@google-cloud/local-auth');

const CREDS_DIR =
  process.env.PROSAIC_GMAIL_CREDS_DIR ||
  path.join(os.homedir(), '.config/prosaic/gmail');
const OAUTH_KEYS_PATH = path.join(CREDS_DIR, 'oauth-keys.json');
const CREDENTIALS_PATH = path.join(CREDS_DIR, 'credentials.json');

(async () => {
  if (!fs.existsSync(OAUTH_KEYS_PATH)) {
    console.error(`Missing OAuth client keys at ${OAUTH_KEYS_PATH} — see header comment.`);
    process.exit(1);
  }
  console.error('Opening browser for Gmail authorization...');
  const client = await authenticate({
    scopes: ['https://www.googleapis.com/auth/gmail.readonly'],
    keyfilePath: OAUTH_KEYS_PATH,
  });
  fs.writeFileSync(CREDENTIALS_PATH, JSON.stringify(client.credentials));
  console.error(`Token saved to ${CREDENTIALS_PATH}`);
})();
