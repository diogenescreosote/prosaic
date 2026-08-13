# 0022 — Paper-anchored attestation: pinned keys, dual hashes, a signed manifest

**Status:** accepted (2026-08)

## Context
Matters need documents whose authenticity survives the author:
estate instruments, settlement terms, attestations meant to be
checked years later by non-technical people. Digital signatures can
do this, but the usual deployments anchor trust in the wrong places
— a keyserver, a keyring, a vendor — and overstate what a signature
proves. A signature proves possession of a key at an unverifiable
claimed time; it does not prove identity, intent, capacity, or
absence of coercion, and a stolen key signs as fluently as its
owner.

## Decision
`crypto/attest.py` (surfaced as `sc attest`) implements a protocol
with four commitments:

1. **The trust anchor is paper.** A signing key earns authority by
   being embedded — armored text plus a `\barcode` — in a
   traditionally executed document (witnessed, notarized). The tool
   never treats a keyring as an anchor: `verify` and
   `manifest verify` import the expected key file into a throwaway
   keyring and verify against it alone, so a valid signature by any
   other key fails.
2. **Documents are named by two hashes** (SHA-256 and SHA3-512, both
   base64), and a match means both match. No single algorithm's
   break orphans the record; the format is one a person can check
   with public tools.
3. **A signed manifest is the mutable pointer under the immutable
   anchor.** The paper anchors the KEY; the manifest — clearsigned,
   superseding all earlier manifests by the same key — names the
   operative version of every document. Revising one document means
   reissuing the manifest, not re-executing paper.
4. **Timestamps are evidence, not decoration.** A signature's
   claimed time is signer-asserted, so `--timestamp` stamps
   signatures and manifests with OpenTimestamps proofs; a proof
   anchored before a death or a dispute is what distinguishes the
   keyholder's signature from a key thief's afterward. Degrades
   gracefully (a warning, not a failure) when `ots` is absent.

What the tool deliberately does NOT claim: that a signature is
"conclusive" or "irrefutable" proof of anything. Documents built on
this protocol should state a rebuttable presumption and carve out
what statute reserves (in California, wills and codicils are outside
UETA; an electronic signature helps a § 6110(c)(2) harmless-error
showing but cannot substitute for execution formalities).

## Consequences
Signing stays in the user's normal gpg home (their key, their agent);
only verification is isolated. gpg joins the manifest as an optional
dependency — nothing else in prosaic needs it — and `ots`
(opentimestamps-client) ships with the python requirements. The
manifest format is parseable markdown, so `manifest verify` checks every hash mechanically, and a
row edited inside the clearsigned block fails the signature before
the hashes are even read.
