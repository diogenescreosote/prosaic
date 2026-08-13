#!/usr/bin/env node
//
// esign connector — thin relay to the Python e-sign client's `poll`.
//
// The connector contract (docs/connectors.md) is Node printing
// "NEW <abs path>" lines; the DocuSeal workflow already lives in
// esign/client.py with its SDK, receipts, and tests. Spawning it
// keeps one implementation instead of a drifting second one.
//
// Usage: node pull.js <matter_dir>

const { spawnSync } = require('child_process');
const path = require('path');

const matterDir = process.argv[2];
if (!matterDir) {
  console.error('usage: pull.js <matter_dir>');
  process.exit(2);
}

const client = path.join(__dirname, '..', '..', 'esign', 'client.py');
const result = spawnSync('python3', [client, 'poll', matterDir], {
  stdio: ['ignore', 'inherit', 'inherit'],  // NEW lines flow to stdout
});
process.exit(result.status === null ? 1 : result.status);
