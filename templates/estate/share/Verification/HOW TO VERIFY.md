# How to verify these documents

*(Template: adapt alongside KEY-PROTOCOL.md in the estate pack; keep
the fingerprint and examples in sync with the real key.)*

Every document in `Executed Documents/` can be proven authentic and
unaltered, without trusting whoever handed you this folder.

## The quick check (no software)

Each executed document's SHA-256 and SHA3-512 hashes are listed in
the signed attestation in this folder. Compute the file's hashes
with any reputable tool (choose Base64 output) and compare — both
must match.

## The full check

The signer's public key (the "Anchored Key") is embedded in the
executed will and trust themselves — as printed text, a fingerprint,
and a scannable barcode — and a copy sits here as `anchor-key.asc`
(fingerprint: `5EDF 79A0 477D BBDE 38AC  F791 6676 E412 5898 C933`).
`signatures/` holds a detached signature for each document and an
OpenTimestamps proof (`.ots`) that the signature existed by a given
date. With [prosaic](https://github.com/diogenescreosote/prosaic):

```
sc attest verify "<document>" --sig "signatures/<document>.sig.asc" \
    --pubkey anchor-key.asc
```

or with plain gpg: import `anchor-key.asc` into an empty keyring and
`gpg --verify` the signature against the document. Trust the key
because the paper instruments embed it — not because a keyserver or
an email says so.
