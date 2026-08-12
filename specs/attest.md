# Spec: cryptographic attestation (`sc attest`)

## Purpose

Make a document's authenticity checkable years later, by a
non-technical person, against a trust anchor that lives on executed
paper rather than in anyone's keyring (ADR-0022). gpg does the
cryptography; `crypto/attest.py` does the protocol.

## Promises

- **`sc attest hash <file>...`** prints each file's SHA-256 and
  SHA3-512, base64-encoded — the dual identity every other operation
  uses. Values match any independent implementation of those
  algorithms. *(tested: tests/test_attest.py)*
- **`sc attest sign <file>... [--key K] [--timestamp]`** writes a
  detached armored signature beside each file (`<file>.sig.asc`,
  SHA-512 digest), using the caller's normal gpg home. With
  `--timestamp`, each signature also gets an OpenTimestamps proof
  when `ots` is installed, and a stderr note (never a failure) when
  it is not. *(tested: tests/test_attest.py)*
- **`sc attest verify <file> --pubkey <key.asc> [--sig S]`** verifies
  the detached signature against the named key file ONLY: the key is
  imported into a throwaway keyring, so a valid signature by any
  other key fails, and the caller's keyring contents are irrelevant.
  Exit 0 on verification, 1 on any failure, with a one-line verdict.
  *(tested: tests/test_attest.py)*
- **`sc attest manifest write <out.md> <file>... [--key K]`** writes
  a clearsigned manifest: a statement of what the manifest means,
  then one row per file with both hashes. The statement says the
  manifest supersedes all earlier manifests by the same key — the
  mutable pointer under the immutable paper anchor.
  *(tested: tests/test_attest.py)*
- **`sc attest manifest verify <manifest.md> --pubkey <key.asc>
  [--dir D]`** verifies the clearsign against the named key, then
  recomputes both hashes of every listed file (beside the manifest,
  or in `--dir`). Any missing file, any hash mismatch, or an empty
  manifest is a failure; a row edited inside the signed block fails
  the signature itself. *(tested: tests/test_attest.py)*
- **`sc attest timestamp <file>...`** stamps existing files with
  OpenTimestamps proofs (`<file>.ots`), degrading to a stderr note
  without `ots`. *(untested: needs network)*

## Non-obvious constraints

- **Verification isolation is the protocol.** Building the throwaway
  keyring per verify is deliberate; do not "optimize" it into the
  user's keyring, and do not add a verify path that trusts keyring
  or keyserver state.
- **Signing is not isolated.** The signer's key lives in their gpg
  home under their agent and passphrase; attest passes `--local-user`
  and stays out of key management. Key generation, expiry, and
  revocation are the keyholder's job (the crypto-attest skill says
  how).
- **The manifest is markdown on purpose**: the audience includes
  people who will never run the tool, and the row format is regular
  enough that `manifest verify` parses it back mechanically.
