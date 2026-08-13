# 0025 — An estate pack: plain-document instruments on the attestation protocol

**Status:** accepted (2026-08)

## Context
prosaic's machinery — markdown to executed-quality PDF, QR blocks,
paper-anchored attestation (ADR-0022), e-signature (ADR-0023) — is
what a self-maintained estate plan needs, and "personal legal ops"
is a natural widening of scope for a tool built on the premise that
a legal file is a directory a person controls. What must NOT widen:
the no-personal-data rule (templates are Jane Roe end to end, and
the local leak-guard denylist grows accordingly), and honesty about
what a template is.

## Decision
`templates/estate/` ships five California instruments (pour-over
will, revocable living trust, § 18100.5 certification, § 4401 power
of attorney, § 4701 health care directive), a key-protocol document
written for the eventual verifier, and execution checklists. Two
rendering features carry them: `doctype: document` (a plain
instrument: centered title, letter geometry, no caption or grid) and
`heading_numbers: false` (headings that carry their own
enumeration).

The legal design decisions, made deliberately:

1. **Rebuttable presumption, never "conclusive."** A signature
   verifying against the Anchored Key with a trusted timestamp is
   presumed authentic; clear and convincing evidence of forgery,
   key compromise, or incapacity defeats it. A stolen key must not
   inherit an "irrefutable" clause.
2. **The trust gets the full protocol; the will gets an evidentiary
   hook.** California excludes wills from UETA and has no electronic
   wills act: a signed record can help a § 6110(c)(2) showing but
   cannot amend a will. Trust amendments are not so excluded. The
   instruments state the asymmetry instead of implying parity.
3. **The manifest replaces cross-instrument hash pins.** Hard-coding
   the will's hash in the trust makes every will revision a trust
   re-execution; the signed, timestamped, superseding manifest is
   the mutable pointer, and paper anchors only the key.
4. **An incapacity mechanism** (two physicians' certification, with
   reliance protection) — "while living and competent" with no
   decider is a latent dispute.
5. **Statutory-form documents defer to the statute.** The § 4401 and
   § 4701 templates carry the structure and flag the mandatory text
   as the statute's, to be verified current at execution — a
   paraphrase that silently drifts from mandatory language is worse
   than a pointer.

## Consequences
Estate work becomes a matter like any other: drafted in markdown,
built by the pipeline, attested under the protocol, with the
TEMPLATE banner on every page until a human clears it. The pack's
tests pin the protections (banner present, execution language
present, "irrefutable"/"conclusive" absent, the QR decoding to the
shipped key). The disclaimer posture is the repo's: a starting
point a careful person can read entirely, not legal advice, and not
a substitute for counsel where the situation warrants it.
