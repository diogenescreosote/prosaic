#!/usr/bin/env node
//
// mycase_sync.js — sync documents from a MyCase client portal into a
// matter directory's staging area, renamed to the workspace's dated
// snake_case nomenclature.
//
// Usage:  node mycase_sync.js <matter_dir>
//
// Config (matter.yaml, connectors.mycase; legacy envelopes.yaml mycase: also read):
//   mycase:
//     portal_url: https://your-firm.mycase.com
//     credential: prosaic.mycase   # security add-generic-password -s prosaic.mycase -a <email> -w
//     staging: inbox/mycase                # default
//
// State:  <matter>/.state/mycase.json — {docs: {<docId>: {name, updated, sha256, localName}}}
// Output: downloads new/updated docs to staging, prints "NEW <abs path>"
//         per file on stdout (consumed by matter_sync.sh for triage).

// Suppress DEP0040 punycode warning from googleapis/puppeteer dep chains.
const _emitWarning = process.emitWarning;
process.emitWarning = function (warning, ...args) {
  const code = args[0] && typeof args[0] === 'object' ? args[0].code : args[1];
  if (code === 'DEP0040') return;
  return _emitWarning.call(process, warning, ...args);
};

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { connectorConfig, loadState, saveState } = require('../core/config');
const { credentialRef } = require('../core/secrets');
const {
  keychainCreds,
  launchBrowser,
  dumpDebug,
  typeInto,
  sleep,
  waitForDownload,
  allowDownloadsTo,
  literateName,
} = require('../core/portal_common');

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

async function ensureLoggedIn(page, portalUrl, creds) {
  await page.goto(portalUrl, { waitUntil: 'networkidle2', timeout: 60000 });
  // If a password field is visible we are on the login screen.
  const needsLogin = await page.$('input[type="password"]');
  if (!needsLogin) return;
  console.error('[mycase] logging in...');
  await typeInto(
    page,
    [
      'input[type="email"]',
      'input[name*="email" i]',
      'input[id*="email" i]',
      'input[name*="login" i]',
      'input[type="text"]',
    ],
    creds.account
  );
  await typeInto(page, ['input[type="password"]'], creds.password);
  await Promise.all([
    page
      .waitForNavigation({ waitUntil: 'networkidle2', timeout: 60000 })
      .catch(() => {}),
    page.keyboard.press('Enter'),
  ]);
  await sleep(3000);
  if (await page.$('input[type="password"]')) {
    await dumpDebug(page, 'mycase_login_failed');
    throw new Error('MyCase login appears to have failed (still on login page)');
  }
  console.error('[mycase] login ok');
}

// Walk the portal's Documents folder tree (BFS from the case picker,
// which redirects to the case's root folder) and return
// [{id, name, href, folder}]. Anchor innerText lines look like
// "description \n 07/29/26 Order ... \n some_file.pdf \n Aug 4, 2026",
// where the first line is a material-icon token to discard.
async function listDocuments(page, portalUrl) {
  await page
    .goto(`${portalUrl}/documents_case_picker`, {
      waitUntil: 'networkidle2',
      timeout: 60000,
    })
    .catch(() => {});
  await sleep(2500);
  if (!/\/folders\//.test(page.url())) {
    // Multi-case picker: enqueue every case/folder link on the page.
    await dumpDebug(page, 'mycase_case_picker');
  }

  const queue = [{ url: page.url(), path: '' }];
  const visitedFolders = new Set();
  const docs = new Map();

  while (queue.length) {
    const { url, path: folderPath } = queue.shift();
    if (visitedFolders.has(url)) continue;
    visitedFolders.add(url);
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 }).catch(() => {});
    await sleep(2000);

    for (let pageNum = 0; pageNum < 50; pageNum++) {
      const { folders, documents } = await page.evaluate(() => {
        const ICON_WORDS = /^(description|folder|insert_drive_file|picture_as_pdf|attach_file)$/i;
        const parseName = (a) =>
          (a.innerText || '')
            .split('\n')
            .map((s) => s.trim())
            .filter((s) => s && !ICON_WORDS.test(s));
        const folders = [];
        const documents = [];
        for (const a of document.querySelectorAll('a[href]')) {
          const href = a.getAttribute('href') || '';
          const fm = href.match(/^\/folders\/(f\d+)/);
          const dm = href.match(/\/documents\/(\d+)/);
          if (fm) {
            const lines = parseName(a);
            folders.push({ href: a.href, name: lines[0] || fm[1] });
          } else if (dm) {
            const lines = parseName(a);
            if (lines.length) documents.push({ id: dm[1], href: a.href, name: lines[0] });
          }
        }
        return { folders, documents };
      });
      for (const d of documents)
        if (!docs.has(d.id)) docs.set(d.id, { ...d, folder: folderPath });
      for (const f of folders)
        if (!visitedFolders.has(f.href))
          queue.push({
            url: f.href,
            path: folderPath ? `${folderPath}/${f.name}` : f.name,
          });
      const advanced = await page.evaluate(() => {
        const next = [...document.querySelectorAll('a, button')].find(
          (el) =>
            /^(next|›|»)$/i.test((el.innerText || '').trim()) &&
            !el.disabled &&
            !/disabled/.test(el.className || '')
        );
        if (next) {
          next.click();
          return true;
        }
        return false;
      });
      if (!advanced) break;
      await sleep(2500);
    }
  }
  if (!docs.size) {
    await dumpDebug(page, 'mycase_no_documents');
    throw new Error('could not locate any documents in the portal folder tree');
  }
  return [...docs.values()];
}

