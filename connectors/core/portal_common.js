// portal_common.js — shared helpers for headless portal automation
// (mycase/pull.js). Browser sessions persist in local
// (non-cloud-synced) profiles so logins survive between runs.
//
// Credentials are resolved through core/secrets.js and directories
// through core/paths.js — this file knows about browsers, not about
// platforms.

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');
const { logDir, dataDir } = require('./paths');
const { resolveCredential } = require('./secrets');

const PROFILE_ROOT =
  process.env.PROSAIC_PROFILE_DIR ||
  path.join(dataDir(), 'portal-profiles');
const LOG_ROOT = logDir();
const DEBUG_DIR = path.join(LOG_ROOT, 'debug');

/**
 * Read {account, password} for a named credential.
 *
 * Retained as the name the connectors already call; the Keychain is
 * now one backend among several rather than the only option.
 */
function keychainCreds(ref) {
  return resolveCredential(ref);
}

async function launchBrowser(profileName) {
  const userDataDir = path.join(PROFILE_ROOT, profileName);
  fs.mkdirSync(userDataDir, { recursive: true });
  return puppeteer.launch({
    headless: 'new',
    userDataDir,
    args: ['--no-sandbox'],
    defaultViewport: { width: 1400, height: 1000 },
  });
}

// On failure, drop a screenshot + HTML snapshot so selector breakage can
// be diagnosed from logs without re-running interactively.
async function dumpDebug(page, tag) {
  try {
    fs.mkdirSync(DEBUG_DIR, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const base = path.join(DEBUG_DIR, `${tag}_${stamp}`);
    await page.screenshot({ path: `${base}.png`, fullPage: true });
    fs.writeFileSync(`${base}.html`, await page.content());
    console.error(`[debug] state dumped to ${base}.{png,html}`);
  } catch (e) {
    console.error(`[debug] dump failed: ${e.message}`);
  }
}

// Type into the first selector that exists on the page.
async function typeInto(page, selectors, text) {
  for (const sel of selectors) {
    const el = await page.$(sel);
    if (el) {
      await el.click({ clickCount: 3 });
      await el.type(text, { delay: 20 });
      return sel;
    }
  }
  throw new Error(`none of the selectors matched: ${selectors.join(', ')}`);
}

async function clickFirst(page, selectors) {
  for (const sel of selectors) {
    const el = await page.$(sel);
    if (el) {
      await el.click();
      return sel;
    }
  }
  throw new Error(`none of the selectors matched: ${selectors.join(', ')}`);
}

// Click the first element (of `baseSelector`) whose visible text matches re.
async function clickByText(page, baseSelector, re) {
  const handles = await page.$$(baseSelector);
  for (const h of handles) {
    const text = (await h.evaluate((el) => el.innerText || '')).trim();
    if (re.test(text)) {
      await h.click();
      return text;
    }
  }
  throw new Error(`no ${baseSelector} matching ${re}`);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// Wait for a new file to appear (and finish downloading) in dir.
async function waitForDownload(dir, before, timeoutMs = 120000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const now = fs.readdirSync(dir).filter((f) => !before.has(f));
    const done = now.filter((f) => !f.endsWith('.crdownload') && !f.startsWith('.'));
    if (done.length) {
      // ensure size is stable
      const p = path.join(dir, done[0]);
      const s1 = fs.statSync(p).size;
      await sleep(700);
      if (fs.statSync(p).size === s1) return p;
    }
    await sleep(500);
  }
  throw new Error('download did not complete in time');
}

async function allowDownloadsTo(page, dir) {
  fs.mkdirSync(dir, { recursive: true });
  const client = await page.createCDPSession();
  await client.send('Browser.setDownloadBehavior', {
    behavior: 'allow',
    downloadPath: dir,
    eventsEnabled: true,
  });
}

// "07/17/26 Notice of Civil Subpoena - Magil" -> "2026-07-17_notice_of_civil_subpoena_magil"
function literateName(rawName) {
  let name = rawName.trim().replace(/\.pdf$/i, '');
  let datePrefix = '';
  const m = name.match(/^(\d{1,2})[\/._-](\d{1,2})[\/._-](\d{2,4})\s*[-_ ]*\s*(.*)$/);
  if (m) {
    let [, mm, dd, yy, rest] = m;
    const yyyy = yy.length === 4 ? yy : `20${yy}`;
    datePrefix = `${yyyy}-${mm.padStart(2, '0')}-${dd.padStart(2, '0')}_`;
    name = rest || 'document';
  }
  const snake = name
    .replace(/&/g, ' and ')
    .replace(/'/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .substring(0, 90);
  return `${datePrefix}${snake || 'document'}`;
}

module.exports = {
  keychainCreds,
  launchBrowser,
  dumpDebug,
  typeInto,
  clickFirst,
  clickByText,
  sleep,
  waitForDownload,
  allowDownloadsTo,
  literateName,
  DEBUG_DIR,
};
