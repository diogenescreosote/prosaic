# 0023 — E-signature through DocuSeal, cloud or self-hosted behind one interface

**Status:** accepted (2026-08); transport moved to the official SDK by ADR-0027

## Context
Some matter documents need real-world signatures from people who will
not install anything: estate instruments, agreements, verifications.
An e-signature service handles delivery, identity capture, and an
audit trail. DocuSeal is open source, self-hostable, and its hosted
service and self-hosted instances expose the same API — which makes
it the rare case where "local-first" and "just works today" are the
same integration.

## Decision
`docuseal-client/client.py` (surfaced as `sc docuseal`) speaks the DocuSeal API
with three subcommands: `send` (create a template from a PDF, create
a submission, email the signers, write a receipt beside the
document), `status`, and `fetch` (signed PDFs plus the audit log,
only for completed submissions). Deployment is one variable:
`DOCUSEAL_URL` defaults to the hosted API and points anywhere a
self-hosted instance lives. The API key is a named credential per
ADR-0012 — `DOCUSEAL_API_KEY` in the environment, else the
`prosaic.docuseal` Keychain entry — never a config value.

Field placement uses DocuSeal's text tags (`{{Signature}}` and
kindred) detected in the document text, so the pleading language can
mark where signatures go; a document without tags sends with a
warning. The client is stdlib urllib: the API surface used is five
requests, and a dependency would be heavier than the code.

## Consequences
Signed originals come back as files beside an audit log and enter the
matter through triage like any other received document — then get
attested (ADR-0022) so their integrity stops depending on DocuSeal.
Sending a document to signers transmits it to whatever DocuSeal
deployment is configured: for privileged material that must not
touch a third party, self-host — the tool cannot make that judgment
and the skill says so. Tests run against a local mock of the API
surface, so the contract is pinned without an account or network.
