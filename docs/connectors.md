# Connectors

A connector pulls one external source into a matter. Connectors are
the seam where cases genuinely differ, so they're designed to be
written, swapped, and retired independently — the rest of the system
only knows the contract below.

## The contract

A connector is a directory `connectors/<name>/` containing:

- **`manifest.json`** — `{name, description, entry, configKey, auth,
  output}`; consumed by `sc connectors` and by humans.
- **`pull.js`** (the `entry`) — invoked as
  `node connectors/<name>/pull.js <matter_dir>`, with
  `NODE_PATH=connectors/node_modules`.

`pull.js` must:

1. **Read its config** via `connectorConfig(matterDir, '<name>')` from
   `../core/config` (backed by `matter.yaml` → `connectors.<name>`).
   If unconfigured, print a note to stderr and exit 0 — an
   unconfigured connector is not an error.
2. **Write output into the matter** — either directly to its
   destination (born-digital, correctly named artifacts like Gmail
   thread PDFs) or into `inbox/<name>/` staging when a triage decision
   is needed about where things belong (like MyCase documents).
3. **Print `NEW <absolute path>` on stdout** for every file it
   creates or updates. *Nothing else goes to stdout*; all progress and
   diagnostics go to stderr. The sync orchestrator consumes these
   lines to build the AI triage worklist.

   One documented exception exists, and a new one needs the same
   argument: the gmail connector does not announce the mbox it stores
   a thread in, because that file is the *source* of the PDF it does
   announce (ADR-0038), and two `NEW` lines for one piece of evidence
   put two rows in the matter's catalog.
4. **Keep state in `.state/<name>.json`** via
   `loadState`/`saveState` from `../core/config`. Pulls must be
   idempotent: re-running after a crash re-downloads at most what
   wasn't recorded, and never duplicates what was.
5. **Exit nonzero on failure.** The orchestrator logs it and holds the
   sync guard back so the next scheduled firing retries.
6. **Never touch anything outside the matter directory** (plus its own
   state/profile/log locations).

## Shared infrastructure (`connectors/core/`)

- `config.js` — matter config + state helpers (above).
- `portal_common.js` — for browser-automation connectors:
  - `keychainCreds(service)` — credentials from the macOS Keychain
    (`security add-generic-password -s <service> -a <login> -w`);
    never store secrets in files.
  - `launchBrowser(profileName)` — headless Puppeteer with a
    persistent profile under `~/.local/share/prosaic/portal-profiles/`
    (local disk — deliberately NOT inside a cloud-synced folder),
    so sessions survive between runs and re-login is rare.
  - `dumpDebug(page, tag)` — on any selector failure, drop a
    screenshot + HTML snapshot into the log dir. This is the single
    most valuable habit for portal automation: when a site changes its
    UI, you diagnose from evidence instead of re-running blind.
  - helpers: `typeInto`, `clickByText`, `waitForDownload`,
    `allowDownloadsTo`, `literateName` (raw portal name → dated
    snake_case), `sleep`.

## Shipped connectors

| name | what it does | auth |
|---|---|---|
| `gmail` | Captures every Gmail thread involving configured addresses/domains **as raw mail** — one mbox per thread at `assets/gmail/mbox/<stem>.mbox`, RFC 822 bytes exactly as the API returns them for `format=raw` — and renders that mbox to the court-usable print-view PDF at `assets/gmail/<stem>.pdf` (ADR-0038). Capture and rendering are separate steps: the PDF is a pure function of the mbox plus options, so `sc mail-render` regenerates it at any time, with different options, offline. Quoted reply chains are **shown by default** (`quoted: hide` in config, or `--quoted hide`, reproduces Gmail's `[Quoted text hidden]` print behavior). Supports per-address `after:`/`before:` bounds, and `accounts:` for a matter that watches more than one mailbox — one OAuth token each, ledger keyed by account then thread id. Incremental via a `.state/gmail.json` thread ledger (per-thread `historyId`, message count and message ids): unchanged threads are skipped without a fetch, threads whose message set changed (grown, or a message replaced at the same count) re-export and re-triage, and a thread once exported is never re-pulled even if triage later moves the PDF. **Attachments are extracted from the stored MIME parts**, into `assets/gmail/attachments/<pdf stem>/`, each with its own `NEW` line — the print view can only list an attachment's *name*, and a document whose value is its contents is invisible to triage until the file itself lands. Images actually embedded in the rendering are excluded; files over 25MB are skipped with a `SKIPPED` line; a file already present at its target path with the expected size is not rewritten. The mbox gets no `NEW` line — it is the source the announced PDF was rendered from, not a second document. Threads exported before the mbox existed get one from `pull.js --backfill-mbox` (opt-in, `--limit N`, `--concurrency N`, resumable, renders nothing and announces nothing). Fetching is concurrent and bounded (6 messages per thread, 4 threads at a time in a backfill, 8 metadata lookups) with a 60-second per-request timeout and retry on transient failures. | OAuth; `node connectors/gmail/auth.js [--account <email>]` once per mailbox |
| `mycase` | Walks a MyCase client portal's document folder tree, diffs against a manifest (doc id + content hash), downloads new/updated documents into staging renamed to dated snake_case, keeping the portal folder as a routing hint. With `billing: <dir>` configured, also pulls the Billing tab: every bill whose detail page offers the portal's first-class PDF export (`/bills/<id>.pdf`) lands directly in `<dir>` (no triage — billing PDFs are born-digital and authoritatively named) as `<date>_invoice_<n>.pdf`, re-exported when a bill's listed status changes (a payment posts, a balance forwards) and never overwriting a previously fetched file; a bill with no export (funds requests) is noted, not fetched. | Keychain |

## Writing a new connector

Copy the closest shipped connector as a starting point. Hard-won
advice for portal (browser-automation) connectors:

- **Prefer the platform's own export/report feature** over scraping
  rendered content — exports tend to be court-friendlier (headers,
  metadata, certification pages) and more stable than DOM structure.
- **Assume the UI will change.** Wrap every step in a try/catch that
  calls `dumpDebug` with a distinct tag before rethrowing.
- **Never hold element handles across interactions** in React/MUI
  apps; re-query fresh (or work from bounding-box coordinates)
  immediately before each click/type. Beware: `Escape` closes MUI
  dialogs entirely.
- **Isolate downloads per tab** and tolerate detached-frame errors —
  direct downloads abort navigation by design.
- **Expect the browser itself to die** during long runs; check
  `browser.isConnected()`, relaunch (the persistent profile keeps the
  session), and retry the failed item once.
- **Write state incrementally** (after each item, not at the end) so a
  crash never forgets completed work.
- **Rate-limit yourself** (small sleeps between items). You're a
  polite client on your own account, not a crawler.

Then add a `manifest.json`, document the config keys in it and here,
and it's live: `sc sync` discovers connectors purely from
`matter.yaml` config keys + the connectors directory.

## Re-rendering stored mail

The gmail connector's presentation layer stands on its own:

```
sc mail-render assets/gmail/mbox/20260105_scheduling.mbox \
    --pdf /tmp/complete.pdf --quoted show
sc mail-render <mbox> --list                  # messages + attachments
sc mail-render <mbox> --eml 2:/tmp/second.eml # one message, verbatim
sc mail-render <mbox> --attachments           # extract the parts
```

No token, no mailbox, no network (beyond the gstatic icons Gmail's own
print view uses). This is what a stored raw record buys: a rendering
defect is a bug to fix and re-run, not damage to the archive.

Local deployments can carry additional connectors under
`local/connectors/` (see ADR-0032); they dispatch identically and are
documented in the local module's repository.
