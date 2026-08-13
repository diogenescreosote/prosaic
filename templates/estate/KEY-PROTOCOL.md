# The Key Protocol — read this if you are checking a document

*(Template: adapt names, then keep this file beside the documents it
describes. It is written for the person — executor, trustee, family
member — who has to verify a document years from now and does not
speak cryptography. The design is ADR-0022 in the prosaic repo.)*

## What anchors what

1. **Paper anchors the key.** The will and the trust each embed, in
   their signed and witnessed/notarized text, one public key (the
   "Anchored Key") — printed as text and as a QR code. The paper
   documents got their authority the old way: signatures, witnesses,
   a notary. The key gets its authority from being inside them.
2. **The key vouches for the manifest.** A file named `MANIFEST.md`
   is signed with the Anchored Key. It lists every current estate
   document with two fingerprints (hashes) per document.
3. **The manifest vouches for the documents.** A document whose
   BOTH hashes match its manifest row is the operative version. A
   newer signed manifest replaces an older one entirely.

## How to check a document (no special software)

1. Compute the file's SHA-256 and SHA3-512 hashes, Base64-encoded.
   Any reputable online hash tool can do this; select the algorithm
   and choose Base64 (not hex) output.
2. Compare both values to the document's row in `MANIFEST.md`. Both
   must match. One match is not enough.

## How to check properly (with software)

```
sc attest manifest verify MANIFEST.md --pubkey anchor-key.asc
sc attest verify <file> --pubkey anchor-key.asc
```

`anchor-key.asc` must be the key from the paper: scan the QR code in
the executed will or trust, or retype the printed block. Do not
substitute a key from a keyserver, an email, or anyone's computer —
paper is the anchor.

## What a signature does and does not prove

A cryptographic signature proves that someone possessing the key
signed those exact bytes. It does not by itself prove who, when, or
willingly. That is why:

- every signature here carries a **trusted timestamp** (an
  independent proof the signature existed by a certain date), and
- the legal documents give a verified signature a **presumption**,
  not a guarantee — a presumption that evidence of theft, coercion,
  or incapacity can defeat.

If the timestamps say a "signature" was created after the
keyholder's death, treat it as what it is.

## Key lifecycle (for the keyholder)

- The key was generated with a three-year expiry, forcing periodic
  review. Renewal extends the same key; replacement requires new
  paper (a new will/trust or a formally executed key-succession
  instrument), because paper is the anchor.
- A revocation certificate exists, stored offline and separately.
  If the key is ever compromised: publish the revocation, execute a
  successor anchor on paper, reissue the manifest under the new key.
- After each document change: `sc attest sign` the new version,
  `sc attest manifest write` a fresh manifest, timestamp both, and
  store copies where the people who will need them can find them.
