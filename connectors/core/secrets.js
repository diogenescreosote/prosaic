// secrets.js — resolve a named credential to {account, password}.
//
// A matter's config names a credential; it does not say where the
// credential lives. That indirection is the whole point: the same
// `credential: prosaic.mycase` works against the macOS Keychain on a
// laptop and against environment variables in a container, and adds
// a Linux Secret Service backend later without touching any matter.
//
// Backends
//   env       <SLUG>_USERNAME / <SLUG>_PASSWORD, where SLUG is the
//             reference upper-cased with non-alphanumerics collapsed
//             to underscores: prosaic.mycase -> PROSAIC_MYCASE_*.
//   keychain  macOS generic-password entries, via `security`.
//   auto      (default) env if present, else keychain on macOS.
//
// env wins under `auto` so a headless or CI run can override without
// reconfiguring the matter — and so a developer can point one run at
// a test account without disturbing their Keychain.
//
// Not yet implemented, and deliberately: Secret Service (libsecret),
// `pass`, and age/sops files. Each is a small addition here, and none
// should be written before there is a machine to test it on — an
// untested credential backend is worse than an absent one.
//
// PROSAIC_SECRET_BACKEND forces a backend. PROSAIC_PLATFORM
// overrides platform detection (tests only).

const { execFileSync } = require('child_process');

// Which credential stores exist here. Not directory policy — no
// filesystem layout is being decided — so it stays local rather than
// reaching into paths.js.
function platform() {
  return process.env.PROSAIC_PLATFORM || process.platform;
}

/** prosaic.mycase -> PROSAIC_MYCASE */
function envSlug(ref) {
  return ref
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toUpperCase();
}

function fromEnv(ref) {
  const slug = envSlug(ref);
  const account = process.env[`${slug}_USERNAME`];
  const password = process.env[`${slug}_PASSWORD`];
  if (!account && !password) return null; // not configured; not an error
  if (!account || !password) {
    throw new Error(
      `Credential "${ref}" is half-configured in the environment: ` +
        `${slug}_${account ? 'PASSWORD' : 'USERNAME'} is missing.`
    );
  }
  return { account, password };
}

function fromKeychain(ref) {
  let meta, password;
  try {
    meta = execFileSync('security', ['find-generic-password', '-s', ref], {
      encoding: 'utf8',
    });
    password = execFileSync(
      'security',
      ['find-generic-password', '-s', ref, '-w'],
      { encoding: 'utf8' }
    ).trim();
  } catch {
    throw new Error(
      `Keychain entry "${ref}" not found. Create it with:\n` +
        `  security add-generic-password -s ${ref} -a <login-email> -w`
    );
  }
  const account = meta.match(/"acct"<blob>="([^"]+)"/)?.[1];
  if (!account || !password) {
    throw new Error(`Keychain entry "${ref}" is missing account or password`);
  }
  return { account, password };
}

/**
 * Resolve a credential reference.
 *
 * @param {string} ref     name from the matter's config, e.g. "prosaic.mycase"
 * @param {string} backend "auto" | "env" | "keychain"
 * @returns {{account: string, password: string}}
 */
function resolveCredential(ref, backend) {
  if (!ref) throw new Error('resolveCredential: no credential reference given');
  const chosen = backend || process.env.PROSAIC_SECRET_BACKEND || 'auto';

  if (chosen === 'env') {
    const found = fromEnv(ref);
    if (!found) {
      throw new Error(
        `Credential "${ref}" not found in the environment. Set ` +
          `${envSlug(ref)}_USERNAME and ${envSlug(ref)}_PASSWORD.`
      );
    }
    return found;
  }

  if (chosen === 'keychain') return fromKeychain(ref);

  if (chosen !== 'auto') {
    throw new Error(
      `Unknown secret backend "${chosen}" ` +
        `(expected auto, env, or keychain).`
    );
  }

  const found = fromEnv(ref);
  if (found) return found;
  if (platform() === 'darwin') return fromKeychain(ref);

  throw new Error(
    `No credential store available for "${ref}" on this platform.\n` +
      `Set ${envSlug(ref)}_USERNAME and ${envSlug(ref)}_PASSWORD in the ` +
      `environment, or add a backend in connectors/core/secrets.js.`
  );
}

/**
 * Read a credential reference out of a connector's config, accepting
 * the pre-rename key.
 *
 * `keychain_service:` named a macOS mechanism in a file that should
 * only name a credential. It stays valid — matters in flight must not
 * break — but warns, so the deprecation is visible rather than
 * permanent.
 */
function credentialRef(cfg, fallback) {
  if (cfg?.credential) return cfg.credential;
  if (cfg?.keychain_service) {
    process.emitWarning(
      `matter.yaml: "keychain_service:" is deprecated; rename it to ` +
        `"credential:" (same value). It names a credential, not a store.`,
      'DeprecationWarning'
    );
    return cfg.keychain_service;
  }
  return fallback;
}

module.exports = { resolveCredential, credentialRef, envSlug };
