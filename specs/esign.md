# Spec: e-signature (`sc esign`)

## Purpose

Get a document signed by people who install nothing, and bring the
signed original plus its audit trail back into the matter
(ADR-0023). DocuSeal does delivery and capture; `esign/docuseal.py`
does prosaic's side.

## Promises

- **Deployment is one variable.** Every request goes to
  `DOCUSEAL_URL` (default `https://api.docuseal.com`); a self-hosted
  instance needs nothing but that variable. The API key resolves
  `DOCUSEAL_API_KEY` first, then the `prosaic.docuseal` Keychain
  entry, and a missing key is a clear how-to-configure error — never
  a silent default. *(tested: tests/test_esign.py)*
- **`sc esign send <pdf> --to "Name <email>" [--to ...]`** uploads
  the document byte-identically, creates one submission with signers
  in the given order (roles `Signer 1..N`), emails them (unless
  `--no-email`), and writes `<pdf>.esign.json` beside the document:
  submission id, signers, signing URLs. The receipt is the durable
  record the other subcommands and the matter's history work from.
  A document with no `{{...}}` text tags sends with a warning.
  *(tested: tests/test_esign.py)*
- **`sc esign status <id>`** prints per-signer state; exit 0 only
  when the submission is completed, 2 while anything is pending —
  scriptable polling. *(tested: tests/test_esign.py)*
- **`sc esign fetch <id> [--out DIR]`** downloads the signed
  document(s) AND the audit log for a completed submission, and
  refuses (exit 2, nothing written) while the submission is
  incomplete — a half-signed document must never land looking like
  an original. *(tested: tests/test_esign.py)*

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
