---
name: estate-plan
description: Draft, execute, and cryptographically bind a small California estate plan from the estate pack templates - pour-over will, living trust, certification of trust, powers of attorney, health care directive, anchored-key protocol. Use when someone wants estate documents drafted or amended, or when executed estate documents need attestation, manifest, or verification work.
---

# Estate plan

The templates live in `templates/estate/` (see its README); the
protocol they implement is ADR-0022/ADR-0025. You draft and verify;
execution — signing, witnessing, notarizing — is entirely human, and
you never remove a `notreal:` marker.

## Drafting

1. Work in a matter; copy the needed templates into `src/` and the
   pack's `assets/anchor-key.asc` placeholder into `assets/`.
2. Substitute names, dates, shares, nominees. Keep the articles
   short — these documents are built to be read. If the user's
   situation exceeds the templates (taxable estate, blended family,
   business interests, expected contest), say so and recommend
   counsel rather than improvising provisions.
3. The Anchored Key: the user generates their own
   (`crypto-attest` skill has the lifecycle); paste the armored
   block into the will and trust AND replace `assets/anchor-key.asc`
   so the QR encodes the same key. The two must be identical.
4. Statutory-form documents (power of attorney § 4401, health care
   directive § 4701): the statute's text controls; verify the
   mandatory language against the current statute before the user
   executes.
5. Build (`doctype: document` renders plain instruments), then
   proofread the PDF and confirm the QR decodes to the user's key.

## Language discipline (the protocol depends on it)

- Never write that a signature is "conclusive" or "irrefutable"
  proof of anything. The instruments grant a **rebuttable
  presumption** to signatures that verify against the Anchored Key
  AND carry a trusted timestamp — and wills/codicils are always
  excluded (California did not adopt electronic wills; Prob. Code
  § 6110 formalities control).
- Phrase guardianship as "any child of mine under eighteen" — the
  leak guard bans the two-word family-law phrase for it repo-wide,
  and will fail the push if a template says it.
- Document versions are identified by the signed Manifest, never by
  hashes hard-coded across instruments — a hard-coded hash makes
  every revision a re-execution of paper.

## Publishing to the share folder

Estate matters (`case.type: estate` in matter.yaml) keep a `share/`
directory — the outward face, shared with beneficiaries and
fiduciaries (specs/matter.md, ADR-0028). Rules when publishing:

1. `share/` receives COPIES of executed deliverables only; the
   originals stay in `assets/executed/`. After every copy,
   `sc attest hash` both and compare — a share folder that drifts
   from the record is worse than none.
2. Keep the tree human: instruments alone in `Executed Documents/`;
   signatures, proofs, keys, and the verification how-to in
   `Verification/`; never commingle sidecars with documents.
3. `START HERE.md` is the reader's entry point — keep it current
   when fiduciaries, documents, or instructions change, in the same
   commit as the change it reflects.
4. `Inbox/` contents are claims, not records: triage them into the
   matter like any inbox, and never treat `share/` as a source.
5. Drive permissions are the human's to set (the folder to the
   named people; `Inbox/` writable by them; `Public/` broader) —
   remind, don't attempt.

## Execution and after

Walk the user through `templates/estate/EXECUTION.md`: the will is
paper-with-both-witnesses-present, the rest notarize (RON works;
`sc esign` can carry the notarized-document ceremonies, never the
will). After execution: scan, `sc attest sign --timestamp`,
`sc attest manifest write --timestamp`, verify from a clean
directory, and make sure the successor fiduciaries hold
`KEY-PROTOCOL.md` and know where the originals live.

References: `templates/estate/README.md`, ADR-0025, ADR-0022,
[crypto-attest](../crypto-attest/SKILL.md), [esign](../esign/SKILL.md).
