---
name: crypto-attest
description: Cryptographically attest matter documents - dual hashes, GPG detached signatures verified against a paper-anchored key, a signed manifest of operative versions, OpenTimestamps proofs. Use when a document needs signing, a signature or manifest needs verification, or a key needs its lifecycle set up.
---

# Cryptographic attestation

The protocol (ADR-0022, `specs/attest.md`): a key is anchored in an
executed paper document (armored block + `\qrblock`); a clearsigned
MANIFEST names the operative version of every document by dual hash;
detached signatures and timestamps make each document independently
checkable. Verification is always against the anchored key file,
never a keyring.

## Everyday operations

| Need | Command |
|---|---|
| Hash a document (both algorithms, base64) | `<prosaic>/cli/sc attest hash <file>` |
| Sign documents | `<prosaic>/cli/sc attest sign <file>... --key <fpr> --timestamp` |
| Verify one document | `<prosaic>/cli/sc attest verify <file> --pubkey <anchored-key.asc>` |
| Reissue the manifest after a revision | `<prosaic>/cli/sc attest manifest write MANIFEST.md <files>... --key <fpr> --timestamp` |
| Check everything at once | `<prosaic>/cli/sc attest manifest verify MANIFEST.md --pubkey <anchored-key.asc>` |

Signing uses the user's own gpg home (their agent asks for the
passphrase); you never handle key material. A failed verify is a
finding to report verbatim, not to explain away.

## What a signature means (say this correctly)

A signature proves possession of the key at a signer-asserted time
and nothing else. Never describe one as conclusive or irrefutable
proof of identity or intent; documents built on this protocol state a
rebuttable presumption. Timestamps (`--timestamp`, OpenTimestamps)
are what bound the signing time independently — recommend them on
every signature that matters.

## Key lifecycle (advise the human; do not do this for them)

- **Generate** with an expiry (3y is sensible: forced periodic
  review): `gpg --quick-gen-key "Name <email>" ed25519 sign 3y`.
- **Anchor**: export the armored public key and embed it, with a
  `\qrblockfile`, in the paper instrument that gives it authority.
- **Revocation certificate**: gpg writes one at generation
  (`openpgp-revocs.d/`); it must be stored OFFLINE, separate from
  the key — anyone holding it can kill the key.
- **Rotation/expiry**: a new key needs new paper (the anchor is the
  paper, not continuity of the keyring); prior signatures stay valid
  as evidence with their timestamps.
- **Compromise**: publish the revocation certificate, reissue the
  manifest under the successor key's paper anchor, and treat
  unrevoked post-compromise signatures as suspect — this scenario is
  why "irrefutable" must never appear in the instrument text.

References: `specs/attest.md`, ADR-0022, and the QR block section of
`pleading/pleading_markdown_spec.md`.
