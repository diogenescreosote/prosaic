# ADR-0036: Attest artifacts byte-for-byte; offer no build reproducibility

**Status:** Accepted (August 25, 2026)

## Context

Cryptographic attestation of signed documents invites an appealing
design: make the build byte-reproducible, digest the *source*, and bind
a signature to that digest. The build then becomes a pure function, and
"is this the signed document?" is answered by rebuilding.

It does not survive contact with either the engineering or the legal
requirement.

**Engineering.** Byte-reproducibility over a document pipeline means
pinning every dependency forever: the PDF writer, the typesetter, font
files and their subsetting, image codecs, and the OS libraries beneath
them. Creation timestamps and font-subset identifiers alone break it.
Buying that guarantee costs the ability to upgrade packages, fix bugs,
or change anything about rendering — permanently, since a signature
attested against last year's toolchain must still verify next year.

The correct analogy is an HTML source file. It is not guaranteed to
render pixel-for-pixel identically across browser versions, and nobody
considers that a defect, because the source was never the artifact.

**Legal.** More decisively: reproducibility would be evidence of
nothing. No court asks whether a filing can be regenerated from source.
The question is always whether a particular document is the one that
was signed, served, and filed. That is answered by retaining the bytes
and attesting them — a claim about a file, not about a pipeline. A
reproducible build is a developer convenience mistaken for a chain of
custody.

This is also already the workspace's discipline elsewhere: `pleadings/`
holds the court-filed version and nothing else, precisely because the
filed artifact is the document and everything under `src/` is drafting
apparatus.

## Decision

1. **No reproducibility guarantee.** Builds offer no byte-level and no
   pixel-level consistency between versions of the toolchain. Nothing
   in the system may depend on rebuilding a source to yield the same
   file, and no guard may be written whose correct operation requires
   it.

2. **Attestation is over a specific artifact, byte-for-byte.** The unit
   of attestation is the exact file sent for filing or service — the
   PDF, and optionally a rasterized rendering of it alongside, which is
   immune to PDF-internal churn and is what a human would actually
   compare. Digests are computed over those bytes. Both SHA-256 and
   SHA3-256 are recorded: SHA-256 because `shasum -a 256` is available
   to any verifier without installing anything, SHA3-256 for longevity.

3. **Attested artifacts must be retained.** An attestation whose
   subject has been deleted asserts nothing. Retention of the exact
   attested bytes is part of the attestation, not an optional
   companion to it.

4. **Signing is an event, not a property of a source.** The build
   produces unsigned output and never applies a signature as a side
   effect. A separate, explicitly invoked step takes one built file,
   applies the signature mark, stamps it, hashes the result, signs a
   statement of assent over that hash, timestamps it, and appends a log
   entry. Rebuilding a source neither reproduces nor re-signs a signed
   artifact, and does not need to.

5. **The on-page stamp is an index, not a commitment.** Where an
   identifier is printed, it encodes a **random nonce generated at
   signing time** — never a digest of the containing file, which is
   self-referential and cannot be computed. The log maps nonce to full
   digests. Nobody verifies the stamp; it is how a human finds the log
   entry, so truncation is a legibility decision rather than a security
   one.

6. **The log records the source commit for provenance only.** It
   locates the drafting state that produced the artifact. It is not
   part of the attestation and carries no reproducibility claim.

## Consequences

**Drift between a signed artifact and its source becomes possible and
must be reported rather than prevented.** Sign an artifact, edit the
source, and the two legitimately diverge — `out/` regenerates something
different while the signed file stands unchanged. No build failure can
detect this honestly, because a differing rebuild is also the expected
result of a package upgrade. The available check is a *report*: the
signed artifact for this envelope was signed from commit X, HEAD is Y,
and these sources changed in between. Advisory, never a gate.

**A digest-binding guard on rebuild is unavailable, and this is a
gain.** Such a guard would misfire on every innocent toolchain change
and would be trained away within a week. Decision 4 makes it
unnecessary: a signature cannot appear on text nobody assented to,
because no build ever applies one.

**Wet-signed paper needs two digests.** Build to PDF, print, sign by
hand, scan, and the scanned artifact has a different hash than the
built one. The log must name both and state the relationship. Wholly
programmatic signing avoids this by producing a single artifact, which
is a further argument for it.

**Verification requires no part of this system.** A third party checks
an attestation with `shasum`, `gpg --verify`, and the OpenTimestamps
client against retained files. That is the point: the claim outlives
the tooling that produced it.
