# Spec: the connector contract

## Purpose

Connectors are where cases genuinely differ: one matter's evidence
arrives by Gmail, another's through an insurer's claim portal, a
third's from a law firm's client portal. A connector pulls exactly
one external source into a matter, so sources can be added, swapped,
and retired independently — the rest of the system (sync, triage)
knows only the contract below and never the source's quirks.

## Promises

Every connector, present or future, keeps all of these:

1. **Idempotence.** Re-running after a crash re-downloads at most
   what was not yet recorded in its state, and never duplicates what
   was. Pulling twice is always safe; state is written incrementally
   so completed work survives any failure. *(untested)*
2. **NEW-line reporting.** For every file it creates or updates, the
   connector prints `NEW <absolute path>` on stdout — and *nothing
   else* goes to stdout; progress and diagnostics go to stderr. The
   sync orchestrator builds the AI triage worklist purely from these
   lines, so a stray print becomes a phantom file and a missing line
   becomes untriaged evidence. *(untested)*
3. **State isolation.** All incremental state lives in the matter's
   `.state/<name>.json`; two matters using the same connector share
   nothing, and deleting a matter's state merely makes the next pull
   a full one. *(untested)*
4. **Unconfigured is not an error.** A connector without config for
   this matter notes it on stderr and exits 0 — matters legitimately
   use different subsets of connectors. *(untested)*
5. **Failure is loud and consequential.** On any real failure the
   connector exits nonzero, which holds the sync guard back so the
   next scheduled firing retries; sources never silently fall out of
   sync. *(untested)*
6. **Nothing outside the matter is touched.** Output goes into the
   matter directory (destination or `inbox/<name>/` staging); the
   only exceptions are the connector's own state, browser profile,
   and log locations. A connector never writes into another matter,
   the repo, or the user's files. *(untested)*
7. **Secrets never live in files.** Credentials come from the OS
   keychain or an OAuth token store, never from the matter directory
   or the repo. *(untested)*

## Non-obvious constraints

- **Destination vs. staging is a semantic choice.** Born-digital,
  correctly named artifacts (Gmail thread PDFs, portal reports) go
  straight to their `assets/` destination; material whose proper
  home requires a *judgment call* (portal documents that might be
  pleadings, drafts, or exhibits) goes to `inbox/<name>/` staging
  for triage to route. A connector must not guess routing that
  triage is designed to decide.
- **Prefer the platform's own export over scraping.** Official
  exports carry headers, certification pages, and metadata that make
  them court-usable, and they survive UI redesigns that break DOM
  scraping. A connector that scrapes what the platform would export
  produces weaker evidence.
- **Assume the portal UI will change**; on any automation failure,
  capture evidence (screenshot + HTML) before failing, so the fix is
  diagnosed from artifacts instead of re-running blind.
- **Browser profiles live on local disk**, never in cloud-synced
  folders — session cookies in a synced directory are a privacy
  smell and a corruption risk.
- **Be a polite client**: rate-limit, on your own account, pulling
  your own data.

## Per-connector specs

- [gmail.md](gmail.md) — email threads as court-usable PDFs
- [mycase.md](mycase.md) — law-firm client portal documents

## Local connectors (ADR-0032)

A deployment may add connectors without touching this repo: a
gitignored `local/connectors/<name>/pull.js` participates in dispatch
exactly like an in-repo connector, wins on a name collision, and its
name joins the legacy `envelopes.yaml` key scan automatically. Specs
for local connectors live in the local module's own repository.
