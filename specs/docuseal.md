# Spec: e-signature (`sc docuseal`)

## Purpose

Get a document signed by people who install nothing, and bring the
signed original plus its audit trail back into the matter
(ADR-0023). DocuSeal does delivery and capture; `docuseal-client/client.py`
does prosaic's side.

## Promises

- **The transport is the official SDK** (pypi `docuseal`, in the
  python requirements): prosaic owns the workflow, DocuSeal owns the
  HTTP contract, and the contract version is pinned by the lockfile.
  Their agent skills are referenced by their official channel
  (`npx skills add docusealco/docuseal-agent-skills`), not vendored.
  *(tested: tests/test_docuseal.py, through the SDK against a mock API)*
- **Deployment is one setting.** Every request goes to
  `DOCUSEAL_URL` (or `DOCUSEAL_SERVER`, the official CLI's spelling),
  else the matter's `connectors.docuseal.url`, else
  `https://api.docuseal.com`; a self-hosted instance needs nothing
  but that setting. *(tested: tests/test_docuseal.py)*
- **Credentials are the matter's, by reference (ADR-0031).** The key
  resolves `DOCUSEAL_API_KEY` (an explicit per-run act) first; inside
  a matter, the Keychain item named by
  `connectors.docuseal.credential` in matter.yaml — a connector with
  no `credential:` is a refusal that prints the exact lines to add,
  even when a global `prosaic.docuseal` key exists. Only outside any
  matter does the global name apply on its own. Key material never
  enters the matter; a missing key is a clear how-to-configure
  error — never a silent default. *(tested: tests/test_docuseal.py)*
- **A draft never ships by accident.** `send` refuses a PDF whose
  metadata carries the prosaic draft stamp (every non-`--final`
  build) unless `--allow-draft` is passed for deliberate circulation.
  *(tested: tests/test_docuseal.py)*
- **The signing roster is declarative.** `sc docuseal send <pdf>
  --envelope <name>` takes the signers from that envelope's
  `signers:` list in the matter's envelopes.yaml (name, email,
  optional human `note:`), in signing order — versioned intent
  instead of emails retyped from a conversation. `--to` remains for
  ad-hoc sends; the two are mutually exclusive. *(tested:
  tests/test_docuseal.py)*
- **The document is consulted before sending.** When the PDF's
  embedded field tags declare N signer roles, a roster of any other
  size refuses to send — a two-signer instrument dispatched to one
  signer is a defective ceremony. *(tested: tests/test_docuseal.py)*
- **`sc docuseal send <pdf> --to "Name <email>" [--to ...]`** uploads
  the document byte-identically, creates one submission with signers
  in the given order (roles `Signer 1..N`), emails them (unless
  `--no-email`), and writes `<pdf>.docuseal.json` beside the document:
  submission id, signers, signing URLs. The receipt is the durable
  record the other subcommands and the matter's history work from.
  Field placement comes from the build's `<pdf>.fields.json`
  sidecar when present — the renderer's exact geometry, sent as API
  field areas, keeping the PDF's text layer clean (nothing invisible
  rides a copy-paste) — else from embedded `{{...}}` text tags
  (`esign: tags` builds, the mode the free web UI's parser needs).
  Roles number in document order matching `--to` order (ADR-0027).
  A document with neither sends with a warning. *(tested:
  tests/test_docuseal.py; pleading/tests/test_signblocks.py)*
- **`sc docuseal status <id>`** prints per-signer state; exit 0 only
  when the submission is completed, 2 while anything is pending —
  scriptable polling. *(tested: tests/test_docuseal.py)*
- **`sc docuseal fetch <id> [--out DIR]`** downloads the signed
  document(s) AND the audit log for a completed submission, and
  refuses (exit 2, nothing written) while the submission is
  incomplete — a half-signed document must never land looking like
  an original. *(tested: tests/test_docuseal.py)*

- **The matter learns on the sync schedule.** `sc docuseal poll
  [matter]` — and the `docuseal` connector, which is a thin relay to
  it — walks every `*.docuseal.json` receipt, checks pending
  submissions, fetches completed ones into `inbox/docuseal/<id>/`
  (documents + audit log) printing `NEW` lines for triage, and marks
  the receipt so a completed submission is never polled again.
  Enable `connectors: {docuseal: {}}` in matter.yaml and the 12-hourly
  sync (or any manual `sc sync .`) carries it; no webhook server, by
  design — a local-first matter polls. *(tested: tests/test_docuseal.py)*

## Non-obvious constraints

- **Sending is publishing.** `send` transmits the document to the
  configured DocuSeal deployment. The tool warns about nothing here;
  the human (or the skill guiding an agent) decides what may leave
  the machine, and self-hosting is the answer when nothing may.
- **Fetched files are received originals**: they enter the matter
  through triage (inbox, INDEX row, `docket`/`intake` commit), and
  they get attested (`sc attest`) so their integrity outlives the
  service.
- The signing key for attestation and the e-signature service are
  unrelated systems on purpose: DocuSeal evidences *execution by
  humans*; attest evidences *bytes over time*.
