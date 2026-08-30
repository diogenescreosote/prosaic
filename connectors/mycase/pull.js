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
//     billing: invoices                    # optional: pull invoice/funds-request
//                                          # PDFs into this dir (matter-relative);
//                                          # absent = billing not pulled
//
// State:  <matter>/.state/mycase.json — {docs: {<docId>: {name, updated, sha256, localName}},
//                                        bills: {<billId>: {detail, amount, status, sha256, localName}}}
// Output: downloads new/updated docs to staging (and, when configured,
//         billing PDFs to their destination), prints "NEW <abs path>"
//         per file on stdout (consumed by matter_sync.sh for triage).

// Suppress DEP0040 punycode warning from googleapis/puppeteer dep chains.
const _emitWarning = process.emitWarning;
process.emitWarning = function (warning, ...args) {
  const code = args[0] && typeof args[0] === 'object' ? args[0].code : args[1];
  if (code === 'DEP0040') return;
  return _emitWarning.call(process, warning, ...args);
};

const cheerio = require('cheerio');
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

// --- billing ----------------------------------------------------------
//
// The portal's Billing tab (/bills) lists every invoice and funds
// request as an <li class="payable"> row linking to /bills/<id>, and
// each has a first-class PDF export at /bills/<id>.pdf — the platform's
// own export, not a scrape of the rendered page. Billing PDFs are
// born-digital and authoritatively named, so (unlike documents) they
// go straight to their configured destination rather than staging.

// Parse the /bills listing. Each row shows an amount
// (".list-row__header"), a detail line like "Jul 28, 2026 - Inv. #13742"
// or "Sep 15, 2025 - #R-00228" (".list-row__header-detail"), and a
// status — "Overdue" (".list-row__alert-text") or "Paid ..."/
// "Forwarded to #..." (".payable-row__payment").
function parseBillRows(html) {
  const $ = cheerio.load(html);
  const rows = [];
  $('li.payable').each((_, li) => {
    const a = $(li).find('a[href^="/bills/"]').first();
    const m = (a.attr('href') || '').match(/^\/bills\/(\d+)/);
    if (!m) return;
    rows.push({
      id: m[1],
      amount: $(li).find('.list-row__header').first().text().trim(),
      detail: $(li).find('.list-row__header-detail').first().text().trim(),
      status: $(li)
        .find('.list-row__alert-text, .payable-row__payment')
        .first()
        .text()
        .trim(),
    });
  });
  return rows;
}

const BILL_MONTHS = {
  jan: '01', feb: '02', mar: '03', apr: '04', may: '05', jun: '06',
  jul: '07', aug: '08', sep: '09', oct: '10', nov: '11', dec: '12',
};

