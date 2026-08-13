#!/usr/bin/env node
//
// proof connector — thin relay to the Python Proof client's `poll`.
// Same one-implementation reasoning as the docuseal connector.
//
// Usage: node pull.js <matter_dir>

const { spawnSync } = require('child_process');
const path = require('path');

const matterDir = process.argv[2];
if (!matterDir) {
  console.error('usage: pull.js <matter_dir>');
  process.exit(2);
}

const client = path.join(__dirname, '..', '..', 'proof-client', 'client.py');
const result = spawnSync('python3', [client, 'poll', matterDir], {
  stdio: ['ignore', 'inherit', 'inherit'],
});
process.exit(result.status === null ? 1 : result.status);
