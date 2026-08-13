# 0030 — RON through Proof; parallel clients, not an e-sign abstraction

**Status:** accepted (2026-08)

## Context
Notarization is the remaining ceremony the pipeline could carry:
the 2025 trust was already notarized remotely (Proof, the platform
formerly Notarize — a Nevada notary over video), by hand. Proof
publishes a Business API (dev.proof.com) whose shape fits the
existing pattern: create a transaction with a base64 document
marked `requirement: notarization`, poll `detailed_status` to
`complete`, download `final_document_url`s.

The tempting move was one generalized "e-signature service"
interface over DocuSeal and Proof. Rejected, deliberately: the two
protocols differ exactly where it matters (submission vs transaction
lifecycles, field tags vs notarial acts, documents endpoints vs
pre-signed URLs), the services occupy different legal roles (a
signature ceremony vs a notarial act), and an abstraction over two
instances is premature by definition. Parallel clients with the
same WORKFLOW shape — send/status/fetch/poll, receipts, a thin
connector relay, terminal statuses — share the discipline without
sharing code that would flatten the differences.

## Decision
`proof-client/client.py` (surfaced as `sc proof`), `*.proof.json`
receipts, the `proof` connector on the sync schedule, credentials
per ADR-0012 (PROOF_API_KEY / `prosaic.proof` Keychain), fairfax
sandbox via PROOF_URL. The DocuSeal integration renames from the
generic `esign` to `docuseal` throughout for the same reason the
abstraction was rejected: names should claim exactly what they are.
Both clients enforce the draft guard (ADR-0027) and mark
declined/expired/canceled ceremonies terminal per their services'
documented lifecycles.

## Consequences
A document needing a notarial act flows like one needing signatures:
roster/instruction → final build → send → receipt → scheduled poll →
inbox → triage → attestation. Costs: two clients to maintain (the
point), and the Proof client is UNTESTED AGAINST THE LIVE SERVICE —
mock-pinned to the documented contract only, stated in the client,
spec, and skill until a fairfax-sandbox run retires the caveat. A
third service, if ever wanted, gets its own client too; if a real
shared core emerges after that, extract it then, from evidence.
