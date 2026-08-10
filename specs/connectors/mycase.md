# Spec: mycase connector

## Purpose

When counsel runs the case through a MyCase client portal, the
portal becomes a drip feed of filings, drafts, and records that the
client would otherwise download by hand, one at a time, into a
Downloads folder with useless names. The mycase connector walks the
portal's document folder tree and brings every new or updated
document into the matter's staging area, renamed to the matter's
dated snake_case convention — leaving the *routing* decision (is
this a filed pleading? a draft? an exhibit source?) to triage, which
is equipped to make it.

## Promises

1. **Staging, not destination.** Everything lands under
   `inbox/mycase/`, mirroring the portal's folder structure as a
   routing hint. The connector never decides whether a document is a
   pleading, a lawyer draft, or an asset — a wrong guess filed into
   `pleadings/` would corrupt the court record's directory.
   *(untested)*
2. **Content-hash dedup.** Documents are tracked in a manifest by
   portal document id *and* content hash, so a re-uploaded or
   renamed-but-identical document is not downloaded again, while a
   genuinely revised document (same id, new content) is. *(untested)*
3. **Literate names on arrival.** Raw portal names become dated
   snake_case at download time, so even unrouted staging is
   readable, sortable, and greppable. *(untested)*
4. **Update-safe and crash-safe.** The manifest is written
   incrementally per document; a crash mid-run forgets nothing
   completed and re-downloads at most the in-flight item.
   *(untested)*
5. **Contract compliance**: keychain credentials, state in
   `.state/mycase.json`, `NEW` lines on stdout only, nonzero exit on
   failure. *(untested)*

## Non-obvious constraints

- **The portal folder is a hint, not an authority.** Firms organize
  portals inconsistently; a "Court Documents" folder may hold drafts
  and a "Shared" folder may hold conformed copies. Triage inspects
  content (file stamps, conformed captions) before routing — which
  is precisely why the connector must preserve the folder path
  instead of flattening it, and must not route on it.
- **Staged duplicates are the one thing triage may delete**: when a
  staged document's content-identical twin already sits in
  `pleadings/`, the staged copy is redundant by construction. The
  connector's content hashes are what make that comparison cheap and
  safe.
- **Documents can be revised upstream.** The same portal id
  reappearing with new bytes means counsel replaced the file; the
  connector must surface it as new material (a fresh `NEW` line),
  never silently overwrite a previously triaged copy.
- **Portal automation caveats apply** (see the contract spec):
  evidence-dumping on failure, fresh element queries, per-tab
  download isolation, local-disk browser profile, polite pacing.
