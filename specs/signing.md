# Signing

One interface, several backends. The rest of the system holds a
`Signer` and never a backend: `signing/base.py` defines it,
`signing/local.py` signs here on this machine, `signing/docuseal.py`
adapts the existing e-signature client, and adding DocuSign means adding
a module and one line in `signing/__init__.py`.

The governing decision is [ADR-0036](../design/adr/0036-attest-artifacts-not-builds.md):
attest a specific artifact byte-for-byte and retain it, rather than
trying to make builds reproducible. Everything below follows from that.

## Promises

**Signing is a separate step from building, and never a side effect of
one.** `sc build --sign NAME` renders a cursive *font* into signature
blocks; it is a drafting convenience, produces no attestation, no
reference and no retained artifact, and is unrelated to this engine.
`sc sign apply` takes an already-built PDF and produces a new one. It
never modifies its input.

**The signed artifact never lands in a build directory.** A path under
`out/` is refused, by name, because the next build destroys it — which is
how signed documents have been lost. The default destination is
`<matter>/staging/<date>_<stem>_SIGNED.pdf`.

**Only what this system signs gets an attestation.** No attestation is
written for a document the local signer did not sign: proposed orders
carrying someone else's signature, documents sent through a remote
service that issues its own certificate, or paper signed by hand. A
backend states which kind it is through `produces_local_attestation`, so
callers never branch on a backend's name.

**Signature marks live outside every repository.** `signing/store.py`
resolves `--as KEY` against `~/.config/prosaic/signatures/KEY.{pdf,png,jpg}`
(override with `PROSAIC_SIGNATURE_DIR`) and **refuses** a mark that sits
inside a git work tree with a remote. A committed signature is a
published signature, and no later deletion unpublishes it.

**PDF is the preferred source when the mark is vector.** A signature
captured on a tablet or traced in a drawing program has no paper behind
it: rendering it with alpha gives real transparency with nothing to key
out, and it can be rendered at whatever resolution the page needs. A
store holding both `KEY.pdf` and `KEY.png` uses the PDF.

**A source that already carries transparency keeps its own colour.** Ink
colour is part of what makes a signature that person's. The `ink`
parameter applies only where alpha had to be derived from luminance ---
a scan of paper, which is effectively greyscale anyway.

**A sidecar binds a mark to an identity.** `KEY.meta.yaml` carrying
`name:` and `gpg_key:` means `sc sign apply --as KEY` needs neither
`--name` nor `--gpg-key`; an explicit flag still wins. This is more than
convenience: a fingerprint typed on a command line is the one thing in an
attestation nobody would notice was wrong. `sc sign marks` prints the
bound identity for each mark so a mistake is visible. A missing or
malformed sidecar degrades to "supply the flags", never to a crash --- a
*wrong* sidecar is the dangerous case, and no parsing strictness detects
that.

**Marks are never distorted.** Scaling is proportional and driven by
height; a mark may overhang its rule horizontally rather than be
compressed to fit. Background removal reads luminance as an alpha ramp,
so anti-aliased pen edges stay smooth instead of acquiring the halo that
keying out pure white produces.

**Slots are found by reading the printed page.** No markers are hidden
in the file. Invisible text was considered and rejected: it is still
selectable and still appears in `pdftotext` output, so a select-all on a
filed pleading would paste it. The signature blocks already print
distinctive text, and `signing/slots.py` matches on that — which also
means discovery works on flattened Judicial Council forms, where
`technology: overlay` has removed every widget.

**The slot vocabulary encodes form, not just content.** "Executed this
_____ day of" takes an ordinal; a bare "Dated: ______" takes a whole
date. `SlotRole` distinguishes them so nobody has to remember at signing
time.

**The stamp is an index, not a commitment.** It carries a random nonce
generated at signing time — never a digest of the file containing it,
which is self-referential and not computable. Format imitates a
document-management reference (`4823-9012-3391v1`): numeric, because real
DMS identifiers are database keys, and unlabelled, because a label is
what draws the eye. Unsigned output carries no stamp, since a stamp
asserts that a log entry exists. Pages with no clear margin are skipped
and reported rather than overprinted.

## The attestation record

Written under `<matter>/audit_log/signatures/<backend>/`, one directory
per signing event:

```
2026-08-25_declaration_4823-9012-3391v1/
    statement.txt          the claim, in plain language, with both digests
    statement.txt.asc      clearsigned by the signer's GPG key
    statement.txt.asc.ots  OpenTimestamps proof of the clearsigned claim
    attestation.json       the same facts, for machines
    <document>.pdf         the exact attested bytes
```

The GPG signature covers the **statement**, not the PDF directly. The
legally meaningful content is the sentence saying whose signature it is
and that they intend to be bound; detached-signing the PDF would
authenticate the file and leave the assertion about it unsigned. The
statement names the document by both hashes (SHA-256 and SHA3-512,
base64, per [ADR-0022](../design/adr/0022-paper-anchored-attestation.md)),
so signing the statement binds the claim to the bytes.

The retained PDF deliberately duplicates whatever copy lives in
`staging/` or `pleadings/`. Those get renamed, superseded and moved; an
attestation whose subject has been altered asserts nothing.

`gpg` is invoked **without** `--batch`, so pinentry can prompt for the
passphrase. Being asked is a feature: it is the moment the signature is
actually authorised. A failure to sign the statement aborts the whole
attestation rather than leaving an unsigned record.

## OpenTimestamps needs a second visit

`ots stamp` returns a calendar-server commitment immediately; the Bitcoin
attestation exists only hours later, after `ots upgrade`, and the
upgraded file must be retained. Until then the proof rests on the
calendar operator, which is a weaker claim than the one it will
eventually support. `sc sign verify` says so when it sees an un-upgraded
proof rather than reporting the record clean.

## Commands

```
sc sign marks                          marks available, and whose key each carries
sc sign slots <pdf>                    what blanks the document offers
sc sign apply <pdf> --as KEY [--name NAME] [--gpg-key FPR]
                             [--date YYYY-MM-DD] [-o OUT] [--no-timestamp]
sc sign verify <attestation-dir> [--pubkey KEY.asc]
```

`--name` and `--gpg-key` come from the mark's sidecar when omitted.

## Not covered

The GPG leg is untested in CI: generating a throwaway key needs a
running `gpg-agent`, unavailable in sandboxed runs. `signing/tests/`
stubs `_clearsign` and covers everything else — slot discovery against
real builds, mark preparation, aspect locking, stamp placement, the store
guard, digest mismatch detection, and the refusals.

Binding a signature to the *identity* of the key is out of scope here and
belongs to ADR-0022's paper anchor: a GPG signature proves possession of
a key, not whose key it is.
