# 0031 — Matters own their configuration; prosaic stores no state

**Status:** accepted (2026-08)

## Context
API keys for DocuSeal and Proof resolved to a prosaic-global
Keychain item (`prosaic.docuseal`, `prosaic.proof`) by default. That
works with one operator and one account per service, but it puts a
binding — *this matter signs with this credential* — in the tool
instead of the matter. Matters are the unit of everything else
(history, envelopes, receipts, backups); a matter carried to another
machine, or a future matter that must use a different account
(a client's DocuSeal instance, separate billing, a fiduciary's own
notary account), should carry its own bindings with it.

The hard constraint pulling the other way: key MATERIAL can never
live in a matter. Matters are git repositories, get backed up, get
shared in part; a secret written there is a secret leaked.

## Decision
Split the secret into material and reference. Material stays in the
operating system's credential store (macOS Keychain, ADR-0012).
The REFERENCE — which named credential this matter uses — lives in
the matter, in matter.yaml:

    connectors:
      docuseal:
        credential: prosaic.docuseal    # a global key, incorporated by reference
      proof:
        credential: proof.smith-estate  # or a matter-specific key
        url: https://api.fairfax.proof.com   # optional per-matter deployment

Resolution order in both clients: environment variable (an explicit
per-run operator act) → the matter's `credential:` reference →
and only OUTSIDE any matter, the global default name. Inside a
matter, a connector with no `credential:` is an error that prints
the exact lines to add: prosaic-global keys may exist, but a matter
must incorporate one by reference, never inherit it silently. A
per-matter `url:` rides along (self-hosted DocuSeal; the fairfax
sandbox for a matter still in rehearsal), with the environment still
winning.

## Consequences
Prosaic converges on implementing skills rather than storing state:
the repo holds mechanism, the Keychain holds material, the matter
holds bindings. Overengineered for one estate plan with one
operator — deliberately: the shape is cheap now and expensive to
retrofit after matters multiply. Costs: every matter that enables a
connector must say its credential (one line, and the error message
is the documentation); the clients each carry ~40 lines of
matter-config resolution, kept parallel rather than shared per
ADR-0030. Future connector configuration (polling cadence, notary
preferences) has an obvious home.