// Download one document in its own tab: navigating to a MyCase doc URL
// either triggers a download directly (which aborts/detaches the frame —
// expected, tolerated) or lands on a preview page with a Download
// control. A fresh tab per doc keeps detached-frame errors contained.
async function downloadDoc(browser, doc, tmpDir) {
  const before = new Set(fs.readdirSync(tmpDir));
  const page = await browser.newPage();
  try {
    await allowDownloadsTo(page, tmpDir);
    await page
      .goto(doc.href, { waitUntil: 'networkidle2', timeout: 60000 })
      .catch(() => {});
    await sleep(1500);
    try {
      return await waitForDownload(tmpDir, before, 8000);
    } catch {
      /* not a direct download — look for a Download control */
    }
    const clicked = await page
      .evaluate(() => {
        const els = [...document.querySelectorAll('a, button')];
        const el = els.find(
          (e) =>
            /download/i.test(e.innerText || '') ||
            /download/i.test(e.getAttribute?.('aria-label') || '')
        );
        if (el) {
          el.click();
          return true;
        }
        return false;
      })
      .catch(() => false); // frame may have detached on a direct download
    if (clicked) return await waitForDownload(tmpDir, before, 120000);
    // Last chance: the direct download may just be slow.
    try {
      return await waitForDownload(tmpDir, before, 20000);
    } catch {
      await dumpDebug(page, `mycase_no_download_${doc.id}`).catch(() => {});
      throw new Error(`no download produced for doc ${doc.id} (${doc.name})`);
    }
  } finally {
    await page.close().catch(() => {});
  }
}

async function main() {
  const matterDir = process.argv[2];
  if (!matterDir) {
    console.error('usage: mycase_sync.js <matter_dir>');
    process.exit(64);
  }
  const cfg = connectorConfig(matterDir, 'mycase');
  if (!cfg || !cfg.portal_url) {
    console.error('mycase connector not configured (needs portal_url); nothing to do');
    return;
  }
  const stagingDir = path.resolve(matterDir, cfg.staging || 'inbox/mycase');
  fs.mkdirSync(stagingDir, { recursive: true });
  const manifest = loadState(matterDir, 'mycase', { docs: {} });

  const creds = keychainCreds(credentialRef(cfg, 'prosaic.mycase'));
  let browser = await launchBrowser('mycase');
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mycase-'));
  let newCount = 0;
  let failCount = 0;
  try {
    const page = await browser.newPage();
    await allowDownloadsTo(page, tmpDir);
    await ensureLoggedIn(page, cfg.portal_url, creds);
    const docs = await listDocuments(page, cfg.portal_url);
    console.error(`[mycase] portal lists ${docs.length} documents`);

    for (const doc of docs) {
      const known = manifest.docs[doc.id];
      if (known && known.name === doc.name) continue; // unchanged (name+id heuristic; content check below on updates)
      let dl;
      try {
        dl = await downloadDoc(browser, doc, tmpDir);
      } catch (e) {
        // Chromium sometimes dies mid-run under rapid tab cycling;
        // relaunch (the profile keeps the session) and retry once.
        if (!browser.isConnected()) {
          console.error('[mycase] browser died; relaunching...');
          await browser.close().catch(() => {});
          browser = await launchBrowser('mycase');
          await sleep(1500);
          try {
            dl = await downloadDoc(browser, doc, tmpDir);
          } catch (e2) {
            console.error(`[mycase] SKIP doc ${doc.id} (${doc.name}): ${e2.message}`);
            failCount++;
            continue;
          }
        } else {
          console.error(`[mycase] SKIP doc ${doc.id} (${doc.name}): ${e.message}`);
          failCount++;
          continue; // not added to manifest — retried next run
        }
      }
      await sleep(400);
      const hash = sha256(dl);
      if (known && known.sha256 === hash) {
        manifest.docs[doc.id] = { ...known, name: doc.name };
        fs.unlinkSync(dl);
        continue; // renamed in MyCase but same bytes
      }
      const ext = path.extname(dl) || '.pdf';
      // Stage under a subdirectory named for the portal folder (e.g.
      // pleadings_documents_filed_with_the_court/) — a routing signal
      // for the triage step.
      const folderSlug = (doc.folder || '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');
      const destDir = folderSlug ? path.join(stagingDir, folderSlug) : stagingDir;
      fs.mkdirSync(destDir, { recursive: true });
      let base = literateName(doc.name);
      let localName = `${base}${ext}`;
      let n = 2;
      while (
        fs.existsSync(path.join(destDir, localName)) &&
        sha256(path.join(destDir, localName)) !== hash
      ) {
        localName = `${base}_${n++}${ext}`;
      }
      const dest = path.join(destDir, localName);
      fs.copyFileSync(dl, dest);
      fs.unlinkSync(dl);
      manifest.docs[doc.id] = {
        name: doc.name,
        folder: doc.folder || '',
        sha256: hash,
        localName: path.relative(stagingDir, dest),
        fetched: new Date().toISOString(),
      };
      newCount++;
      console.log(`NEW ${dest}`);
      // Incremental write so a mid-run crash doesn't forget completed work.
      saveState(matterDir, 'mycase', manifest);
    }
    saveState(matterDir, 'mycase', manifest);
    console.error(
      `[mycase] done: ${newCount} new/updated document(s), ${failCount} failed`
    );
    if (failCount) process.exitCode = 1;
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    await browser.close();
  }
}

main().catch((err) => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
