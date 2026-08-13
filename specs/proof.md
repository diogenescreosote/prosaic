# Spec: remote online notarization (`sc proof`)

## Purpose

Get a document notarized by a commissioned online notary without
anyone leaving their desk, and bring the notarized original back
into the matter. Proof (proof.com, the platform formerly Notarize)
does identity proofing, the video session, and the notarial act;
`proof-client/client.py` does prosaic's side. Deliberately a
SEPARATE client from DocuSeal's (ADR-0030): different service,
different protocol, no premature generalization.

## Promises

- **`sc proof send <pdf> --to "Name <email>"`** creates and
  activates a notarization transaction (base64 document,
  `requirement: notarization`), refuses DRAFT-stamped PDFs without
  `--allow-draft`, and writes `<pdf>.proof.json` beside the document
  — transaction id, per-signer access links — the memo everything
  later works from. *(tested: tests/test_proof.py)*
- **`sc proof status <id>`** prints the transaction's
  `detailed_status`; exit 0 only at `complete`. *(tested)*
- **`sc proof fetch <id> [--out D]`** downloads the notarized
  document(s) via their pre-signed `final_document_url`s, refusing
  (exit 2, nothing written) while incomplete. *(tested)*
- **`sc proof poll [matter]`** — and the `proof` connector riding
  the sync schedule — walks every `*.proof.json` receipt, fetches
  completed transactions into `inbox/proof/<id>/` with `NEW` lines
  for triage, and marks expired/canceled transactions terminal so a
  dead ceremony is a recorded fact, not an eternal retry. *(tested)*
- **Deployment and credentials**: `PROOF_URL` selects production
  (`https://api.proof.com`, default) or the fairfax sandbox
  (`https://api.fairfax.proof.com`); the key resolves
  `PROOF_API_KEY` then the `prosaic.proof` Keychain entry. Auth is
  Proof's `ApiKey` header. *(tested against a mock)*

## Non-obvious constraints

- **Not yet exercised against a live Proof account.** The mock pins
  our side of the documented contract (dev.proof.com); the first
  real run should target the fairfax sandbox, and this caveat (here
  and in the client docstring) comes out when it passes.
- **RON validity is jurisdictional.** California recognizes
  out-of-state notarizations valid where performed; the 2025 trust
  was notarized exactly this way (Proof, Nevada notary). The
  execution checklist, not this client, is where that judgment
  lives.
- **A will is never notarized into validity** — witnesses, not
  notaries (Prob. Code § 6110); the wet-ink rule in
  templates/estate/EXECUTION.md is unaffected by this client
  existing.
