# Execution checklist

*(California requirements, stated as of this template's writing —
verify anything load-bearing against the current statute. Nothing
here is legal advice.)*

## Before any signing ceremony

- [ ] Names, dates, and shares are final; every `[bracket]` filled.
- [ ] The Anchored Key in the will and trust is YOUR key (armored
      block and `assets/anchor-key.asc` both replaced), generated
      with an expiry, revocation certificate stored offline.
- [ ] `notreal:` removed from the source; rebuilt with `--final`
      (`make <envelope> FINAL=1`); PDF proofread. Only this build
      lacks the DRAFT banner.
- [ ] The build's barcode scans back to your key (any PDF417-capable
      scanner app), and the printed fingerprint matches
      `gpg --fingerprint` for your key.

## The will — paper only

Prob. Code § 6110: signed by the testator, and witnessed by **two
adults who are both present at the same time** and who understand
the instrument is the testator's will. No notary substitutes for
witnesses; remote/electronic execution is not authorized for
California wills.

- [ ] Print. One sitting: testator signs; both witnesses watch, then
      sign the attestation, all three present together throughout.
- [ ] Prefer witnesses who take nothing under the will (a gift to a
      subscribing witness creates a statutory presumption problem,
      Prob. Code § 6112).
- [ ] Store the wet-ink original where the executor can get it;
      scans are working copies, not the will.

## The trust, certification, and power of attorney — notarize

- [ ] Trust: settlor signs; notary acknowledgment (the California
      certificate text is in the template). Remote online
      notarization through a service satisfying California's
      recognition of out-of-state notarizations has been used for
      instruments like these; keep the RON provider's certificate
      and audit trail with the document.
- [ ] Certification of trust: same acknowledgment; keep several
      originals — banks like to keep one.
- [ ] Power of attorney: notary OR two adult witnesses (agent may
      not witness), § 4402.
- [ ] Health care directive: two qualified witnesses (statutory
      declarations, § 4701) or a notary, § 4673-4675.
- [ ] E-signature ceremonies (`sc docuseal`) work for the notarized
      documents where your notary/RON flow accepts them — never for
      the will.

## After execution — bind the crypto to the paper

- [ ] Scan each executed original to PDF; these scans are now the
      operative digital copies.
- [ ] `sc attest sign <each>.pdf --key <fpr> --timestamp`
- [ ] `sc attest manifest write MANIFEST.md <all pdfs> --key <fpr>
      --timestamp`
- [ ] `sc attest manifest verify MANIFEST.md --pubkey
      anchor-key.asc` — from a clean directory, the way a stranger
      would.
- [ ] Distribute: the executor/successor trustee gets the storage
      location, the KEY-PROTOCOL.md, and enough to verify — not the
      private key.
- [ ] Calendar the key expiry and a yearly review (beneficiary
      designations, guardianship, new assets).

## Funding the trust (the step everyone skips)

An unfunded living trust is a pour-over will with extra steps.

- [ ] Retitle: bank and brokerage accounts, real property (deed to
      trustee; county transfer-tax exemption for trust transfers),
      vehicles as appropriate.
- [ ] Beneficiary designations: life insurance and retirement
      accounts per your plan (get advice on retirement accounts —
      naming a trust has income-tax consequences).
- [ ] The certification of trust is the document institutions
      actually want; carry it, not the trust.