// "Jul 28, 2026 - Inv. #13742" -> "2026-07-28_invoice_13742"
// "Sep 15, 2025 - #R-00228"    -> "2025-09-15_funds_request_r00228"
// Unparseable detail lines fall back to the portal's bill id.
function billFileName(detail, id) {
  const m = (detail || '').match(
    /^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),\s*(\d{4})\s*(?:-\s*(.*))?$/
  );
  const mm = m && BILL_MONTHS[m[1].toLowerCase()];
  if (!mm) return `bill_${id}`;
  const date = `${m[3]}-${mm}-${m[2].padStart(2, '0')}`;
  const rest = m[4] || '';
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '');
  const inv = rest.match(/inv(?:oice)?\.?\s*#?\s*([\w-]+)/i);
  if (inv) return `${date}_invoice_${slug(inv[1])}`;
  const ref = rest.match(/#\s*([\w-]+)/);
  if (ref) return `${date}_funds_request_${slug(ref[1])}`;
  return `${date}_bill_${id}`;
}

// The detail page's export control:
//   <a class="payable-detail__export-link" href="/bills/<id>.pdf">
// Invoices carry it; funds requests render no export control at all —
// the portal has no PDF for them, and guessing /bills/<id>.pdf blind
// returns an error page rendered *as a PDF*, which must never be saved
// as if it were the bill.
function billExportHref(html) {
  const $ = cheerio.load(html);
  const explicit = $('a.payable-detail__export-link').first().attr('href');
  if (explicit) return explicit;
  let fallback = null;
  $('a[href]').each((_, a) => {
    const href = $(a).attr('href') || '';
    if (!fallback && /^\/bills\/\d+\.pdf$/.test(href)) fallback = href;
  });
  return fallback;
}

// Fetch one bill's PDF export in its own tab (same isolation rationale
// as downloadDoc: a direct download aborts navigation by design).
// Returns null when the bill's detail page offers no export.
async function downloadBillPdf(browser, portalUrl, bill, tmpDir) {
  const page = await browser.newPage();
  try {
    await allowDownloadsTo(page, tmpDir);
    await page
      .goto(`${portalUrl}/bills/${bill.id}`, {
        waitUntil: 'networkidle2',
        timeout: 60000,
      })
      .catch(() => {});
    await sleep(1500);
    const href = billExportHref(await page.content());
    if (!href) return null;
    const before = new Set(fs.readdirSync(tmpDir));
    await page
      .goto(`${portalUrl}${href}`, { waitUntil: 'networkidle2', timeout: 60000 })
      .catch(() => {});
    try {
      return await waitForDownload(tmpDir, before, 60000);
    } catch {
      await dumpDebug(page, `mycase_no_bill_pdf_${bill.id}`).catch(() => {});
      throw new Error(`no PDF produced for bill ${bill.id} (${bill.detail})`);
    }
  } finally {
    await page.close().catch(() => {});
  }
}

// Pull every new or status-changed bill into cfg.billing. A bill whose
// listed status changed (a payment posted, a balance forwarded) is
// re-exported: the PDF's face changes with it. Same bytes = manifest
// refresh only; new bytes never overwrite a previously fetched file.
async function pullBilling(browser, page, cfg, matterDir, manifest, tmpDir) {
  const destDir = path.resolve(matterDir, cfg.billing);
  await page
    .goto(`${cfg.portal_url}/bills`, { waitUntil: 'networkidle2', timeout: 60000 })
    .catch(() => {});
  await sleep(2000);
  const rows = parseBillRows(await page.content());
  if (!rows.length) {
    await dumpDebug(page, 'mycase_no_bills');
    throw new Error('billing is configured but /bills lists no bills');
  }
  console.error(`[mycase] portal lists ${rows.length} bills`);
  manifest.bills = manifest.bills || {};
  let newCount = 0;
  let failCount = 0;
  for (const bill of rows) {
    const known = manifest.bills[bill.id];
    if (known && known.status === bill.status && known.detail === bill.detail)
      continue; // unchanged listing; content re-checked only on a change
    let dl;
    try {
      dl = await downloadBillPdf(browser, cfg.portal_url, bill, tmpDir);
    } catch (e) {
      console.error(`[mycase] SKIP bill ${bill.id} (${bill.detail}): ${e.message}`);
      failCount++;
      continue; // not recorded — retried next run
    }
    if (dl === null) {
      // Not a failure: the portal genuinely has no PDF for this bill
      // (funds requests). Recorded so it isn't revisited until its
      // listed status changes.
      console.error(
        `[mycase] bill ${bill.id} (${bill.detail}) offers no PDF export; noted`
      );
      manifest.bills[bill.id] = {
        detail: bill.detail,
        amount: bill.amount,
        status: bill.status,
        exported: false,
        noted: new Date().toISOString(),
      };
      saveState(matterDir, 'mycase', manifest);
      continue;
    }
    await sleep(400);
    const hash = sha256(dl);
    if (known && known.sha256 === hash) {
      manifest.bills[bill.id] = { ...known, ...bill };
      fs.unlinkSync(dl);
      saveState(matterDir, 'mycase', manifest);
      continue; // status changed in the listing but same bytes
    }
    fs.mkdirSync(destDir, { recursive: true });
    const base = billFileName(bill.detail, bill.id);
    let localName = `${base}.pdf`;
    let n = 2;
    while (
      fs.existsSync(path.join(destDir, localName)) &&
      sha256(path.join(destDir, localName)) !== hash
    ) {
      localName = `${base}_${n++}.pdf`;
    }
    const dest = path.join(destDir, localName);
    fs.copyFileSync(dl, dest);
    fs.unlinkSync(dl);
    manifest.bills[bill.id] = {
      detail: bill.detail,
      amount: bill.amount,
      status: bill.status,
      sha256: hash,
      localName,
      fetched: new Date().toISOString(),
    };
    newCount++;
    console.log(`NEW ${dest}`);
    // Incremental write so a mid-run crash doesn't forget completed work.
    saveState(matterDir, 'mycase', manifest);
  }
  console.error(
    `[mycase] billing done: ${newCount} new/updated bill(s), ${failCount} failed`
  );
  return { newCount, failCount };
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
    // Billing first: a handful of PDFs, independent of the (much
    // longer) document crawl, so a crawl failure can't block invoices.
    if (cfg.billing) {
      const billing = await pullBilling(browser, page, cfg, matterDir, manifest, tmpDir);
      newCount += billing.newCount;
      failCount += billing.failCount;
    }
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
      `[mycase] done: ${newCount} new/updated file(s), ${failCount} failed`
    );
    if (failCount) process.exitCode = 1;
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    await browser.close();
  }
}

module.exports = { parseBillRows, billFileName, billExportHref };

if (require.main === module) {
  main().catch((err) => {
    console.error('Fatal:', err.message);
    process.exit(1);
  });
}
