// paths.js — where prosaic keeps logs, data, and caches.
//
// This module does not decide anything. The policy lives in exactly
// one place, `cli/sc` (`sc paths <kind>`), and this asks it. A second
// implementation here would be a copy that can drift, and a test
// asserting two copies agree is a worse guarantee than not having two
// copies.
//
// Cost: one subprocess, once, only when the answer wasn't inherited.
// Anything that spawns connectors (matter_sync.sh) exports
// PROSAIC_LOG_DIR and friends, so the usual path spawns nothing.

const { execFileSync } = require('child_process');
const path = require('path');

const SC = path.join(__dirname, '..', '..', 'cli', 'sc');

const ENV_VAR = {
  'log-dir': 'PROSAIC_LOG_DIR',
  'data-dir': 'PROSAIC_DATA_DIR',
  'cache-dir': 'PROSAIC_CACHE_DIR',
};

const cache = new Map();

function appPath(kind) {
  const inherited = process.env[ENV_VAR[kind]];
  if (inherited) return inherited;
  if (cache.has(kind)) return cache.get(kind);

  let resolved;
  try {
    resolved = execFileSync(SC, ['paths', kind], { encoding: 'utf8' }).trim();
  } catch (e) {
    throw new Error(
      `Could not resolve the ${kind} from "${SC} paths ${kind}": ${e.message}\n` +
        `Set ${ENV_VAR[kind]} to bypass, or check that cli/sc is executable ` +
        `and python3 is on PATH.`
    );
  }
  cache.set(kind, resolved);
  return resolved;
}

const logDir = () => appPath('log-dir');
const dataDir = () => appPath('data-dir');
const cacheDir = () => appPath('cache-dir');

module.exports = { appPath, logDir, dataDir, cacheDir };
